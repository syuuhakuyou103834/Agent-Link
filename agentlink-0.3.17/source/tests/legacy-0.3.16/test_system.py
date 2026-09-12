import json
import os
from pathlib import Path
import sys
import time
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.engine import NodeService
from app.storage import Settings, read_json, FileLock, import_legacy, atomic_json
from app.context import FEATURE


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
        (self.root / 'case.txt').write_text(self.id(), encoding='utf-8')
        self.shared = (Path(os.environ['AGENTLINK_TEST_SHARE_ROOT']) / ('e2e-' + self.root.name)
                       if os.environ.get('AGENTLINK_TEST_SHARE_ROOT') else self.root / 'share')
        self.nodes, self.events = {}, {'A': [], 'B': []}
        for role in ('A', 'B'):
            config = Settings(role=role, shared_root=str(self.shared), auto_connect=True)
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
        paths = sorted((self.shared / 'jobs').iterdir())
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
            FileLock(self.shared / 'nodes' / 'A.lease').acquire()
        self.nodes['A'].command('start', topic='[FAIL] 接口错误', rounds=1)
        until(lambda: self.state() == 'failed')
        self.assertEqual(len(self.calls('B')), 0)
        self.assertTrue((self.job() / 'A-error.json').exists())

    def start_and_finish(self, role, topic, parent=None):
        count = len(list((self.shared / 'jobs').iterdir()))
        until(lambda: all(not n.active for n in self.nodes.values()))
        until(lambda: all(not read_json(self.shared / 'nodes' / (r + '.json'), {}).get('job_id') for r in ('A', 'B')))
        self.nodes[role].command('start', topic=topic, rounds=1, parent_job_id=parent)
        until(lambda: len(list((self.shared / 'jobs').iterdir())) == count + 1)
        path = self.job()
        until(lambda: read_json(path / 'state.json', {}).get('status') == 'completed')
        until(lambda: all(not n.active for n in self.nodes.values()))
        return path

    def test_continuation_both_nodes_restart_reverse_and_fresh(self):
        first = self.start_and_finish('A', 'FIRST-HISTORY-UNIQUE: 按 T19 测试集检查中文')
        # Add a recorded user requirement to prove it reaches future requests.
        control = read_json(first / 'control.json')
        control['notes'] = ['ONLY-TEST-T03 用户约束']
        atomic_json(first / 'control.json', control)
        original_turn = (first / 'turn-002-A.json').read_bytes()
        for node in self.nodes.values():
            node.stop()
        for node in self.nodes.values():
            node.thread.join(15)
            self.assertFalse(node.thread.is_alive())
        for role in ('A', 'B'):
            previous = self.nodes[role]
            self.nodes[role] = NodeService(previous.settings, previous.data, previous.emit, previous.command_override)
            self.nodes[role].start()
        until(lambda: all(n.connected for n in self.nodes.values()))
        second = self.start_and_finish('B', 'SECOND-EXECUTE-UNIQUE: 按上一轮开始测试', first.name)
        for role, offset, count in (('A', 2, 1), ('B', 1, 2)):
            calls = self.calls(role)[offset:]
            self.assertEqual(len(calls), count)
            for call in calls:
                self.assertIn('FIRST-HISTORY-UNIQUE', call['prompt'])
                self.assertIn('ONLY-TEST-T03', call['prompt'])
                self.assertIn('中文传递正确', call['prompt'])
            self.assertNotEqual(self.calls(role)[0]['thread'], calls[0]['thread'])
        self.assertEqual((self.root / 'A' / 'runs' / second.name / 'context.json').read_bytes(),
                         (self.root / 'B' / 'runs' / second.name / 'context.json').read_bytes())
        third = self.start_and_finish('A', 'THIRD-CONTINUE-UNIQUE: 汇总阶段结果', second.name)
        context = read_json(third / 'context.json')
        self.assertEqual([d['job_id'] for d in context['discussions']], [first.name, second.name])
        for role in ('A', 'B'):
            self.assertIn('FIRST-HISTORY-UNIQUE', self.calls(role)[-1]['prompt'])
            self.assertIn('SECOND-EXECUTE-UNIQUE', self.calls(role)[-1]['prompt'])
        fresh = self.start_and_finish('B', 'FRESH-UNRELATED: 独立新任务')
        self.assertNotIn('context', read_json(fresh / 'meta.json'))
        for role in ('A', 'B'):
            self.assertNotIn('FIRST-HISTORY-UNIQUE', self.calls(role)[-1]['prompt'])
        self.assertEqual(sum(len(self.calls(r)) for r in ('A', 'B')), 12, 'Four discussions, exactly 12 requests, no summary call')
        self.assertEqual((first / 'turn-002-A.json').read_bytes(), original_turn)

    def test_continuation_missing_history_or_legacy_peer_never_calls_model(self):
        until(lambda: FEATURE in read_json(self.shared / 'nodes' / 'B.json', {}).get('features', []))
        missing = '20260910-000000-' + 'a' * 32
        with self.assertRaisesRegex(ValueError, '缺失'):
            self.nodes['A'].run_initiator('继续', 1, missing)
        self.nodes['B'].stop(); self.nodes['B'].thread.join(15)
        atomic_json(self.shared / 'nodes' / 'B.json', {'updated': time.time(), 'status': 'idle', 'version': '0.3.1'})
        with self.assertRaisesRegex(ValueError, '0.3.2'):
            self.nodes['A'].run_initiator('继续', 1, missing)
        self.assertEqual(len(self.calls('A')) + len(self.calls('B')), 0)
        self.assertEqual(len(list((self.shared / 'jobs').iterdir())), 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
