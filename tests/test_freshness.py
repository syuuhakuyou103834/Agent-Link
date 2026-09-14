from fixture_paths import fs, entries
import json
from pathlib import Path
import sys
import time
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
from test_repairs import RepairComponentTests
from app.engine import NodeService, SAFETY_FEATURE
from app.liveness import FEATURE as LF
from app.storage import Settings, FileLock, atomic_json, read_json

class FreshnessTests(RepairComponentTests):
    def test_T18_exit_after_final_gate_may_cost_one_request_but_no_continuation(self):
        meta = self.ready()
        self.node.active = meta
        path, peer = self.peer_record()
        original = self.client.run_turn
        def call(*args, **kwargs):
            result = original(*args, **kwargs)
            atomic_json(path, dict(peer, status='offline'))
            return result
        self.client.run_turn = call
        with self.assertRaises(ValueError) as error:
            self.node._perform(1, 'peer exits after request accepted')
        self.node._failed(error.exception)
        self.assertEqual(len(self.client.calls), 1)
        self.assertEqual(self.box.get(meta['id'], 'state.json')['status'], 'failed')
        self.assertFalse((fs(self.box.job(meta['id']) / 'turn-001-B.json')).exists())
        (fs(self.root / 'post-gate-exit.json')).write_text(json.dumps({
            'job_id':meta['id'], 'requests':1, 'automatic_retry':False,
            'window':'after final peer check and client request acceptance', 'status':'failed'}), encoding='utf-8')

    def test_T18_queued_admission_cannot_rebind_to_restarted_peer(self):
        meta = self.ready()
        self.box.put(meta['id'],'state.json',{'status':'completed'})
        path, peer = self.peer_record()
        self.node._admit_start({'request_id':'queue-binding','topic':'new request','rounds':1})
        kind, args = self.node.commands.get_nowait()
        self.assertEqual(kind, 'start')
        atomic_json(self.box.root / 'nodes/A-owner.json', {'instance':'c'*32,'role':'A'})
        atomic_json(path, dict(peer, instance='c'*32))
        self.node.run_initiator(args['topic'], args['rounds'], _dispatch=args['_dispatch'],
                                _peer_instance=args['_peer_instance'])
        self.assertEqual(len(list(entries(self.box.root / 'jobs','iterdir'))), 1)
        self.assertEqual(self.client.calls, [])
        self.assertTrue(any(k=='activity' and '实例' in v['text'] for k,v in self.events))

    def peer_record(self):
        path = self.box.root / 'nodes/A.json'
        peer = read_json(path, {}) or {}
        peer.update(role='A', instance='a'*32, updated=time.time(), status='idle', features=[SAFETY_FEATURE,LF])
        atomic_json(self.box.root / 'nodes/A-owner.json', {'instance':'a'*32,'role':'A'})
        atomic_json(path, peer)
        return path, peer

    def test_T18_expired_offline_invalid_and_replaced_capability_rejected(self):
        self.ready()
        path, normal = self.peer_record()
        cases = [('offline', {'status':'offline'}), ('sequence_invalid', {'seq':0}),
                 ('sequence_bool', {'seq':True}), ('sequence_float', {'seq':1.5}),
                 ('sequence_old', {'seq':1}), ('missing_instance', {'instance':None}),
                 ('new_instance_old_capability', {'instance':'c'*32}), ('missing_features', {'features':None})]
        for name, patch in cases:
            with self.subTest(case=name):
                peer = dict(normal, **patch)
                atomic_json(path, peer)
                with self.assertRaises(ValueError):
                    self.node._check_peer_compatibility(peer)
        self.assertEqual(self.client.calls, [])

    def test_T18_unheld_peer_role_lease_rejects_recent_capabilities(self):
        self.ready()
        _, peer = self.peer_record()
        for lease in getattr(self, 'peer_locks', []):
            lease.close()
        with self.assertRaises(ValueError):
            self.node._check_peer_compatibility(peer)
        self.assertEqual(self.client.calls, [])

    def test_T18_peer_exits_during_thread_setup_zero_model_requests(self):
        meta = self.ready()
        self.node.active = meta
        path, peer = self.peer_record()
        original = self.client.new_thread
        def new_thread(*args):
            result = original(*args)
            atomic_json(path, dict(peer, status='offline'))
            return result
        self.client.new_thread = new_thread
        with self.assertRaises(Exception):
            self.node._perform(1, 'exit after compatibility check')
        self.assertEqual(self.client.calls, [])
        self.assertFalse((fs(self.box.job(meta['id']) / 'turn-001-B.json')).exists())

    def test_T18_restart_between_gate_and_send_does_not_rebind_old_job(self):
        meta = self.ready()
        self.node.active = meta
        path, peer = self.peer_record()
        original = self.client.new_thread
        def new_thread(*args):
            result = original(*args)
            atomic_json(self.box.root / 'nodes/A-owner.json', {'instance':'c'*32,'role':'A'})
            atomic_json(path, dict(peer, instance='c'*32))
            return result
        self.client.new_thread = new_thread
        with self.assertRaises(Exception):
            self.node._perform(1, 'restart barrier')
        self.assertEqual(self.client.calls, [])

    def test_T05_cross_job_reuse_and_cross_node_collision_are_explicit(self):
        first = self.ready()
        self.node._edit_control(first['id'], 'note', 'same text', 'collision')
        other = NodeService(Settings(role='A', shared_root=str(self.box.root)), self.root / 'A',
                            lambda *args: None)
        other.box, other.connected = self.box, True
        other._edit_control(first['id'], 'note', 'same text', 'collision')
        self.assertEqual(self.box.get(first['id'],'control.json')['notes'], ['same text'])
        with self.assertRaisesRegex(ValueError, '编号'):
            other._edit_control(first['id'], 'note', 'different text', 'collision')
        other._edit_control(first['id'], 'note', 'same text', 'another-id')
        self.assertEqual(self.box.get(first['id'],'control.json')['notes'], ['same text','same text'])
        second = self.box.create('second job', 1, 'A')
        other._edit_control(second['id'], 'note', 'independent', 'collision')
        self.assertEqual(self.box.get(second['id'],'control.json')['notes'], ['independent'])
        self.assertEqual(self.box.get(first['id'],'control.json')['notes'], ['same text','same text'])

if __name__ == '__main__':
    suite = unittest.TestSuite(FreshnessTests(name) for name in FreshnessTests.__dict__ if name.startswith('test_'))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(not result.wasSuccessful())
