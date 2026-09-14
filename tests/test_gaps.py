from fixture_paths import fs, entries
"""Additional local fault/ordering regressions; never connects to real models."""
import sys
from pathlib import Path
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
from test_repairs import RepairComponentTests
from app.protocol import TurnView
from app.storage import read_json, atomic_json


class GapTests(RepairComponentTests):
    # Reuse fixtures, but keep inherited test names out of this suite.
    def test_T05_pause_at_last_pre_send_pump(self):
        meta = self.ready()
        self.node.active = meta
        original = self.node._pump
        paused = threading.Event()
        done = []
        def pump():
            if not paused.is_set():
                self.node._edit_control(meta['id'], 'pause', '')
                paused.set()
            original()
        self.node._pump = pump
        def perform():
            try:
                self.node._perform(1, 'pause barrier')
            except Exception as error:
                done.append(error)
        worker = threading.Thread(target=perform)
        worker.start()
        try:
            self.assertTrue(paused.wait(4))
            self.assertFalse(self.client.entered.wait(.3), 'Paused before send must mean zero requests')
            self.node._edit_control(meta['id'], 'resume', '')
            worker.join(5)
            self.assertFalse(worker.is_alive())
            self.assertEqual(done, [])
            self.assertEqual(len(self.client.calls), 1)
        finally:
            self.node._edit_control(meta['id'], 'resume', '')
            worker.join(5)

    def test_T17_queued_old_cancel_does_not_cancel_new_active(self):
        old = self.ready()
        self.node.active = old
        self.node.command('cancel')
        newer = self.box.create('new', 1, 'B')
        self.box.put(newer['id'], 'state.json', {'status': 'running'})
        self.node.active = newer
        before = (fs(self.box.job(newer['id']) / 'control.json')).read_bytes()
        self.node._drain_controls()
        self.assertEqual((fs(self.box.job(newer['id']) / 'control.json')).read_bytes(), before)
        self.assertEqual(self.box.get(old['id'], 'state.json')['status'], 'cancelled')

    def test_T11_claim_without_result_reports_uncertainty_zero_resend(self):
        meta = self.ready()
        self.node.active = meta
        self.assertTrue(self.box.claim(meta['id'], '001-B'))
        with self.assertRaisesRegex(RuntimeError, '不确定'):
            self.node._receive_step(self.box.job(meta['id']), meta)
        self.assertEqual(self.client.calls, [])

    def test_T18_request_filename_must_match_step(self):
        meta = self.ready()
        self.node.active = meta
        path = self.box.job(meta['id']) / 'request-001-B.json'
        fs(path).rename(fs(path.with_name('request-003-B.json')))
        with self.assertRaises(ValueError):
            self.node._receive_step(self.box.job(meta['id']), meta)
        self.assertEqual(self.client.calls, [])

    def test_T18_invalid_indices_are_reported_not_silently_skipped(self):
        meta = self.ready()
        self.node.active = meta
        for index in (True, 1.0, None, -1, 0, 3):
            with self.subTest(index=index):
                self.box.put(meta['id'], 'request-001-B.json', {
                    'protocol': 1, 'job_id': meta['id'], 'index': index, 'prompt': 'invalid'})
                with self.assertRaises(ValueError):
                    self.node._receive_step(self.box.job(meta['id']), meta)
                self.assertEqual(self.client.calls, [])


class EventTests(unittest.TestCase):
    def test_T17_old_turn_events_same_thread_are_ignored(self):
        for method, extra in [
            ('turn/started', {'turn': {'id': 'old'}}),
            ('item/agentMessage/delta', {'itemId': 'answer', 'delta': 'OLD'}),
            ('item/completed', {'item': {'id': 'answer', 'type': 'agentMessage', 'text': 'OLD'}}),
            ('error', {'error': {'message': 'OLD'}}),
        ]:
            with self.subTest(method=method):
                view = TurnView('B', '003-B', 'same-thread')
                view.turn_id = 'new'
                before = view.snapshot()
                view.feed(method, dict(threadId='same-thread', turnId='old', **extra))
                self.assertEqual(view.snapshot(), before)
        view.feed('item/agentMessage/delta', {'threadId': 'same-thread', 'turnId': 'new',
                                            'itemId': 'valid', 'delta': '中文合法'})
        self.assertEqual(view.snapshot()['answer'], '中文合法')


if __name__ == '__main__':
    suite = unittest.TestSuite()
    for cls in (GapTests, EventTests):
        for name in cls.__dict__:
            if name.startswith('test_'):
                suite.addTest(cls(name))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(not result.wasSuccessful())
