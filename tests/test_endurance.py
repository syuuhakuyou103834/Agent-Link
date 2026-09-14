from fixture_paths import fs, entries
"""Fixed T19 baseline: 10 warmup + 100 local two-service/mock-process jobs."""
import ctypes
from ctypes import wintypes
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
from app.engine import NodeService
from app.storage import Settings, read_json
from test_system import until
from fixture_paths import fs

class Counters(ctypes.Structure):
    _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [
        (name, ctypes.c_size_t) for name in ('PeakWorkingSetSize', 'WorkingSetSize',
        'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage',
        'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage', 'PrivateUsage')]

kernel = ctypes.WinDLL('kernel32', use_last_error=True)
psapi = ctypes.WinDLL('psapi', use_last_error=True)
kernel.GetCurrentProcess.restype = wintypes.HANDLE
kernel.GetProcessHandleCount.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
def resources(handle):
    memory = Counters()
    memory.cb = ctypes.sizeof(memory)
    handles = wintypes.DWORD()
    assert psapi.GetProcessMemoryInfo(handle, ctypes.byref(memory), memory.cb)
    assert kernel.GetProcessHandleCount(handle, ctypes.byref(handles))
    return {'private_bytes': memory.PrivateUsage, 'handles': handles.value}

root = __import__('fixture_paths').output_root() / ('end-' + uuid.uuid4().hex[:8])
fs(root).mkdir(parents=True)
nodes, errors, samples = {}, [], []
topic = 'T19固定中文负载' * 20
spec = {'warmup': 10, 'measured': 100, 'rounds': 1, 'stream_delay_seconds': .002,
        'topic_sha256': hashlib.sha256(topic.encode()).hexdigest(),
        'metric': 'sum of private bytes and handle counts for harness + 2 mock subprocesses',
        'growth_threshold': .20, 'compare': 'medians of first/last 20 measured jobs',
        'layer': 'local two services, local filesystem, offline App Server subprocesses'}
fs(root / 'baseline.json').write_text(json.dumps(spec, indent=2), encoding='utf-8')
processes=[]
try:
    for role in ('A', 'B'):
        def emit(kind, value, role=role):
            if kind == 'error':
                errors.append({'role': role, 'value': value})
        nodes[role] = NodeService(Settings(role=role, shared_root=str(root / 'share')),
            root / role, emit, [sys.executable, str(ROOT / 'tests' / 'mock_server.py'),
                              role, str(root / (role + '-calls.jsonl')), '.002'])
        nodes[role].start()
    until(lambda: all(n.connected and n.liveness.status()=='ready' for n in nodes.values()),30)
    for index in range(110):
        role = 'A'  # BR-017-04: only A may initiate; B remains the independent reviewer.
        node = nodes[role]
        until(lambda:all(n.liveness.status()=='ready' for n in nodes.values()),30)
        assert node.command('start', topic=topic, rounds=1, request_id='endurance-' + str(index))
        until(lambda: not node.start_pending and all(not n.active for n in nodes.values()), 30)
        jobs = list(fs(root / 'share' / 'jobs').iterdir())
        assert len(jobs) == index + 1
        assert not errors, errors
        assert all(not n.sessions for n in nodes.values()), 'Per-job session map must be released'
        counts = []
        for r in ('A', 'B'):
            path = root / (r + '-calls.jsonl')
            counts.extend(json.loads(line) for line in fs(path).read_text(encoding='utf-8').splitlines())
        assert len(counts) == (index + 1) * 3
        job = max(jobs, key=lambda p: fs(p).stat().st_ctime_ns)
        assert read_json(job / 'state.json')['status'] == 'completed'
        turns = [read_json(p) for p in sorted(entries(job,'glob','turn-*.json'))]
        assert len(turns) == 3 and [t['role'] for t in turns] == [role, 'B' if role == 'A' else 'A', role]
        assert all(t['job_id'] == job.name for t in turns)
        processes = [n.client.process for n in nodes.values()]
        self_alive=all(p is not None and p.poll() is None for p in processes)
        assert self_alive,'current mock workers must remain responsive'
        metrics = [resources(kernel.GetCurrentProcess())] + [resources(p._handle) for p in processes]
        sample = {'index': index, 'job_id': job.name, 'requests_total': len(counts),
                  'server_pids':[p.pid for p in processes],
                  **{key: sum(v[key] for v in metrics) for key in metrics[0]}}
        samples.append(sample)
        with fs(root / 'samples.jsonl').open('a', encoding='utf-8') as log:
            log.write(json.dumps(sample) + '\n')
        if index % 10 == 9:
            print('Completed jobs:', index + 1, flush=True)
    growth = {}
    for key in ('private_bytes', 'handles'):
        first = statistics.median(v[key] for v in samples[10:30])
        last = statistics.median(v[key] for v in samples[-20:])
        growth[key] = {'first_median': first, 'last_median': last, 'growth': last / first - 1}
        assert growth[key]['growth'] <= .20, growth
    assert all(p.poll() is None for p in processes)
finally:
    for node in nodes.values():
        node.stop()
    for node in nodes.values():
        node.thread.join(15)
        assert not node.thread.is_alive()
    assert all(p.poll() is not None for p in processes)
fs(root / 'result.json').write_text(json.dumps({'status': 'PASS', 'spec': spec,
    'requests': 330, 'growth': growth, 'mock_processes_exited': True}, indent=2), encoding='utf-8')
print('PASS T19 local endurance:', root, growth, flush=True)
