"""Small atomic SMB mailbox. Data files never become executable commands."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from contextlib import contextmanager
import json
import os
import logging
import math
from pathlib import Path
import random
import re
import socket
import time
import uuid

DEFAULT_SHARE = r"\\192.168.1.108\shared\AgentLink-GUI-v1"
JOB_PATTERN = re.compile(r"^\d{8}-\d{6}-[a-f0-9]{32}$")
TERMINAL_STATES = frozenset(('completed', 'failed', 'cancelled'))
LONG_TASK_FEATURE = 'unlimited-wait-v1'
IO_RETRY_SECONDS = 1.5
log = logging.getLogger('agentlink.storage')

if os.name == 'nt':
    import ctypes
    from ctypes import wintypes
    import msvcrt
    _kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    _create_file = _kernel.CreateFileW
    _create_file.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                            wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    _create_file.restype = wintypes.HANDLE
    _close_handle = _kernel.CloseHandle
    _close_handle.argtypes = [wintypes.HANDLE]
    _close_handle.restype = wintypes.BOOL


def io_path(path):
    """Extended Windows spelling for I/O only; never changes access rights."""
    value = str(Path(path).absolute())
    if os.name == 'nt' and len(value) >= 220 and not value.startswith('\\\\?\\'):
        value = ('\\\\?\\UNC\\' + value[2:]) if value.startswith('\\\\') else ('\\\\?\\' + value)
    return Path(value)


def plain_path(path):
    """Normalize equivalent Windows spellings without changing the target."""
    value = str(path)
    if os.name == 'nt':
        if value.lower().startswith('\\\\?\\unc\\'):
            value = '\\\\' + value[8:]
        elif re.match(r'^\\\\\?\\[a-zA-Z]:\\', value):
            value = value[4:]
    return Path(value)


def canonical_path(path):
    return plain_path(io_path(plain_path(path)).resolve())


def _open_read(path):
    """Readers permit a writer's atomic rename, including over Windows SMB.

    Python's normal CRT open shares read/write but not delete access. The latter
    is needed for os.replace; without it either side can receive EACCES.
    This changes handle sharing, never ACLs or the requested READ permission.
    """
    if os.name != 'nt':
        return Path(path).open('rb')
    name = os.path.abspath(path)
    if not name.startswith('\\\\?\\'):
        name = ('\\\\?\\UNC\\' + name[2:]) if name.startswith('\\\\') else ('\\\\?\\' + name)
    handle = _create_file(name, 0x80000000, 0x1 | 0x2 | 0x4, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        error = ctypes.WinError(ctypes.get_last_error())
        error.filename = str(path)
        raise error
    try:
        descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except Exception:
        _close_handle(handle)
        raise
    try:
        return os.fdopen(descriptor, 'rb')
    except Exception:
        os.close(descriptor)
        raise


def _retry_io(action, *, timeout=None, max_delay=.15, initial_delay=.015):
    deadline = time.monotonic() + (IO_RETRY_SECONDS if timeout is None else timeout)
    delay = initial_delay
    while True:
        try:
            return action()
        except OSError as error:
            # WinError 5 can mean delete-pending OR a real ACL denial. Retry
            # briefly, but preserve the error if it persists. Never return {}.
            transient = isinstance(error, (PermissionError, BlockingIOError)) or getattr(error, 'winerror', None) in (5, 32, 33)
            remaining = deadline - time.monotonic()
            if not transient or remaining <= 0:
                raise
            time.sleep(min(remaining, delay * random.uniform(.8, 1.2)))
            delay = min(delay * 1.8, max_delay)


@contextmanager
def _json_guard(path):
    """Serialize a JSON read/replace through a stable SMB byte-range lock.

    Keep the sidecar on disk: unlinking it would let contenders lock different
    inodes. The OS releases the range on close/process exit. This is distinct
    from a job's permanent .claim; it never invokes or retries a model call.
    """
    lock_path = path.with_name('.' + path.name + '.io.lock')
    with _retry_io(lambda: io_path(lock_path).open('a+b')) as handle:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b'0')
            handle.flush()
        def lock():
            handle.seek(0)
            try:
                if os.name == 'nt':
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                error.filename = str(lock_path)
                raise
        # Short jitter avoids one fast poller repeatedly beating a reader whose
        # exponential retry has backed off too far. Locks have a bounded wait.
        _retry_io(lock, timeout=5, max_delay=.02, initial_delay=.004)
        yield


def now():
    return time.time()


def read_json(path, default=None, limit=8 * 1024 * 1024):
    path = Path(path)
    def read_bytes():
        with _json_guard(path):
            with _open_read(path) as handle:
                # Heartbeats are tiny. read(limit + 1) allocated an 8 MiB
                # temporary buffer per poll, regardless of actual file size.
                chunks, remaining = [], limit + 1
                while remaining:
                    chunk = handle.read(min(64 * 1024, remaining))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    remaining -= len(chunk)
                return b''.join(chunks)
    try:
        data = _retry_io(read_bytes)
    except FileNotFoundError:
        return default
    if len(data) > limit:
        raise ValueError("消息过大：" + path.name)
    return json.loads(data.decode("utf-8-sig"))


def atomic_json(path, value):
    path = Path(path)
    _retry_io(lambda: io_path(path.parent).mkdir(parents=True, exist_ok=True))
    with _json_guard(path):
        _publish_json(path, value)


def _publish_json(path, value):
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".partial")
    payload = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")
    created = False
    published = False
    try:
        # Read+write is recommended by Windows for a new network file. The
        # unique temp is never observed as a published JSON document.
        with _retry_io(lambda: io_path(temp).open('x+b')) as handle:
            created = True
            handle.write(payload)
            handle.flush()
        _retry_io(lambda: os.replace(io_path(temp), io_path(path)))
        published = True
    finally:
        if created and not published:
            try:
                _retry_io(lambda: io_path(temp).unlink(missing_ok=True))
            except OSError:
                log.warning('Unable to remove unpublished temp file: %s', temp, exc_info=True)


def new_job_id():
    return time.strftime("%Y%m%d-%H%M%S", time.gmtime()) + "-" + uuid.uuid4().hex


class FileLock:
    def __init__(self, path):
        self.path = Path(path)
        self.handle = None

    def acquire(self):
        io_path(self.path.parent).mkdir(parents=True, exist_ok=True)
        handle = io_path(self.path).open("a+b")
        try:
            handle.seek(0, 2)
            if not handle.tell():
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            raise RuntimeError("该节点已由另一个 AgentLink 窗口占用。")
        self.handle = handle
        return self

    def close(self):
        if self.handle:
            self.handle.close()
            self.handle = None

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *args):
        self.close()


def default_data_dir():
    return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "AgentLinkGUI"


def managed_codex_candidates():
    base = Path(os.environ.get("LOCALAPPDATA", "")) / "OpenAI" / "Codex" / "bin"
    choices = sorted((p for p in base.glob("*/codex.exe") if p.is_file()),
                     key=lambda p: p.stat().st_mtime, reverse=True) if base.exists() else []
    return base, choices


def resolve_codex(configured):
    """Migrate only the desktop's legacy executable or a removed managed version."""
    base, choices = managed_codex_candidates()
    if configured:
        path = Path(configured)
        legacy = path.resolve() == (base / 'codex.exe').resolve()
        removed_managed = (not path.exists() and path.name.lower() == 'codex.exe'
                           and path.parent.parent.resolve() == base.resolve())
        if choices and (legacy or removed_managed):
            return str(choices[0])
        return configured
    return find_codex()


