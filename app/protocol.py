"""Local stdio App Server adapter; all model authentication stays on this PC."""
from __future__ import annotations
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
from collections import OrderedDict
from . import __version__
from .runtime_check import runtime_status, require_project_runtime, runtime_environment


def without_null_fields(value):
    """config/read returns optional nulls; JSON-to-TOML overrides cannot encode them."""
    if isinstance(value, dict):
        return {key: without_null_fields(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [without_null_fields(item) for item in value]
    return value


class Cancelled(RuntimeError):
    pass


def stop_process_tree(process):
    if not process or process.poll() is not None:
        return
    if os.name == "nt":
        result = subprocess.run(
            ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=12)
        if process.poll() is None and result.returncode:
            process.kill()
    else:
        process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


class TurnView:
    def __init__(self, role, step, thread_id=""):
        self.role, self.step, self.thread_id = role, step, thread_id
        self.turn_id = ""
        self.blocks = OrderedDict()
        self.summaries = OrderedDict()
        self.tools = OrderedDict()
        self.status = "running"
        self.error = ""
        self.usage = {}
        self.revision = 0

    def item(self, item, complete=False):
        kind, key = item.get("type", ""), str(item.get("id", "unknown"))
        if kind == "agentMessage":
            self.blocks[key] = {"text": item.get("text", ""), "phase": item.get("phase") or ""}
        elif kind == "reasoning":
            # Only the public summary is displayed. Raw reasoning content is ignored.
            summary = item.get("summary") or []
            if summary:
                text = "\n".join(x if isinstance(x, str) else x.get("text", "") for x in summary)
                self.summaries[key] = text
        elif kind not in ("userMessage", "hookPrompt"):
            detail = item.get("command") or item.get("tool") or item.get("query") or kind
            output = item.get("aggregatedOutput") or item.get("text") or ""
            if kind == "fileChange":
                detail = ", ".join(x.get("path", "") for x in item.get("changes", []))
            if item.get("error"):
                output = str(item["error"])
            self.tools[key] = {
                "kind": kind, "name": str(detail)[:2000],
                "status": item.get("status") or ("completed" if complete else "running"),
                "output": str(output)[-12000:],
            }
        self.revision += 1

    def feed(self, method, params):
        if params.get("threadId") and params["threadId"] != self.thread_id:
            return
        event_turn = params.get('turnId')
        if method in ('turn/started', 'turn/completed'):
            event_turn = (params.get('turn') or {}).get('id') or event_turn
        if self.turn_id and event_turn and event_turn != self.turn_id:
            return
        if method == "turn/started":
            self.turn_id = params["turn"]["id"]
        elif method == "item/agentMessage/delta":
            key = str(params["itemId"])
            block = self.blocks.setdefault(key, {"text": "", "phase": ""})
            block["text"] += params.get("delta", "")
        elif method == "item/reasoning/summaryTextDelta":
            key = str(params["itemId"])
            self.summaries[key] = self.summaries.get(key, "") + params.get("delta", "")
        elif method in ("item/started", "item/completed"):
            self.item(params.get("item", {}), method.endswith("completed"))
        elif method in ("item/commandExecution/outputDelta", "item/fileChange/outputDelta"):
            key = str(params.get("itemId", "tool"))
            tool = self.tools.setdefault(key, {"kind": "commandExecution", "name": "", "status": "running", "output": ""})
            tool["output"] = (tool["output"] + params.get("delta", ""))[-12000:]
        elif method == "thread/tokenUsage/updated":
            self.usage = params.get("tokenUsage", {})
        elif method == "turn/completed":
            turn = params.get("turn", {})
            if self.turn_id and turn.get("id") != self.turn_id:
                return
            for item in turn.get("items", []):
                self.item(item, True)
            self.status = turn.get("status", "failed")
            self.error = (turn.get("error") or {}).get("message", "")
        elif method == "error":
            self.error = (params.get("error") or {}).get("message", "Codex 报告错误")
        self.revision += 1

    def snapshot(self):
        values = list(self.blocks.values())
        finals = [x["text"] for x in values if x.get("phase") == "final_answer"]
        answer = finals[-1] if finals else (values[-1]["text"] if values else "")
        return {
            "role": self.role, "step": self.step, "thread_id": self.thread_id,
            "turn_id": self.turn_id, "status": self.status, "error": self.error,
            "blocks": list(self.blocks.values()), "summary": "\n\n".join(self.summaries.values()),
            "tools": list(self.tools.values()), "answer": answer,
            "usage": self.usage, "revision": self.revision,
        }


class RpcClient:
    def __init__(self, command, data_dir, note=lambda message: None):
        self.command = list(command)
        self.data_dir = Path(data_dir)
        self.note = note
        self.process = None
        self.process_job = None
        self.cleanup_pending = False
        self.messages = queue.Queue()
        self.responses = {}
        self.sensitive_requests = set()
        self.counter = 0
        self.current = None
        self.last_partial = None
        self.pending_turn_events = []
        self.pump = lambda: None
        self.changed = lambda value: None
        self.log = None
        self.log_lock = threading.Lock()
        self.readers = []
        self.turn_started_at = None
        self.last_turn_event_at = None
        self.turn_event_count = 0

    def start(self):
        if self.cleanup_pending:
            raise RuntimeError('上次执行进程清理未确认完成，禁止发送新请求；请先断开并核查清理错误。')
        if self.process and self.process.poll() is None:
            return
        self.close()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.messages = queue.Queue()
        self.responses = {}
        self.log = open(self.data_dir / ("app-server-" + time.strftime("%Y%m%d-%H%M%S") + ".jsonl"), "ab")
        try:
            if os.name == 'nt':
                from .process_job import ProcessJob, ensure_host_guard
                ensure_host_guard()
                self.process_job = ProcessJob()
            self.process = subprocess.Popen(
                self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                cwd=str(self.data_dir), env=runtime_environment(self.command),
                creationflags=(subprocess.CREATE_NO_WINDOW | 0x4) if os.name == 'nt' else 0,
            )
            if self.process_job:
                # No initialize, thread/start or turn/start is sent until ownership
                # is established. Assignment failure must never fall back to RPC.
                self.process_job.assign(self.process)
                self.process_job.resume(self.process)
        except Exception:
            self.close()
            raise
        self.readers = [threading.Thread(target=self._reader, args=(pipe, err), daemon=True)
                        for pipe, err in ((self.process.stdout, False), (self.process.stderr, True))]
        for reader in self.readers:
            reader.start()
        self.call("initialize", {"clientInfo": {"name": "agentlink_gui", "title": "AgentLink GUI", "version": __version__},
                                 "capabilities": {"experimentalApi": True}}, timeout=40)
        self.send({"method": "initialized"})

    def _reader(self, pipe, stderr):
        try:
            while True:
                raw = pipe.readline(4 * 1024 * 1024)
                if not raw:
                    break
                if stderr:
                    # Diagnostic stderr stays local; do not mirror server credentials or URLs to peers.
                    with open(self.data_dir / "app-server-stderr.log", "ab") as out:
                        out.write(raw)
                    continue
                try:
                    message = json.loads(raw.decode("utf-8-sig"))
                    if not isinstance(message, dict):
                        raise ValueError("JSON event is not an object")
                except (ValueError, UnicodeError):
                    message = {"method": "_unparsed", "params": {"text": raw.decode("utf-8", "replace")[:500]}}
                method = message.get("method", "")
                if method != "item/reasoning/textDelta" and not method.startswith("account/"):
                    with self.log_lock:
                        if self.log and not self.log.closed:
                            if message.get('id') in self.sensitive_requests:
                                self.log.write((json.dumps({'id': message['id'], 'redacted': 'config response'}) + '\n').encode('utf-8'))
                            else:
                                self.log.write(raw)
                            self.log.flush()
                self.messages.put(message)
        finally:
            if not stderr:
                self.messages.put({"method": "_eof"})

    def send(self, message):
        if not self.process or self.process.poll() is not None:
            raise RuntimeError("Codex App Server 已退出，请重新连接节点。")
        data = (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8")
        self.process.stdin.write(data)
        self.process.stdin.flush()

    def request(self, method, params):
        self.counter += 1
        request_id = self.counter
        if method == 'config/read':
            self.sensitive_requests.add(request_id)
        self.send({"id": request_id, "method": method, "params": params})
        return request_id

    def call(self, method, params, timeout=40):
        request_id = self.request(method, params)
        deadline = None if timeout is None else time.monotonic() + timeout
        while request_id not in self.responses:
            self.pump()
            if deadline is not None and time.monotonic() > deadline:
                raise TimeoutError("Codex 接口超时：" + method)
            self.poll(0.1)
        response = self.responses.pop(request_id)
        if "error" in response:
            raise RuntimeError(method + ": " + str(response["error"].get("message", response["error"])))
        return response.get("result", {})

    def poll(self, timeout=0.0):
        try:
            message = self.messages.get(timeout=timeout)
        except queue.Empty:
            return
        if "method" not in message:
            self.responses[message.get("id")] = message
            return
        method, params = message["method"], message.get("params") or {}
        if method == "_eof":
            raise RuntimeError("Codex 进程意外退出；日志保留在本机。")
        if "id" in message:
            self._server_request(message)
        elif method == "_unparsed":
            self.note("无法识别的接口输出已保存在本机日志。")
        elif self.current:
            if not self.current.turn_id:
                # turn/start can interleave notifications with its response.
                # Bind the response ID before accepting any turn content.
                self.pending_turn_events.append((method, params))
                return
            self._feed_current(method, params)

    def _feed_current(self, method, params):
        before = self.current.revision
        self.current.feed(method, params)
        if self.current.revision != before:
            self.last_turn_event_at = time.monotonic()
            self.turn_event_count += 1
            self.changed(self.current.snapshot())

    def activity_snapshot(self):
        if self.current is None or self.turn_started_at is None:
            return None
        stamp = time.monotonic()
        silence = max(0, stamp - (self.last_turn_event_at or self.turn_started_at))
        running_tools = sum(t.get('status') in ('inProgress', 'running', 'started')
                            for t in self.current.tools.values())
        alive = bool(self.process and self.process.poll() is None)
        phase = ('process_exited' if not alive else
                 'tool_running' if running_tools else
                 'quiet' if silence >= 60 else 'working')
        return {'step': self.current.step, 'turn_id': self.current.turn_id,
                'phase': phase, 'process_alive': alive, 'running_tools': running_tools,
                'elapsed_seconds': int(max(0, stamp - self.turn_started_at)),
                'event_age_seconds': int(silence), 'event_count': self.turn_event_count}

    def _server_request(self, message):
        method = message["method"]
        if method in ("item/commandExecution/requestApproval", "item/fileChange/requestApproval"):
            result = {"decision": "decline"}
        elif method == "item/permissions/requestApproval":
            result = {"permissions": {}, "scope": "turn"}
        elif method == "item/tool/requestUserInput":
            result = {"answers": {}}
            questions = message.get("params", {}).get("questions", [])
            self.note("模型请求补充信息：" + "；".join(q.get("question", q.get("header", "")) for q in questions))
        else:
            self.send({"id": message["id"], "error": {"code": -32601, "message": "AgentLink does not support this interactive request."}})
            self.note("接口需要暂不支持的交互：" + method)
            return
        self.send({"id": message["id"], "result": result})
        if "Approval" in method:
            self.note("当前节点未追加授权，已拒绝工具的额外权限请求。")

    def capabilities(self, cwd):
        status = runtime_status(self.command)
        result = {"skills": [], "mcp": [], "errors": [],
                  "project_runtime": {k: status[k] for k in ('ready', 'missing', 'checked')}}
        if not status['ready']:
            self.note('项目审查组件缺失：' + ', '.join(status['missing']) + '；目录：' + status['directory'])
        for method, params, target in (
            ("skills/list", {"cwds": [cwd], "forceReload": False}, "skills"),
            ("mcpServerStatus/list", {"limit": 100, "detail": "toolsAndAuthOnly"}, "mcp"),
        ):
            try:
                response = self.call(method, params, timeout=20)
                if target == "skills":
                    for entry in response.get("data", []):
                        result["skills"].extend(
                            {"name": s.get("name", ""), "enabled": s.get("enabled", True),
                             "description": str(s.get("description", ""))[:200]}
                            for s in entry.get("skills", []))
                        result["errors"].extend(str(e.get("message", ""))[:200] for e in entry.get("errors", []))
                else:
                    result["mcp"] = [
                        {"name": s.get("name", ""), "authStatus": s.get("authStatus", "unknown"),
                         "tool_count": len(s.get("tools") or {})}
                        for s in response.get("data", [])
                    ]
            except (RuntimeError, TimeoutError) as error:
                result["errors"].append(str(error))
        return result

    def new_thread(self, settings, cwd, instructions):
        if settings.get('permissions'):
            return self.scoped_thread(settings, cwd, instructions)
        response = self.call("thread/start", {
            "model": settings["model"], "cwd": cwd,
            "sandbox": settings.get("sandbox", "read-only"), "approvalPolicy": "never",
            "developerInstructions": instructions, "ephemeral": False,
        }, timeout=60)
        policy = response.get("sandbox") or {}
        if settings.get("sandbox", "read-only") == "read-only" and policy.get("type") not in ("readOnly", None):
            raise RuntimeError("Codex 返回的权限与只读设置不一致，已停止。")
        return response["thread"]["id"]

    def scoped_thread(self, settings, cwd, instructions, resume_thread=None):
        require_project_runtime(self.command)
        name = settings['permissions']
        # Query effective node config, then disable every configured MCP/plugin.
        # Never let external tools bypass the project filesystem boundary.
        config = self.call('config/read', {'includeLayers': False, 'cwd': cwd}, timeout=30).get('config')
        if not isinstance(config, dict):
            raise RuntimeError('无法核对节点工具配置，未启动项目模型请求。')
        overrides = {'permissions': {name: settings['permission_profile']},
                     'features.apps': False, 'features.multi_agent': False,
                     'web_search': 'disabled', 'hooks': {}, 'features.hooks': False}
        # JSON objects preserve literal server/plugin names. Quoted dotted keys
        # are not TOML syntax here: they create a different, transport-less server.
        for table in ('mcp_servers', 'plugins'):
            entries = config.get(table) or {}
            if not isinstance(entries, dict) or any(not isinstance(v, dict) for v in entries.values()):
                raise RuntimeError('节点工具配置格式无效，未启动项目模型请求。')
            overrides[table] = {key: dict(without_null_fields(value), enabled=False) for key, value in entries.items()}
        params = {
            'model': settings['model'], 'cwd': cwd, 'permissions': name,
            'approvalPolicy': 'never', 'approvalsReviewer': 'user',
            'config': overrides, 'developerInstructions': instructions, 'ephemeral': False,
        }
        if resume_thread:
            params['threadId'] = resume_thread
        response = self.call('thread/resume' if resume_thread else 'thread/start', params, timeout=60)
        if (response.get('activePermissionProfile', {}).get('id') != name
                or response.get('approvalPolicy') != 'never'
                or response.get('approvalsReviewer') != 'user'
                or Path(response.get('cwd', '')).resolve() != Path(cwd).resolve()):
            raise RuntimeError('Codex 未确认项目权限配置；已阻塞，未发送模型请求。')
        if resume_thread and response.get('thread',{}).get('id') != resume_thread:
            raise RuntimeError('恢复会话编号不一致，未发送模型请求。')
        self.note('项目权限配置已确认：' + name)
        return response['thread']['id']

    def begin_steer(self, text):
        if not self.current or not self.current.turn_id or self.current.status != 'running':
            raise RuntimeError('选定节点没有可接收实时输入的运行中请求。')
        turn = self.current.turn_id
        request = self.request('turn/steer', {'threadId': self.current.thread_id,
            'expectedTurnId': turn, 'input': [{'type': 'text', 'text': text}]})
        return request, turn

    def run_turn(self, thread_id, prompt, role, step, settings, changed, pump):
        if self.cleanup_pending:
            raise RuntimeError('执行进程清理未完成，禁止发送新请求。')
        self.last_partial = None
        self.current = TurnView(role, step, thread_id)
        self.changed, self.pump = changed, pump
        self.turn_started_at = self.last_turn_event_at = time.monotonic()
        self.turn_event_count = 0
        cancelled_at = None
        reason = ""
        try:
            turn_params = {
                "threadId": thread_id, "input": [{"type": "text", "text": prompt}],
                "model": settings["model"], "effort": settings.get("effort", "high"),
                "summary": "auto",
            }
            if settings.get('output_schema'):
                turn_params['outputSchema'] = settings['output_schema']
            response = self.call('turn/start', turn_params, timeout=None)
            self.current.turn_id = response["turn"]["id"]
            for method, params in self.pending_turn_events:
                self._feed_current(method, params)
            self.pending_turn_events.clear()
            self.changed(self.current.snapshot())
            while self.current.status not in ("completed", "failed", "interrupted"):
                if cancelled_at is None:
                    try:
                        self.pump()
                    except Cancelled as error:
                        reason = str(error)
                        cancelled_at = time.monotonic()
                        self.request("turn/interrupt", {"threadId": thread_id, "turnId": self.current.turn_id})
                if cancelled_at is not None and time.monotonic() - cancelled_at > 10:
                    self._stop_process()
                    raise Cancelled(reason + " 已终止本机 App Server 及其子进程。")
                self.poll(0.1)
            result = self.current.snapshot()
            if cancelled_at is not None or result["status"] == "interrupted":
                raise Cancelled(reason or "任务已停止。")
            if result["status"] != "completed":
                raise RuntimeError(result["error"] or "Codex 执行失败。")
            if not result["answer"].strip():
                raise RuntimeError("本次调用没有返回回答，事件记录已保留。")
            return result
        except Cancelled:
            # Includes cancellation while turn/start itself was waiting.
            if self.current and not cancelled_at:
                self._stop_process()
            raise
        except Exception as error:
            self.last_partial = self.current.snapshot() if self.current else None
            if self.last_partial:
                self.last_partial.update(status="failed", error=str(error))
            self._stop_process()
            raise
        finally:
            self.current = None
            self.turn_started_at = self.last_turn_event_at = None
            self.pending_turn_events.clear()
            self.pump = lambda: None
            self.changed = lambda value: None

    def _stop_process(self):
        self.cleanup_pending = True
        # Close even when the root process has exited: descendants may remain.
        if self.process_job:
            try:
                self.process_job.close()
            except Exception as error:
                raise RuntimeError('执行进程组清理失败，归属句柄已保留，禁止继续发送请求：' + str(error)) from error
            self.process_job = None
            if self.process:
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    stop_process_tree(self.process)
        else:
            stop_process_tree(self.process)
        self.cleanup_pending = False

    def close(self):
        self._stop_process()
        for reader in self.readers:
            reader.join(timeout=2)
        self.readers.clear()
        if self.process:
            for pipe in (self.process.stdin, self.process.stdout, self.process.stderr):
                if pipe:
                    pipe.close()
        self.process = None
        with self.log_lock:
            if self.log:
                self.log.close()
                self.log = None
