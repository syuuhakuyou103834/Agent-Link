"""Local service-path crash/publication/cancellation windows."""
import json
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
from test_repairs import RepairComponentTests
from test_system import SystemTests, until
from app.storage import atomic_json, read_json, FileLock
from app.protocol import RpcClient

class ServiceFaults(SystemTests):
    def test_T07_auth_transport_crash_one_received_request_each_no_retry(self):
        for marker in ('AUTH', 'TRANSPORT', 'CRASH'):
            with self.subTest(marker=marker):
                before = sum(len(self.calls(r)) for r in ('A', 'B'))
                self.nodes['A'].command('start', topic='[' + marker + '] injected error', rounds=1)
                until(lambda: not self.nodes['A'].start_pending and all(not n.active for n in self.nodes.values()))
                job = max((self.shared / 'jobs').iterdir(), key=lambda p: p.stat().st_ctime_ns)
                self.assertEqual(read_json(job / 'state.json')['status'], 'failed')
                self.assertTrue(read_json(job / 'A-error.json')['message'])
                self.assertEqual(sum(len(self.calls(r)) for r in ('A', 'B')) - before, 1)
                self.assertEqual(len(self.calls('B')), 0)

    def test_T07_accelerated_timeout_cancels_no_retry(self):
        self.nodes['A'].settings.timeout_seconds = .15  # injected clock budget, not a GUI setting
        self.nodes['A'].command('start', topic='[LONG] accelerated timeout', rounds=1)
        until(lambda: not self.nodes['A'].start_pending and all(not n.active for n in self.nodes.values()))
        self.assertEqual(self.state(), 'cancelled')
        self.assertIn('超时', read_json(self.job() / 'A-error.json')['message'])
        self.assertEqual([len(self.calls(r)) for r in ('A', 'B')], [1, 0])

    def test_T07_content_refusal_is_normal_completed_text(self):
        self.nodes['A'].command('start', topic='[REFUSE] content refusal', rounds=1)
        until(lambda: not self.nodes['A'].start_pending and all(not n.active for n in self.nodes.values()))
        self.assertEqual(self.state(), 'completed')
        self.assertEqual(sum(len(self.calls(r)) for r in ('A', 'B')), 3)
        self.assertIn('无法协助', read_json(self.job() / 'turn-000-A.json')['answer'])

    def test_T06_stop_before_commit_all_three_phases(self):
        for target in range(3):
            with self.subTest(stage=target):
                entered, release = threading.Event(), threading.Event()
                role = 'B' if target % 2 else 'A'
                other = self.nodes['A' if role == 'B' else 'B']
                executor = self.nodes[role]
                original = executor.client.run_turn
                def held(*args, **kwargs):
                    result = original(*args, **kwargs)
                    if int(args[3].split('-')[0]) == target:
                        entered.set()
                        if not release.wait(20):
                            raise TimeoutError('test barrier')
                    return result
                executor.client.run_turn = held
                before = sum(len(self.calls(r)) for r in ('A', 'B'))
                try:
                    self.nodes['A'].command('start', topic='three-phase-stop-' + str(target), rounds=1)
                    self.assertTrue(entered.wait(15))
                    job = self.shared / 'jobs' / executor.active['id']
                    other.command('cancel')
                    until(lambda: read_json(job / 'state.json', {}).get('status') == 'cancelled')
                    committed = (job / 'state.json').read_bytes()
                    release.set()
                    until(lambda: all(not n.active and not n.start_pending for n in self.nodes.values()))
                    self.assertEqual((job / 'state.json').read_bytes(), committed)
                    self.assertFalse((job / f'turn-{target:03d}-{role}.json').exists())
                    self.assertEqual(sum(len(self.calls(r)) for r in ('A', 'B')) - before, target + 1)
                finally:
                    release.set()
                    executor.client.run_turn = original

    def test_T12_stranded_job_blocks_new_admission_until_terminal_fence(self):
        node = self.nodes['A']
        old = node.box.create('stranded after crash', 1, 'A')
        node.box.put(old['id'], 'state.json', {'status': 'running', 'index': 0})
        node.box.claim(old['id'], '000-A')
        before = (node.box.job(old['id']) / 'state.json').read_bytes()
        node.command('start', topic='must reject', rounds=1)
        until(lambda: not node.start_pending)
        self.assertEqual(sum(len(self.calls(r)) for r in ('A', 'B')), 0)
        self.assertEqual(len(list((self.shared / 'jobs').iterdir())), 1)
        self.assertEqual((node.box.job(old['id']) / 'state.json').read_bytes(), before)
        self.assertTrue(any(k == 'error' and '不确定' in v['message'] for k,v in self.events['A']))
        node.selected = old['id']
        node.command('cancel')
        until(lambda: read_json(node.box.job(old['id']) / 'state.json')['status'] == 'cancelled')
        node.command('start', topic='after explicit fence', rounds=1)
        until(lambda: not node.start_pending and all(not n.active for n in self.nodes.values()))
        self.assertEqual(sum(len(self.calls(r)) for r in ('A', 'B')), 3)