def find_codex():
    import shutil
    base, choices = managed_codex_candidates()
    if choices:
        return str(choices[0])
    return shutil.which("codex.exe") or (str(base / 'codex.exe') if (base / 'codex.exe').is_file() else "")


@dataclass
class Settings:
    role: str = "A"
    shared_root: str = DEFAULT_SHARE
    codex: str = ""
    model: str = "gpt-6-astra"
    effort: str = "high"
    workspace: str = ""
    sandbox: str = "read-only"
    tools: str = "configured"
    timeout_seconds: int = 0  # Legacy settings are migrated to unlimited task waiting.
    auto_connect: bool = True

    @classmethod
    def load(cls, data_dir):
        path = Path(data_dir) / "settings.json"
        raw = read_json(path, {}) or {}
        valid = {name: value for name, value in raw.items() if name in cls.__dataclass_fields__}
        settings = cls(**valid)
        if not raw:
            settings.role = "B" if socket.gethostname().upper() == "WILLDESKTOP" else "A"
        settings.codex = resolve_codex(settings.codex)
        settings.validate()
        return settings

    def validate(self):
        if self.role not in ("A", "B"):
            raise ValueError("节点角色必须是 A 或 B")
        if self.sandbox not in ("read-only", "workspace-write"):
            raise ValueError("仅支持只读或项目读写沙盒。")
        if self.tools not in ("configured", "discussion"):
            raise ValueError("工具模式无效")
        if not isinstance(self.shared_root, str) or not self.shared_root:
            raise ValueError("请选择共享目录")
        self.timeout_seconds = 0

    def save(self, data_dir):
        self.validate()
        atomic_json(Path(data_dir) / "settings.json", asdict(self))


