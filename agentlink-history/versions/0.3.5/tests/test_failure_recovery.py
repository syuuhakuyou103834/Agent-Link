"""Fixed failure-recovery baseline; local services and offline model processes."""
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import statistics
import sys
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
from test_system import SystemTests, until
from app.storage import read_json, FileLock
import app.storage as storage

class Counters(ctypes.Structure):
    _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [
        (name, ctypes.c_size_t) for name in ('PeakWorkingSetSize','WorkingSetSize',
        'QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage',
        'QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage')]
kernel = ctypes.WinDLL('kernel32', use_last_error=True)
psapi = ctypes.WinDLL('psapi', use_last_error=True)
kernel.GetCurrentProcess.restype = wintypes.HANDLE
kernel.GetProcessHandleCount.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
def measure(handle):
    memory, handles = Counters(), wintypes.DWORD()
    memory.cb = ctypes.sizeof(memory)
    assert psapi.GetProcessMemoryInfo(handle, ctypes.byref(memory), memory.cb)
    assert kernel.GetProcessHandleCount(handle, ctypes.byref(handles))
    return {'private_bytes': memory.PrivateUsage, 'handles': handles.value}

class FailureRecovery(SystemTests):
    def tearDown(self):
        known = getattr(self, 'known_processes', [])
        super().tearDown()
        self.assertTrue(all(p.poll() is not None for p in known))
        for role in ('A','B'):
            with FileLock(self.shared / 'nodes' / (role + '.lease')):
                pass
        if hasattr(self, 'recovery_result'):
            self.recovery_result['all_known_mock_processes_exited'] = True
            self.recovery_result['role_locks_reacquired_after_disconnect'] = True
            (self.root / 'recovery-result.json').write_text(json.dumps(self.recovery_result, indent=2), encoding='utf-8')

    def test_T07_T11_T12_repeated_failures_then_valid_next_job(self):
        self.known_processes = []
        samples, pairs = [], []
        spec = {'warmup_pairs': 3, 'measured_pairs': 9,
            'fault_order': ['timeout','cancel','publish_failure'] * 4,
            'normal_jobs_after_every_failure': 1,
            'threshold': .20, 'comparison': 'first/last 3 measured pair medians',
            'resource_scope': 'two service threads in harness plus current mock child processes'}
        (self.root / 'recovery-baseline.json').write_text(json.dumps(spec, indent=2), encoding='utf-8')
        for pair, mode in enumerate(spec['fault_order']):
            a = self.nodes['A']
            base_calls = sum(len(self.calls(r)) for r in ('A','B'))
            previous_ids = {p.name for p in (self.shared / 'jobs').iterdir()}
            old_timeout = a.settings.timeout_seconds
            original_publish = storage.atomic_json
            denied = []
            def publish(path, value):
                path = Path(path)
                if (mode == 'publish_failure' and path.parent.parent == self.shared / 'jobs'
                        and path.name == 'turn-000-A.json'):
                    denied.append(str(path))
                    raise PermissionError('injected result publication denial')
                return original_publish(path, value)
            try:
                if mode == 'timeout':
                    a.settings.timeout_seconds = .15
                with patch.object(storage, 'atomic_json', side_effect=publish):
                    a.command('start', topic=('[LONG] ' if mode != 'publish_failure' else '') + mode, rounds=1)
                    until(lambda: len(self.calls('A')) + len(self.calls('B')) == base_calls + 1)
                    if mode == 'cancel':
                        a.command('cancel')
                    until(lambda: all(not n.active and not n.start_pending for n in self.nodes.values()))
            finally:
                a.settings.timeout_seconds = old_timeout
            failed = next(p for p in (self.shared / 'jobs').iterdir() if p.name not in previous_ids)
            expected = 'failed' if mode == 'publish_failure' else 'cancelled'
            self.assertEqual(read_json(failed / 'state.json')['status'], expected)
            self.assertEqual(sum(len(self.calls(r)) for r in ('A','B')) - base_calls, 1)
            if mode == 'publish_failure':
                self.assertTrue(denied)
                self.assertEqual(read_json(a.box.cache(failed.name) / 'turn-000-A.json')['status'], 'completed')
            with FileLock(self.shared / 'discussion.lease'):
                pass
            self.assertTrue(all(not n.sessions for n in self.nodes.values()))
            terminal = (failed / 'state.json').read_bytes()
            prior_ids = {p.name for p in (self.shared / 'jobs').iterdir()}
            a.command('start', topic='valid recovery ' + str(pair), rounds=1)
            until(lambda: all(not n.active and not n.start_pending for n in self.nodes.values()))
            completed = next(p for p in (self.shared / 'jobs').iterdir() if p.name not in prior_ids)
            self.assertEqual(read_json(completed / 'state.json')['status'], 'completed')
            self.assertEqual(sum(len(self.calls(r)) for r in ('A','B')) - base_calls, 4)
            self.assertEqual((failed / 'state.json').read_bytes(), terminal)
            self.assertEqual(len(list(completed.glob('turn-*.json'))), 3)
            current = [n.client.process for n in self.nodes.values()]
            for process in current:
                if process not in self.known_processes:
                    self.known_processes.append(process)
            self.assertTrue(all(p in current or p.poll() is not None for p in self.known_processes))
            with FileLock(self.shared / 'discussion.lease'):
                pass
            # Test event capture is not a product cache; clear it before measurement.
            for events in self.events.values():
                events.clear()
            measured = [measure(kernel.GetCurrentProcess())] + [measure(p._handle) for p in current]
            sample = {'pair': pair, **{k: sum(m[k] for m in measured) for k in measured[0]}}
            samples.append(sample)
            pairs.append({'pair':pair, 'fault':mode, 'failed_job':failed.name, 'failed_status':expected,
                          'next_job':completed.name, 'requests':4})
            (self.root / 'recovery-samples.json').write_text(json.dumps(samples, indent=2), encoding='utf-8')
        growth = {}
        for key in ('private_bytes','handles'):
            first = statistics.median(s[key] for s in samples[3:6])
            last = statistics.median(s[key] for s in samples[-3:])
            growth[key] = {'first':first, 'last':last, 'growth':last/first-1}
            self.assertLessEqual(growth[key]['growth'], .20, growth)
        self.recovery_result = {'status':'PASS', 'spec':spec, 'pairs':pairs,
                                'requests':48, 'growth':growth}

if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite([
        FailureRecovery('test_T07_T11_T12_repeated_failures_then_valid_next_job')]))
    sys.exit(not result.wasSuccessful())
