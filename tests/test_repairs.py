"""T08/T17/T18 deterministic local regression. No external model or SMB."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import threading
import time
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
from app.engine import NodeService, SAFETY_FEATURE
from app.storage import Mailbox, Settings, atomic_json, read_json, FileLock
from app.protocol import Cancelled
import test_system
from test_system import until


class Fixture:
    """Records requests at entry, optionally holds results despite cancellation."""
    def __init__(self, root):
        self.root = root
        self.calls = []
        self.entered = threading.Event()
        self.release = threading.Event()
        self.block = False
        self.pump = None

    def start(self):
        pass

    def new_thread(self, *args):
        return 'fixture-' + uuid.uuid4().hex

    def run_turn(self, thread, prompt, role, step, settings, stream, pump):
        call = {'role': role, 'step': step, 'thread': thread, 'attempt': 1,
                'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest()}
        self.calls.append(call)
        with (self.root / 'fixture-requests.jsonl').open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(call) + '\n')
        self.entered.set()
        if self.block and not self.release.wait(15):
            raise TimeoutError('Test result barrier was not released')
        view = {'role': role, 'step': step, 'thread_id': thread,
                'status': 'completed', 'answer': '中文模拟完成', 'tools': [], 'summary': ''}
        stream(dict(view))
        return view


class RepairComponentTests(unittest.TestCase):
    def setUp(self):
        self.root = ROOT / 'test-output' / ('r-' + uuid.uuid4().hex[:10])
        self.root.mkdir(parents=True)
        (self.root / 'case.txt').write_text(self.id(), encoding='utf-8')
        self.box = Mailbox(self.root / 'share', self.root / 'B')
        self.box.connect()
        self.events = []
        self.node = NodeService(Settings(role='B', shared_root=str(self.box.root)), self.root / 'B',
                                lambda k, v: self.events.append((k, v)))
        self.node.box, self.node.connected = self.box, True
        self.node.client = self.client = Fixture(self.root)
        # Synthetic peers hold real local role leases and publish matching owners.
        self.peer_locks = []
        for role in ('A','B'):
            identity = role.lower() * 32
            self.peer_locks.append(FileLock(self.box.root / 'nodes' / (role + '.lease')).acquire())
            atomic_json(self.box.root / 'nodes' / (role + '-owner.json'), {'instance':identity,'role':role})
            atomic_json(self.box.root / 'nodes' / (role + '.json'), {
                'instance':identity, 'role':role, 'status':'idle','updated':time.time(),'features':[SAFETY_FEATURE]})

    def tearDown(self):
        for lease in self.peer_locks:
            lease.close()

    def ready(self):
        meta = self.box.create('合法中文对照', 1, 'A')
        meta['participants'] = {'A':'a'*32, 'B':self.node.instance}
        self.box.put(meta['id'], 'meta.json', meta)
        self.box.put(meta['id'], 'state.json', {'status': 'waiting_peer', 'index': 1})
        self.box.put(meta['id'], 'request-001-B.json', {
            'protocol': 1, 'job_id': meta['id'], 'index': 1, 'prompt': '合法中文请求'})
        atomic_json(self.box.root / 'nodes' / 'A.json', {'updated': time.time(), 'job_id': meta['id'],
            'features': [SAFETY_FEATURE], 'instance':'a'*32, 'role':'A','status':'idle'})
        return meta

    def test_T18_nine_invalid_meta_via_receiver_zero_claims_history_unchanged(self):
        cases = [('protocol', True), ('protocol', False), ('protocol', 1.0),
                 ('protocol', None), ('expires', float('nan')), ('expires', float('inf')),
                 ('expires', -float('inf')), ('expires', True), ('expires', None)]
        results = []
        sentinel = self.box.create('历史哨兵', 1)
        self.box.put(sentinel['id'], 'state.json', {'status': 'completed'})
        original = (self.box.job(sentinel['id']) / 'state.json').read_bytes()
        for field, value in cases:
            with self.subTest(field=field, value=value):
                meta = self.ready()
                if value is None:
                    del meta[field]
                else:
                    meta[field] = value
                self.box.put(meta['id'], 'meta.json', meta)
                state_before = (self.box.job(meta['id']) / 'state.json').read_bytes()
                with self.assertRaises(ValueError) as error:
                    self.node.scan_receiver()
                self.assertEqual(self.client.calls, [])
                self.assertEqual(list(self.box.job(meta['id']).glob('*.claim')), [])
                self.assertIsNone(self.node.active)
                self.assertEqual((self.box.job(meta['id']) / 'state.json').read_bytes(), state_before)
                self.assertEqual((self.box.job(sentinel['id']) / 'state.json').read_bytes(), original)
                with FileLock(self.box.root / 'discussion.lease'):
                    pass
                results.append({'field': field, 'input': repr(value), 'requests': 0,
                                'claims': 0, 'history_unchanged': True, 'error': str(error.exception)})
        (self.root / 'T18-cases.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')

    def test_T18_request_protocol_and_legal_control(self):
        meta = self.ready()
        self.node.active = meta
        request = read_json(self.box.job(meta['id']) / 'request-001-B.json')
        for protocol in (True, False, 1.0, None, '1', 2):
            with self.subTest(protocol=protocol):
                value = dict(request, protocol=protocol)
                if protocol is None:
                    del value['protocol']
                self.box.put(meta['id'], 'request-001-B.json', value)
                with self.assertRaises(ValueError):
                    self.node._receive_step(self.box.job(meta['id']), meta)
                self.assertEqual(self.client.calls, [])
                self.assertEqual(list(self.box.job(meta['id']).glob('*.claim')), [])
        self.box.put(meta['id'], 'request-001-B.json', request)
        self.node._receive_step(self.box.job(meta['id']), meta)
        self.node._receive_step(self.box.job(meta['id']), meta)
        self.assertEqual(len(self.client.calls), 1)
        self.assertEqual(read_json(self.box.job(meta['id']) / 'turn-001-B.json')['status'], 'completed')

    def late_result(self, replace_active):
        meta = self.ready()
        self.node.active = meta
        self.client.block = True
        errors = []
        def perform():
            try:
                self.node._perform(1, '旧请求')
            except Exception as error:
                errors.append(error)
        worker = threading.Thread(target=perform)
        worker.start()
        try:
            self.assertTrue(self.client.entered.wait(5))
            self.node._edit_control(meta['id'], 'cancel', '')
            old_state = (self.box.job(meta['id']) / 'state.json').read_bytes()
            with self.assertRaises(Cancelled):
                self.node._state('running', 1)
            if replace_active:
                newer = self.box.create('新场次', 1, 'B')
                self.box.put(newer['id'], 'state.json', {'status': 'running', 'index': 0})
                self.node.active = newer
                new_state = (self.box.job(newer['id']) / 'state.json').read_bytes()
            self.client.release.set()
            worker.join(5)
            self.assertFalse(worker.is_alive())
            self.assertEqual(len(errors), 1)
            self.assertIsInstance(errors[0], Cancelled)
            self.assertEqual(len(self.client.calls), 1)
            self.assertFalse((self.box.job(meta['id']) / 'turn-001-B.json').exists())
            self.assertEqual((self.box.job(meta['id']) / 'state.json').read_bytes(), old_state)
            if replace_active:
                self.assertEqual((self.box.job(newer['id']) / 'state.json').read_bytes(), new_state)
                self.assertFalse((self.box.job(newer['id']) / 'live-B.json').exists())
            (self.root / 'race-result.json').write_text(json.dumps({
                'old_job': meta['id'], 'replacement_active': replace_active,
                'requests': 1, 'old_state_unchanged': True, 'result_rejected': True,
                'error': str(errors[0])}, ensure_ascii=False, indent=2), encoding='utf-8')
        finally:
            self.client.release.set()
            worker.join(5)

    def test_T17_stop_committed_before_result(self):
        self.late_result(False)

    def test_T17_replaced_active_before_old_stream_and_result(self):
        self.late_result(True)

    def test_T17_completed_wins_late_cancel_failure_resume(self):
        meta = self.ready()
        self.node.active = meta
        self.node._state('completed')
        path = self.box.job(meta['id']) / 'state.json'
        before = path.read_bytes()
        for kind in ('cancel', 'resume', 'pause'):
            self.node._edit_control(meta['id'], kind, '')
        self.node._failed(RuntimeError('late failure'))
        with self.assertRaises(Cancelled):
            self.node._state('failed')
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse((self.box.job(meta['id']) / 'B-error.json').exists())
        self.assertEqual(self.client.calls, [])


class RepairServiceTests(unittest.TestCase):
    setUp = test_system.SystemTests.setUp
    tearDown = test_system.SystemTests.tearDown
    job = test_system.SystemTests.job
    calls = test_system.SystemTests.calls
    state = test_system.SystemTests.state

    def test_T08_running_duplicate_not_queued_and_request_id_replay_after_restart(self):
        node = self.nodes['A']
        node.command('start', topic='[LONG] 保持首场运行', rounds=1, request_id='stable-req')
        until(lambda: len(self.calls('A')) == 1)
        first = self.job()
        self.assertFalse(node.command('start', topic='重复投递', rounds=1, request_id='stable-req'))
        self.assertFalse(node.command('start', topic='不同请求', rounds=1, request_id='other-req'))
        node.command('cancel')
        until(lambda: read_json(first / 'state.json', {}).get('status') == 'cancelled')
        until(lambda: all(not n.active for n in self.nodes.values()) and not node.start_pending)
        node.stop()
        node.thread.join(15)
        self.assertFalse(node.thread.is_alive())
        node = self.nodes['A'] = NodeService(node.settings, node.data, node.emit, node.command_override)
        node.start()
        until(lambda: node.connected)
        node.command('start', topic='完成后重复编号', rounds=1, request_id='stable-req')
        until(lambda: not node.start_pending)
        self.assertEqual(len(list((self.shared / 'jobs').iterdir())), 1)
        self.assertEqual(sum(len(self.calls(r)) for r in ('A', 'B')), 1)
        until(lambda: any(k == 'error' and '已有记录' in v['message'] for k, v in self.events['A']))

    def concurrent_admission(self, same_id):
        barrier = threading.Barrier(3)
        def submit(role):
            barrier.wait()
            self.nodes[role].command('start', topic='并发准入 ' + role, rounds=1,
                                    request_id='same-request' if same_id else 'race-' + role)
        workers = [threading.Thread(target=submit, args=(r,)) for r in ('A', 'B')]
        for worker in workers:
            worker.start()
        barrier.wait()
        for worker in workers:
            worker.join(5)
        until(lambda: self.state() == 'completed')
        until(lambda: all(not n.active and not n.start_pending for n in self.nodes.values()))
        self.assertEqual(len(list((self.shared / 'jobs').iterdir())), 1)
        self.assertEqual(sum(len(self.calls(r)) for r in ('A', 'B')), 3)
        self.assertTrue(any(k == 'error' and ('冲突' in v['message'] or '已有讨论' in v['message'] or '只有 A' in v['message'])
                            for values in self.events.values() for k, v in values))

    def test_T08_different_requests_simultaneous_admission_one_job_three_requests(self):
        self.concurrent_admission(False)

    def test_T08_same_request_simultaneous_admission_one_job_three_requests(self):
        self.concurrent_admission(True)

    def test_T17_new_service_job_before_old_receiver_result(self):
        entered, release = threading.Event(), threading.Event()
        isolate, isolated = threading.Event(), threading.Event()
        peer = self.nodes['B']
        original = peer.client.run_turn
        old_job = []
        def delayed(*args, **kwargs):
            result = original(*args, **kwargs)
            if not old_job:
                old_job.append(peer.active['id'])
                entered.set()
                if not isolate.wait(20):
                    raise TimeoutError('Explicit executor isolation barrier')
                # The real RPC has completed above. Model a verified executor
                # fence with only a delayed, non-executing result callback left.
                peer._release_execution()
                isolated.set()
                if not release.wait(20):
                    raise TimeoutError('Old receiver result barrier')
            return result
        peer.client.run_turn = delayed
        a = self.nodes['A']
        a.command('start', topic='旧场次结果屏障', rounds=1)
        try:
            self.assertTrue(entered.wait(12))
            first = self.shared / 'jobs' / old_job[0]
            a.command('cancel')
            until(lambda: read_json(first / 'state.json', {}).get('status') == 'cancelled')
            until(lambda: not a.active and not a.start_pending)
            before = (first / 'state.json').read_bytes()
            event_start = len(self.events['A'])
            a.command('start', topic='旧执行者未隔离，必须拒绝', rounds=1)
            until(lambda:any(k=='error' and '执行归属' in v['message'] for k,v in self.events['A'][event_start:]))
            self.assertEqual([len(self.calls(r)) for r in ('A','B')],[1,1])
            isolate.set()
            self.assertTrue(isolated.wait(5))
            a.command('start', topic='新场次先启动', rounds=1)
            until(lambda: a.active and a.active['id'] != old_job[0] and len(self.calls('A')) == 2)
            second = self.shared / 'jobs' / a.active['id']
            release.set()
            until(lambda: read_json(second / 'state.json', {}).get('status') == 'completed')
            until(lambda: all(not n.active for n in self.nodes.values()))
            self.assertEqual((first / 'state.json').read_bytes(), before)
            self.assertFalse((first / 'turn-001-B.json').exists())
            self.assertEqual(len(list(second.glob('turn-*.json'))), 3)
            self.assertEqual([len(self.calls(r)) for r in ('A', 'B')], [3, 2])
        finally:
            isolate.set()
            release.set()


if __name__ == '__main__':
    unittest.main(verbosity=2)