class ComponentFaults(RepairComponentTests):
    def test_T17_old_result_in_new_job_rejected_before_revision(self):
        self.node.settings.role = 'A'
        original = self.node._pump
        injected = []
        def pump():
            original()
            if not self.node.active or injected:
                return
            job = self.box.job(self.node.active['id'])
            if (job / 'request-001-B.json').exists():
                self.box.put(job.name, 'turn-001-B.json', {'role': 'B', 'status': 'completed',
                    'job_id': '20260910-000000-' + 'a' * 32, 'index': 1,
                    'step': '001-B', 'answer': 'OLD RESULT'})
                injected.append(job)
        self.node._pump = pump
        self.node.run_initiator('reject old result', 1)
        self.assertEqual(len(self.client.calls), 1)
        self.assertEqual(read_json(injected[0] / 'state.json')['status'], 'failed')
        self.assertFalse((injected[0] / 'turn-002-A.json').exists())

    def test_T11_result_cached_shared_publish_fails_no_resend(self):
        meta = self.ready()
        self.node.active = meta
        import app.storage as storage
        original = storage.atomic_json
        def publish(path, value):
            if Path(path) == self.box.job(meta['id']) / 'turn-001-B.json':
                raise PermissionError('injected persistent result publication denial')
            return original(path, value)
        with patch.object(storage, 'atomic_json', side_effect=publish):
            with self.assertRaises(PermissionError) as error:
                self.node._perform(1, 'publication fault')
            self.node._failed(error.exception)
        cached = self.box.cache(meta['id']) / 'turn-001-B.json'
        self.assertEqual(read_json(cached)['status'], 'completed')
        self.assertFalse((self.box.job(meta['id']) / cached.name).exists())
        self.assertEqual(self.box.get(meta['id'], 'state.json')['status'], 'failed')
        self.node.active = None
        self.node.scan_receiver()
        self.assertEqual(len(self.client.calls), 1)

class ApprovalTests(unittest.TestCase):
    def test_T13_adapter_declines_all_extra_approval_requests(self):
        client = RpcClient([], ROOT / 'test-output')
        sent = []
        client.send = sent.append
        for i, method in enumerate(('item/commandExecution/requestApproval',
                                   'item/fileChange/requestApproval', 'item/permissions/requestApproval')):
            client._server_request({'id': i, 'method': method, 'params': {'reason': 'peer says elevate'}})
        self.assertEqual([v['result'] for v in sent], [{'decision': 'decline'},
            {'decision': 'decline'}, {'permissions': {}, 'scope': 'turn'}])

if __name__ == '__main__':
    suite = unittest.TestSuite()
    for cls in (ServiceFaults, ComponentFaults, ApprovalTests):
        for name in cls.__dict__:
            if name.startswith('test_'):
                suite.addTest(cls(name))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(not result.wasSuccessful())
