import ctypes
import errno
import json
from pathlib import Path
import os
import sys
import threading
import time
import unittest
from unittest.mock import patch
import uuid
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import storage


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.root = ROOT / 'test-output' / ('storage-' + uuid.uuid4().hex)
        self.root.mkdir(parents=True)
        self.path = self.root / 'heartbeat.json'
        storage.atomic_json(self.path, {'text': '中文 23℃', 'version': 1})

    @unittest.skipUnless(os.name == 'nt', 'Windows sharing semantics')
    def test_old_reader_errno13_when_writer_has_delete_access(self):
        # A rename needs DELETE access. Hold that access without deleting data.
        handle = storage._create_file(str(self.path), 0x10000, 7, None, 3, 0x80, None)
        self.assertNotEqual(handle, ctypes.c_void_p(-1).value)
        try:
            with self.assertRaises(PermissionError) as caught:
                self.path.read_bytes()  # 0.3.0 reader via the CRT
            self.assertEqual(caught.exception.errno, 13)
            self.assertEqual(storage.read_json(self.path)['text'], '中文 23℃')
        finally:
            storage._close_handle(handle)

    def test_transient_read_denial_recovers(self):
        real = storage._open_read
        calls = []
        def flaky(path):
            calls.append(path)
            if len(calls) < 3:
                raise PermissionError(errno.EACCES, 'sharing conflict', str(path))
            return real(path)
        with patch.object(storage, '_open_read', side_effect=flaky):
            self.assertEqual(storage.read_json(self.path)['version'], 1)
        self.assertEqual(len(calls), 3)

    def test_persistent_permission_error_not_hidden_as_empty(self):
        with patch.object(storage, 'IO_RETRY_SECONDS', .04), patch.object(storage, '_open_read',
                side_effect=PermissionError(errno.EACCES, 'persistent denial', str(self.path))):
            with self.assertRaises(PermissionError):
                storage.read_json(self.path, default={})

    def test_failed_publish_preserves_old_data_and_cleans_temp(self):
        with patch.object(storage, 'IO_RETRY_SECONDS', .04), patch.object(storage.os, 'replace',
                side_effect=PermissionError(errno.EACCES, 'persistent denial', str(self.path))):
            with self.assertRaises(PermissionError):
                storage.atomic_json(self.path, {'version': 2})
        self.assertEqual(storage.read_json(self.path)['version'], 1)
        self.assertEqual(list(self.root.glob('*.partial')), [])

    def test_writer_waits_for_reader_and_lock_is_reusable(self):
        finished, entered, failures = threading.Event(), threading.Event(), []
        def writer():
            entered.set()
            try:
                storage.atomic_json(self.path, {'version': 2})
            except Exception as e:
                failures.append(e)
            finished.set()
        with storage._json_guard(self.path):
            worker = threading.Thread(target=writer)
            worker.start(); self.assertTrue(entered.wait(1))
            self.assertFalse(finished.wait(.12))
        worker.join(4)
        self.assertFalse(failures)
        self.assertTrue(finished.is_set())
        self.assertEqual(storage.read_json(self.path)['version'], 2)
        self.assertTrue((self.root / '.heartbeat.json.io.lock').exists())

    def test_missing_and_invalid_json_are_distinct(self):
        self.assertEqual(storage.read_json(self.root / 'missing.json', {}), {})
        self.path.write_bytes(b'{broken')
        with self.assertRaises(json.JSONDecodeError):
            storage.read_json(self.path)


if __name__ == '__main__':
    unittest.main(verbosity=2)
