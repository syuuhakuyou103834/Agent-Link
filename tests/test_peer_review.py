from fixture_paths import fs, entries
"""B review gaps. Direct module execution avoids inherited duplicate discovery."""
import json
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
from test_repairs import RepairComponentTests
from test_system import SystemTests, until
from app.storage import atomic_json, read_json, FileLock
from app.protocol import Cancelled
import app.storage as storage

class ReviewComponents(RepairComponentTests):
    def test_T11_cancel_before_model_request_zero_send(self):
        meta = self.ready()
        self.node.active = meta
        original = self.client.new_thread
        def create(*args):
            thread = original(*args)
            self.node._edit_control(meta['id'], 'cancel', '')
            return thread
        self.client.new_thread = create
        with self.assertRaises(Cancelled):
            self.node._perform(1, 'cancel before send')
        self.assertEqual(self.client.calls, [])
        self.assertEqual(self.box.get(meta['id'], 'state.json')['status'], 'cancelled')
        self.node.active = None
        self.node.scan_receiver()
        self.assertEqual(self.client.calls, [])

    def test_T11_published_result_ack_lost_no_repeat(self):
        meta = self.ready()
        self.node.active = meta
        original = storage.atomic_json
        published = []
        def publish(path, value):
            original(path, value)
            if Path(path) == self.box.job(meta['id']) / 'turn-001-B.json':
                published.append(fs(Path(path)).read_bytes())
                raise OSError('injected acknowledgement loss after atomic publication')
        with patch.object(storage, 'atomic_json', side_effect=publish):
            with self.assertRaises(OSError) as error:
                self.node._perform(1, 'publish then lose confirmation')
            self.node._failed(error.exception)
        self.assertEqual(len(published), 1)
        self.assertEqual((fs(self.box.job(meta['id']) / 'turn-001-B.json')).read_bytes(), published[0])
        self.node.active = None
        self.node.scan_receiver()
        self.assertEqual(len(self.client.calls), 1)
        self.assertEqual(self.box.get(meta['id'], 'state.json')['status'], 'failed')

    def test_T05_note_id_replay_deduplicates_but_equal_text_new_id_preserved(self):
        meta = self.ready()
        self.node.active = meta
        for ident in ('note-1', 'note-1', 'note-2'):
            self.node.command('note', text='有意重复的用户要求', note_id=ident)
        self.node._drain_controls()
        self.assertEqual(self.box.get(meta['id'], 'control.json')['notes'],
                         ['有意重复的用户要求', '有意重复的用户要求'])
        self.node.command('note', text='不同内容重复同一编号', note_id='note-1')
        self.node._drain_controls()
        self.assertEqual(len(self.box.get(meta['id'], 'control.json')['notes']), 2)
        self.assertTrue(any(k == 'activity' and '编号' in v['text'] for k,v in self.events))

    def test_T18_missing_safety_feature_rejected_in_both_directions(self):
        for local in ('A', 'B'):
            with self.subTest(local=local):
                self.node.settings.role = local
                peer = self.node.peer_role
                old = self.box.create('old peer job', 1, peer)
                self.box.put(old['id'], 'state.json', {'status': 'completed'})
                original = (fs(self.box.job(old['id']) / 'state.json')).read_bytes()
                heartbeat = {'version': '0.3.4', 'features': ['discussion-context-v1'],
                             'updated': time.time(), 'job_id': old['id'], 'role': peer}
                atomic_json(self.box.root / 'nodes' / (peer + '.json'), heartbeat)
                self.node._admit_start({'request_id': 'version-' + local, 'topic': 'reject', 'rounds': 1})
                self.assertTrue(self.node.commands.empty())
                self.assertFalse((fs(self.box.root / 'start-requests' / ('version-' + local + '.json'))).exists())
                self.assertEqual((fs(self.box.job(old['id']) / 'state.json')).read_bytes(), original)
                # Receiver rejects before active/claim/history mutation as well.
                self.box.put(old['id'], 'state.json', {'status': 'waiting_peer', 'index': 1})
                before = (fs(self.box.job(old['id']) / 'state.json')).read_bytes()
                with self.assertRaisesRegex(ValueError, '兼容'):
                    self.node.scan_receiver()
                self.assertEqual((fs(self.box.job(old['id']) / 'state.json')).read_bytes(), before)
                self.assertEqual(list(entries(self.box.job(old['id']),'glob','*.claim')), [])
                self.assertEqual(self.client.calls, [])
                self.box.put(old['id'], 'state.json', {'status': 'cancelled'})