class Mailbox:
    def __init__(self, shared_root, local_root):
        self.root = Path(shared_root)
        self.local = Path(local_root)

    def connect(self):
        io_path(self.root / "jobs").mkdir(parents=True, exist_ok=True)
        io_path(self.root / "nodes").mkdir(parents=True, exist_ok=True)
        io_path(self.local).mkdir(parents=True, exist_ok=True)

    def job(self, job_id):
        if not JOB_PATTERN.fullmatch(job_id):
            raise ValueError("任务编号无效")
        return self.root / "jobs" / job_id

    def cache(self, job_id):
        if not JOB_PATTERN.fullmatch(job_id):
            raise ValueError("任务编号无效")
        result = self.local / "runs" / job_id
        io_path(result).mkdir(parents=True, exist_ok=True)
        return result

    def create(self, topic, rounds, initiator="A", context=None, unlimited=False):
        if not isinstance(topic, str) or not topic.strip() or len(topic) > 24000:
            raise ValueError("议题应为 1 到 24000 个字符")
        if type(rounds) is not int or not 1 <= rounds <= 8:
            raise ValueError("评审轮数应为 1 到 8")
        job_id = new_job_id()
        meta = {"protocol": 1, "id": job_id, "topic": topic, "rounds": rounds,
                "created": now(), "expires": now() + (1 + 2 * rounds) * 1800, "initiator": initiator}
        if unlimited:
            meta.update(protocol=2, expires=None, wait_policy='unlimited')
        if context is not None:
            from .context import validate_context, context_hash
            validate_context(context)
            meta['context'] = {'schema': 1, 'parent_job_id': context['discussions'][-1]['job_id'],
                               'sha256': context_hash(context), 'discussion_count': len(context['discussions'])}
        io_path(self.job(job_id)).mkdir(parents=True, exist_ok=False)
        if context is not None:
            self.put(job_id, 'context.json', context)
        self.put(job_id, "meta.json", meta)
        self.put(job_id, "control.json", {"paused": False, "cancelled": False, "notes": []})
        return meta

    def put(self, job_id, filename, value):
        if Path(filename).name != filename:
            raise ValueError("消息文件名无效")
        atomic_json(self.cache(job_id) / filename, value)
        atomic_json(self.job(job_id) / filename, value)

    def get(self, job_id, filename, default=None):
        if Path(filename).name != filename:
            raise ValueError("消息文件名无效")
        value = read_json(self.job(job_id) / filename, default)
        if value is not default:
            cached = self.cache(job_id) / filename
            if read_json(cached) != value:
                atomic_json(cached, value)
        return value

    def claim(self, job_id, step):
        if not re.fullmatch(r"\d{3}-[AB]", step):
            raise ValueError("步骤编号无效")
        try:
            with io_path(self.job(job_id) / (step + ".claim")).open("xb") as handle:
                handle.write(json.dumps({"host": socket.gethostname(), "pid": os.getpid(), "time": now()}).encode("utf-8"))
            return True
        except FileExistsError:
            return False

    @contextmanager
    def lifecycle(self, job_id):
        """Serialize control, terminal state and result commits across nodes."""
        with _json_guard(self.job(job_id) / 'lifecycle'):
            yield

    def ensure_open(self, job_id):
        from .protocol import Cancelled
        state = self.get(job_id, 'state.json', {}) or {}
        control = self.get(job_id, 'control.json', {}) or {}
        if state.get('status') in TERMINAL_STATES or control.get('cancelled'):
            raise Cancelled('讨论已结束，拒绝迟到结果或后续执行：' + job_id)

    def jobs(self):
        path = self.root / "jobs"
        return sorted((p for p in path.iterdir() if p.is_dir() and JOB_PATTERN.fullmatch(p.name)), reverse=True)[:200]

    def validate_meta(self, meta, job_id):
        if (not isinstance(meta, dict) or type(meta.get("protocol")) is not int
                or meta["protocol"] not in (1, 2) or meta.get("id") != job_id):
            raise ValueError("不兼容的任务记录")
        if not isinstance(meta.get("topic"), str) or not meta['topic'].strip() or len(meta["topic"]) > 24000:
            raise ValueError("议题内容无效")
        if type(meta.get("rounds")) is not int or not 1 <= meta["rounds"] <= 8:
            raise ValueError("轮数无效")
        if meta.get("initiator") not in ("A", "B"):
            raise ValueError("发起节点无效")
        if meta.get('mode', 'text') not in ('text', 'code'):
            raise ValueError('讨论模式无效')
        if meta.get('mode') == 'code':
            from .projects import project_id
            project_id(meta.get('project', {}).get('id'))
            if (meta['protocol'] != 2 or meta['rounds'] > 3 or type(meta.get('budget')) is not int
                    or meta['budget'] != 2 * meta['rounds'] + 1):
                raise ValueError('项目审查协议或调用预算无效')
        expires = meta.get('expires')
        if meta['protocol'] == 2:
            if 'expires' not in meta or expires is not None or meta.get('wait_policy') != 'unlimited':
                raise ValueError('无时限任务记录无效')
            return
        if type(expires) not in (int, float) or not math.isfinite(expires):
            raise ValueError('任务有效时间必须是有限数值')
        if expires < now():
            raise ValueError("任务已过期")

    def validate_turn(self, view, job_id, index, role):
        if (not isinstance(view, dict) or view.get('job_id') != job_id
                or type(view.get('index')) is not int or view['index'] != index
                or view.get('step') != f'{index:03d}-{role}' or view.get('role') != role
                or view.get('status') != 'completed' or not isinstance(view.get('answer'), str)
                or not view['answer'].strip()):
            raise ValueError('对方结果的场次、步骤或内容无效，拒绝继续执行。')


