from fixture_paths import FixtureTemporaryDirectory
"""Unlimited task waiting, with virtual time and isolated offline integration."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
from app import protocol
from app.protocol import RpcClient, TurnView, Cancelled
from app.storage import Mailbox, Settings, read_json, atomic_json, LONG_TASK_FEATURE
from app.engine import NodeService
import test_system
from test_system import until


class Clock:
    def __init__(self):
        self.value = 100.

    def monotonic(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds


class ScriptedRpc(RpcClient):
    """Real RPC/turn loop, deterministic incoming events and virtual time."""
    def __init__(self, clock, script):
        super().__init__([], '.')
        self.process = SimpleNamespace(poll=lambda: None)
        self.clock, self.script, self.sent = clock, list(script), []

    def send(self, message):
        self.sent.append(message)

    def poll(self, timeout=0):
        if not self.script:
            raise AssertionError('Script exhausted; loop should already have terminated')
        elapsed, message = self.script.pop(0)
        self.clock.value += elapsed
        if message == 'ack':
            message = {'id': self.sent[0]['id'], 'result': {'turn': {'id': 'turn-1'}}}
        if message:
            self.messages.put(message)
        super().poll(0)


def event(method, **params):
    return {'method': method, 'params': {'threadId': 'thread-1', 'turnId': 'turn-1', **params}}


def finished(status='completed'):
    return event('turn/completed', turn={'id': 'turn-1', 'status': status,
                 'items': [{'type': 'agentMessage', 'id': 'answer', 'phase': 'final_answer', 'text': '完成'}]})


class WaitingTests(unittest.TestCase):
    def run_rpc(self, script, pump_extra=lambda client: None):
        clock = Clock()
        client = ScriptedRpc(clock, script)
        observations = []
        def pump():
            observations.append(client.activity_snapshot())
            pump_extra(client)
        with patch.object(protocol, 'time', clock), patch.object(protocol, 'stop_process_tree') as stop:
            result = client.run_turn('thread-1', '测试', 'A', '000-A',
                                     {'model': 'mock', 'timeout_seconds': 1}, lambda v: None, pump)
            stop.assert_not_called()
        self.assertEqual(result['answer'], '完成')
        self.assertEqual([m['method'] for m in client.sent], ['turn/start'])
        return observations

    def test_model_start_ack_can_take_two_days_without_retry(self):
        self.run_rpc([(172800, 'ack'), (1, finished())])

    def test_tool_running_more_than_two_days_keeps_waiting(self):
        seen = self.run_rpc([(0, 'ack'), (1, event('item/started', item={
            'id': 'tool', 'type': 'commandExecution', 'status': 'inProgress', 'command': 'offline fixture'})),
            (172800, None), (1, finished())])
        self.assertTrue(any(x['phase'] == 'tool_running' and x['elapsed_seconds'] > 900 for x in seen))

    def test_silent_process_is_uncertain_and_not_automatically_killed(self):
        seen = self.run_rpc([(0, 'ack'), (1800, None), (1, finished())])
        self.assertTrue(any(x['phase'] == 'quiet' and x['process_alive'] for x in seen))

    def test_manual_cancel_still_interrupts(self):
        clock = Clock()
        client = ScriptedRpc(clock, [(0, 'ack'), (0, finished('interrupted'))])
        def pump():
            if client.current.turn_id:
                raise Cancelled('用户停止')
        with patch.object(protocol, 'time', clock), patch.object(protocol, 'stop_process_tree'):
            with self.assertRaises(Cancelled):
                client.run_turn('thread-1', '测试', 'A', '000-A', {'model': 'mock'}, lambda v: None, pump)
        self.assertEqual([m['method'] for m in client.sent], ['turn/start', 'turn/interrupt'])

    def test_unresponsive_interrupt_still_cleans_owned_process(self):
        clock = Clock()
        client = ScriptedRpc(clock, [(0, 'ack'), (11, None)])
        def pump():
            if client.current.turn_id:
                raise Cancelled('用户停止')
        with patch.object(protocol, 'time', clock), patch.object(protocol, 'stop_process_tree') as stop:
            with self.assertRaisesRegex(Cancelled, '子进程'):
                client.run_turn('thread-1', '测试', 'A', '000-A', {'model': 'mock'}, lambda v: None, pump)
            stop.assert_called_once_with(client.process)

    def test_actual_process_exit_is_error_not_infinite_wait(self):
        clock = Clock()
        client = ScriptedRpc(clock, [(0, 'ack'), (1, {'method': '_eof'})])
        with patch.object(protocol, 'time', clock), patch.object(protocol, 'stop_process_tree'):
            with self.assertRaisesRegex(RuntimeError, '意外退出'):
                client.run_turn('thread-1', '测试', 'A', '000-A', {'model': 'mock'}, lambda v: None, lambda: None)

    def test_other_thread_events_do_not_claim_progress(self):
        seen = self.run_rpc([(0, 'ack'), (120, event('item/agentMessage/delta', threadId='other', itemId='x', delta='other')),
                            (1, finished())])
        self.assertTrue(any(x['phase'] == 'quiet' and x['event_count'] == 0 for x in seen))

    def test_new_meta_has_no_expiry_legacy_values_remain_strict(self):
        with FixtureTemporaryDirectory(prefix='agentlink-wait-') as folder:
            box = Mailbox(Path(folder) / 'share', Path(folder) / 'local'); box.connect()
            meta = box.create('长任务', 1, unlimited=True)
            self.assertIsNone(meta['expires'])
            with patch('app.storage.now', return_value=time.time() + 365 * 86400):
                box.validate_meta(meta, meta['id'])
            for value in (True, 2.0, None, '2'):
                with self.assertRaises(ValueError):
                    box.validate_meta(dict(meta, protocol=value), meta['id'])
            for value in (0, True, float('nan'), float('inf')):
                with self.assertRaises(ValueError):
                    box.validate_meta(dict(meta, expires=value), meta['id'])
            with self.assertRaises(ValueError):
                box.validate_meta(dict(meta, wait_policy='unknown'), meta['id'])
            atomic_json(Path(folder) / 'settings.json', {'timeout_seconds': 900, 'auto_connect': False})
            self.assertEqual(Settings.load(folder).timeout_seconds, 0)

    def test_peer_heartbeat_gap_detected_on_local_monotonic_clock(self):
        with FixtureTemporaryDirectory(prefix='agentlink-peer-') as folder, __import__('contextlib').ExitStack() as locks:
            box = Mailbox(Path(folder) / 'share', Path(folder) / 'local'); box.connect()
            node = NodeService(Settings(), box.local, lambda *args: None); node.box = box
            peer = {'updated': time.time(), 'instance': 'b'*32, 'status': 'running', 'job_id': 'job'}
            atomic_json(box.root / 'nodes' / 'B.json', peer)
            lease=__import__('liveness_fixture').owned_peer(node,peer)
            locks.callback(lease.close)
            node._check_peer_wait('job', 'B')
            node.liveness.last_progress -= 31
            with self.assertRaises(__import__('app.interruption',fromlist=['TechnicalInterruption']).TechnicalInterruption):
                node._check_peer_wait('job', 'B')
            # A new heartbeat renews waiting regardless of cross-machine wall-clock skew.
            node.liveness.reset()
            peer['updated'] -= 3600
            __import__('liveness_fixture').respond(node,peer)
            node._check_peer_wait('job', 'B')

    def test_coordinator_waits_past_old_twenty_minute_limit(self):
        with FixtureTemporaryDirectory(prefix='agentlink-coordinator-') as folder:
            box = Mailbox(Path(folder) / 'share', Path(folder) / 'local'); box.connect()
            node = NodeService(Settings(role='A'), box.local, lambda *args: None)
            node.box, node.connected = box, True
            clock = Clock()
            peer = {'updated': time.time(), 'instance': 'peer', 'status': 'idle',
                    'features': [LONG_TASK_FEATURE]}
            atomic_json(box.root / 'nodes' / 'B.json', peer)
            own_calls, waiting_pumps = [], []
            def own(index, prompt):
                own_calls.append(index)
                value = {'index': index, 'role': 'A', 'step': f'{index:03d}-A',
                         'status': 'completed', 'answer': '本机完成'}
                box.put(node.active['id'], f'turn-{index:03d}-A.json', value)
                return value
            def pump():
                if (box.get(node.active['id'], 'state.json', {}) or {}).get('status') == 'waiting_peer':
                    clock.value += 2000
                    waiting_pumps.append(clock.value)
                    peer.update(updated=time.time() + clock.value, job_id=node.active['id'], status='running')
                    atomic_json(box.root / 'nodes' / 'B.json', peer)
                    if len(waiting_pumps) == 3:
                        box.put(node.active['id'], 'turn-001-B.json', {'index': 1, 'role': 'B', 'step': '001-B',
                                'status': 'completed', 'answer': '对方长任务完成'})
            node._perform, node._pump = own, pump
            # Isolate coordinator timing; separate service tests exercise real
            # instance/role/execution gates. Keep result identity validation.
            node._check_peer_compatibility = lambda *args, **kwargs: 'a' * 32
            original_put = box.put
            def put(job_id, filename, value):
                if filename.startswith('turn-'):
                    value = dict(value, job_id=job_id)
                original_put(job_id, filename, value)
            box.put = put
            with patch('app.engine.time', clock):
                node.run_initiator('超过旧等待上限', 1)
            self.assertEqual(box.get(node.selected, 'state.json')['status'], 'completed')
            self.assertEqual(own_calls, [0, 2])
            self.assertGreaterEqual(len(waiting_pumps), 3)


class WaitingServiceTests(unittest.TestCase):
    setUp = test_system.SystemTests.setUp
    tearDown = test_system.SystemTests.tearDown
    calls = test_system.SystemTests.calls
    job = test_system.SystemTests.job
    state = test_system.SystemTests.state

    def test_peer_progress_visible_and_no_expiry_on_real_mock_flow(self):
        self.nodes['A'].settings.timeout_seconds = 1  # Legacy value must not kill this longer turn.
        self.nodes['A'].command('start', topic='[LONG] 无时限活动同步', rounds=1)
        until(lambda: len(self.calls('A')) == 1)
        until(lambda: any(k == 'peer' and v.get('execution') for k, v in self.events['B']))
        meta = read_json(self.job() / 'meta.json')
        self.assertEqual((meta['protocol'], meta['expires']), (2, None))
        until(lambda: self.state() == 'completed', 35)
        self.assertEqual([len(self.calls(r)) for r in ('A', 'B')], [2, 1])
        peer_events = [v['execution'] for k, v in self.events['B'] if k == 'peer' and v.get('execution')]
        self.assertTrue(any(x['event_count'] > 0 and x['elapsed_seconds'] >= 1 for x in peer_events))


if __name__ == '__main__':
    unittest.main(verbosity=2)
