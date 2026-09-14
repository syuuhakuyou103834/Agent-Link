from fixture_paths import fs, entries
"""Fail-closed containment setup and repeated start/close on Windows."""
import ctypes
from ctypes import wintypes
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch
import uuid
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.protocol import RpcClient
from app.process_job import ProcessJob

class ProcessJobTests(unittest.TestCase):
    def test_server_code_cannot_run_before_job_assignment(self):
        folder = __import__('fixture_paths').output_root() / ('job-' + uuid.uuid4().hex)
        fs(folder).mkdir(parents=True)
        marker = folder/'started.txt'
        script = folder/'server.py'
        fs(script).write_text('from pathlib import Path\nimport runpy,sys\n'
            + 'Path(' + repr(str(marker)) + ').write_text("started")\n'
            + 'sys.argv=' + repr([str(ROOT/'tests/mock_server.py'),'A',str(folder/'calls.jsonl')])
            + '\nrunpy.run_path(sys.argv[0],run_name="__main__")\n', encoding='utf-8')
        client = RpcClient([sys.executable,str(script)],folder/'logs')
        original = ProcessJob.assign
        def delayed_assign(job,process):
            time.sleep(.3)
            self.assertFalse(fs(marker).exists())
            original(job,process)
        try:
            with patch.object(ProcessJob,'assign',delayed_assign): client.start()
            self.assertTrue(fs(marker).exists())
        finally:
            client.close()

    def test_assignment_failure_sends_no_initialize_and_closes_process(self):
        folder = __import__('fixture_paths').output_root() / ('job-' + uuid.uuid4().hex)
        client = RpcClient([sys.executable, str(ROOT/'tests/mock_server.py'), 'A', str(folder/'calls.jsonl')], folder)
        with patch.object(ProcessJob, 'assign', side_effect=OSError('injected ownership failure')):
            with patch.object(client, 'send', wraps=client.send) as send:
                with self.assertRaisesRegex(OSError, 'ownership failure'):
                    client.start()
                send.assert_not_called()
        self.assertIsNone(client.process)
        self.assertIsNone(client.process_job)
        self.assertIsNone(client.log)
        self.assertFalse((fs(folder/'calls.jsonl')).exists())

    def test_repeated_start_close_releases_job_handles(self):
        api = ctypes.WinDLL('kernel32')
        api.GetCurrentProcess.restype = wintypes.HANDLE
        api.GetProcessHandleCount.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        def count():
            value = wintypes.DWORD()
            assert api.GetProcessHandleCount(api.GetCurrentProcess(), ctypes.byref(value))
            return value.value
        folder = __import__('fixture_paths').output_root() / ('job-' + uuid.uuid4().hex)
        client = RpcClient([sys.executable, str(ROOT/'tests/mock_server.py'), 'A', str(folder/'calls.jsonl')], folder)
        client.start(); client.close()
        before = count()
        for _ in range(20):
            client.start()
            process = client.process
            client.close(); client.close()
            self.assertIsNotNone(process.poll())
            self.assertIsNone(client.process_job)
            del process
        self.assertLessEqual(count(), before + 2)

if __name__ == '__main__':
    unittest.main(verbosity=2)