class ReviewServices(SystemTests):
    def test_T05_duplicate_resume_does_not_add_calls_or_revive_cancelled(self):
        a = self.nodes['A']
        a.command('start', topic='[LONG] pause replay', rounds=1)
        until(lambda: len(self.calls('A')) == 1 and self.nodes['B'].active)
        self.nodes['B'].command('pause')
        until(lambda: self.state() == 'paused')
        self.assertEqual(len(self.calls('B')), 0)
        self.nodes['B'].command('resume')
        a.command('resume')
        until(lambda: self.state() == 'completed')
        until(lambda: all(not n.active and not n.start_pending for n in self.nodes.values()))
        self.assertEqual([len(self.calls(r)) for r in ('A','B')], [2,1])
        a.command('start', topic='[LONG] stop then resume', rounds=1)
        until(lambda: len(self.calls('A')) == 3)
        job = self.shared / 'jobs' / a.active['id']
        a.command('cancel')
        until(lambda: read_json(job / 'state.json', {}).get('status') == 'cancelled')
        for node in self.nodes.values():
            node.command('resume')
        until(lambda: all(not n.active and not n.start_pending for n in self.nodes.values()))
        self.assertEqual([len(self.calls(r)) for r in ('A','B')], [3,1])
        self.assertEqual(read_json(job / 'state.json')['status'], 'cancelled')

    def test_T17_late_error_after_new_job_started_preserves_both_jobs(self):
        peer, a = self.nodes['B'], self.nodes['A']
        entered, release = threading.Event(), threading.Event()
        isolate, isolated = threading.Event(), threading.Event()
        original = peer.client.run_turn
        old_id = []
        def delayed_error(*args, **kwargs):
            result = original(*args, **kwargs)
            if not old_id:
                old_id.append(peer.active['id'])
                entered.set()
                if not isolate.wait(20):
                    raise TimeoutError('Explicit executor isolation barrier')
                # Original RPC is complete. Release verified execution ownership
                # on its service thread, retaining a delayed error callback.
                peer._release_execution()
                isolated.set()
                if not release.wait(20):
                    raise TimeoutError('test error barrier')
                raise RuntimeError('late old callback failure')
            return result
        peer.client.run_turn = delayed_error
        a.command('start', topic='old late error', rounds=1)
        try:
            self.assertTrue(entered.wait(12))
            old = self.shared / 'jobs' / old_id[0]
            a.command('cancel')
            until(lambda: read_json(old / 'state.json', {}).get('status') == 'cancelled')
            until(lambda: not a.active and not a.start_pending)
            before = (fs(old / 'state.json')).read_bytes()
            event_start = len(self.events['A'])
            a.command('start', topic='must reject before executor isolation', rounds=1)
            until(lambda:any(k=='error' and '执行归属' in v['message'] for k,v in self.events['A'][event_start:]))
            self.assertEqual([len(self.calls(r)) for r in ('A','B')],[1,1])
            isolate.set()
            self.assertTrue(isolated.wait(5))
            a.command('start', topic='new valid job', rounds=1)
            until(lambda: a.active and a.active['id'] != old_id[0] and len(self.calls('A')) == 2)
            new = self.shared / 'jobs' / a.active['id']
            release.set()
            until(lambda: read_json(new / 'state.json', {}).get('status') == 'completed')
            until(lambda: all(not n.active for n in self.nodes.values()))
            self.assertEqual((fs(old / 'state.json')).read_bytes(), before)
            self.assertFalse((fs(new / 'B-error.json')).exists())
            self.assertFalse((fs(old / 'turn-001-B.json')).exists())
            self.assertEqual([len(self.calls(r)) for r in ('A','B')], [3,2])
        finally:
            isolate.set()
            release.set()

if __name__ == '__main__':
    suite = unittest.TestSuite(cls(name) for cls in (ReviewComponents, ReviewServices)
        for name in cls.__dict__ if name.startswith('test_'))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(not result.wasSuccessful())