def turn_title(index):
    if index == 0:
        return "初稿"
    return "第 %d 轮%s" % ((index + 1) // 2, "评审" if index % 2 else "修订")


def report_text(meta, turns, context=None):
    parts = ["AgentLink 讨论记录", "", "议题：", meta["topic"], ""]
    if meta.get('context'):
        parts += ['承接来源：' + meta['context']['parent_job_id'],
                  '上下文 SHA-256：' + meta['context']['sha256'], '']
        if context:
            from .context import prompt_context
            parts += [prompt_context(context), '']
    for turn in turns:
        title = {'implement': '实施并交付源码', 'review': '独立审查', 'summary': '只读总结'}.get(turn.get('phase'), turn_title(turn['index']))
        parts += [turn["role"] + " · " + title, turn.get("answer", ""), ""]
        if turn.get('artifact'):
            parts += ['源码 SHA-256：' + turn['artifact']['manifest_sha256'], '']
    parts += ["Codex 本机任务："]
    for role in ("A", "B"):
        sessions = sorted({t.get("thread_id", "") for t in turns if t["role"] == role and t.get("thread_id")})
        parts += [role + ": " + ", ".join(sessions)]
    return "\n".join(parts)


def import_legacy(path):
    path = Path(path)
    if path.is_dir():
        path = path / "discussion.txt"
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("旧版记录过大")
    text = path.read_text(encoding="utf-8-sig")
    keys = ["TOPIC:", "A PROPOSAL:", "B REVIEW:", "A FINAL:", "CODEX LOCAL TASKS:"]
    segments = {}
    for i, key in enumerate(keys):
        start = text.find(key)
        if start >= 0:
            start += len(key)
            ends = [text.find(next_key, start) for next_key in keys[i + 1:] if text.find(next_key, start) >= 0]
            segments[key] = text[start:min(ends) if ends else len(text)].strip()
    turns = [{"role": role, "index": i, "step": f"{i:03d}-{role}", "status": "completed",
              "answer": segments.get(key, ""), "blocks": [{"text": segments.get(key, ""), "phase": "final_answer"}],
              "summary": "", "tools": [], "thread_id": ""}
             for i, (role, key) in enumerate([("A", keys[1]), ("B", keys[2]), ("A", keys[3])])]
    return {"meta": {"id": "legacy:" + str(path), "topic": segments.get(keys[0], path.parent.name),
                     "rounds": 1, "created": path.stat().st_mtime},
            "turns": turns, "status": "completed", "legacy_path": str(path), "report": text}
