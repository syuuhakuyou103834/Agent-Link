import json
from pathlib import Path
import sys
import time
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.engine import NodeService
from app.storage import Settings, read_json, FileLock, import_legacy


def until(predicate, seconds=25):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(.04)
    raise AssertionError('Timed out waiting for expected state')


class SystemTests(unittest.TestCase):
    def setUp(self):
        self.root = ROOT / 'test-output' / uuid.uuid4().hex
        self.root.mkdir(parents=True)
        self.nodes, self.events = {}, {'A': [], 'B': []}
        for role in ('A', 'B'):
            config = Settings(role=role, shared_root=str(self.root / 'share'), auto_connect=True)
            command = [sys.executable, str(ROOT / 'tests' / 'mock_server.py'), role, str(self.root / (role + '-calls.jsonl'))]
            self.nodes[role] = NodeService(config, self.root / role,
                lambda kind, value, r=role: self.events[r].append((kind, value)), command)
            self.nodes[role].start()
        until(lambda: all(n.connected for n in self.nodes.values()))

    def tearDown(self):
        for node in self.nodes.values():
            node.stop()
        for node in self.nodes.values():
            node.thread.join(15)
            self.assertFalse(node.thread.is_alive(), 'Node must close cleanly')

    def job(self):
        paths = list((self.root / 'share' / 'jobs').iterdir())
        return paths[-1] if paths else None

    def calls(self, role):
        path = self.root / (role + '-calls.jsonl')
        return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()] if path.exists() else []

    def state(self):
        path = self.job()
        return (read_json(path / 'state.json', {}) or {}).get('status') if path else None

    def test_A_two_rounds_unicode_stream_history(self):
        self.nodes['A'].command('start', topic='中文议题：多轮协作与温度 23℃', rounds=2)
        until(lambda: self.state() == 'completed')
        until(lambda: all(not n.active for n in self.nodes.values()))
        self.assertEqual([len(self.calls(r)) for r in ('A', 'B')], [3, 2])
        for role in ('A', 'B'):
            self.assertEqual(len({c['thread'] for c in self.calls(role)}), 1)
            until(lambda r=role: (self.root / r / 'runs' / self.job().name / 'discussion.txt').exists())
            record = (self.root / role / 'runs' / self.job().name / 'discussion.txt').read_text(encoding='utf-8')
            self.assertIn('温度 23℃', record)
        self.assertIn('中文传递正确', self.calls('B')[0]['prompt'])
        self.assertTrue(any(k == 'live' and v['status'] == 'running' and v.get('answer') for k, v in self.events['A']))
        self.assertEqual(len(list(self.job().glob('turn-*.json'))), 5)
        time.sleep(1)
        self.assertEqual(len(self.calls('B')), 2, 'No duplicate automatic replay')

    def test_B_initiates_A_pauses_and_resumes(self):
        self.nodes['B'].command('start', topic='[LONG] B 发起，A 控制', rounds=1)
        until(lambda: self.nodes['A'].active is not None)
        self.nodes['A'].command('pause')
        until(lambda: self.state() == 'paused', 20)
        self.assertEqual(len(self.calls('A')), 0)
        self.nodes['A'].command('note', text='新增要求：验收 Unicode 中文')
        self.nodes['A'].command('resume')
        until(lambda: self.state() == 'completed', 25)
        self.assertEqual([len(self.calls(r)) for r in ('A', 'B')], [1, 2])
        self.assertIn('新增要求：验收 Unicode 中文', self.calls('A')[0]['prompt'])
        self.assertEqual(read_json(self.job() / 'meta.json')['initiator'], 'B')

    def test_receiver_can_cancel_inflight(self):
        self.nodes['A'].command('start', topic='[LONG] 中止测试', rounds=3)
        until(lambda: self.nodes['B'].active is not None and len(self.calls('A')) == 1)
        self.nodes['B'].command('cancel')
        until(lambda: self.state() == 'cancelled', 12)
        self.assertEqual(len(self.calls('B')), 0)
        until(lambda: not self.nodes['A'].active and not self.nodes['B'].active)

    def test_failure_propagates_and_locks_prevent_duplicate_nodes(self):
        with self.assertRaises(RuntimeError):
            FileLock(self.root / 'share' / 'nodes' / 'A.lease').acquire()
        self.nodes['A'].command('start', topic='[FAIL] 接口错误', rounds=1)
        until(lambda: self.state() == 'failed')
        self.assertEqual(len(self.calls('B')), 0)
        self.assertTrue((self.job() / 'A-error.json').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
