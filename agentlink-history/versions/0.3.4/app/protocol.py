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
        self.messages = queue.Queue()
        self.responses = {}
        self.counter = 0
        self.current = None
        self.pump = lambda: None
        self.changed = lambda value: None
        self.log = None
        self.log_lock = threading.Lock()
        self.readers = []
        self.turn_started_at = None
        self.last_turn_event_at = None
        self.turn_event_count = 0

    def start(self):
        if self.process and self.process.poll() is None:
            return
        self.close()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.messages = queue.Queue()
        self.responses = {}
        self.log = open(self.data_dir / ("app-server-" + time.strftime("%Y%m%d-%H%M%S") + ".jsonl"), "ab")
        self.process = subprocess.Popen(
            self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=str(self.data_dir), creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        self.readers = [threading.Thread(target=self._reader, args=(pipe, err), daemon=True)
                        for pipe, err in ((self.process.stdout, False), (self.process.stderr, True))]
        for reader in self.readers:
            reader.start()
        self.call("initialize", {"clientInfo": {"name": "agentlink_gui", "title": "AgentLink GUI", "version": __version__},
                                 "capabilities": {"experimentalApi": False}}, timeout=40)
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
            if (params.get('threadId', self.current.thread_id) == self.current.thread_id
                    and (not self.current.turn_id or not params.get('turnId')
                         or params['turnId'] == self.current.turn_id)):
                self.last_turn_event_at = time.monotonic()
                self.turn_event_count += 1
            self.current.feed(method, params)
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
        result = {"skills": [], "mcp": [], "errors": []}
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
        response = self.call("thread/start", {
            "model": settings["model"], "cwd": cwd,
            "sandbox": settings.get("sandbox", "read-only"), "approvalPolicy": "never",
            "developerInstructions": instructions, "ephemeral": False,
        }, timeout=60)
        policy = response.get("sandbox") or {}
        if settings.get("sandbox", "read-only") == "read-only" and policy.get("type") not in ("readOnly", None):
            raise RuntimeError("Codex 返回的权限与只读设置不一致，已停止。")
        return response["thread"]["id"]

    def run_turn(self, thread_id, prompt, role, step, settings, changed, pump):
        self.current = TurnView(role, step, thread_id)
        self.changed, self.pump = changed, pump
        self.turn_started_at = self.last_turn_event_at = time.monotonic()
        self.turn_event_count = 0
        cancelled_at = None
        reason = ""
        try:
            response = self.call("turn/start", {
                "threadId": thread_id, "input": [{"type": "text", "text": prompt}],
                "model": settings["model"], "effort": settings.get("effort", "high"),
                "summary": "auto",
            }, timeout=None)
            self.current.turn_id = response["turn"]["id"]
            while self.current.status not in ("completed", "failed", "interrupted"):
                if cancelled_at is None:
                    try:
                        self.pump()
                    except Cancelled as error:
                        reason = str(error)
                        cancelled_at = time.monotonic()
                        self.request("turn/interrupt", {"threadId": thread_id, "turnId": self.current.turn_id})
                if cancelled_at is not None and time.monotonic() - cancelled_at > 10:
                    stop_process_tree(self.process)
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
                stop_process_tree(self.process)
            raise
        except Exception:
            stop_process_tree(self.process)
            raise
        finally:
            self.current = None
            self.turn_started_at = self.last_turn_event_at = None
            self.pump = lambda: None
            self.changed = lambda value: None

    def close(self):
        stop_process_tree(self.process)
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
