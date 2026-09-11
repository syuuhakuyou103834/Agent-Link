"""Native cleanup errors retain ownership and block new model requests."""
import ctypes
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import uuid
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.protocol import RpcClient
from app.engine import NodeService
from app.storage import Settings

class CleanupFailures(unittest.TestCase):
    def exercise(self, failure):
        folder=ROOT/'test-output'/('cleanup-'+uuid.uuid4().hex)
        client=RpcClient([sys.executable,str(ROOT/'tests/mock_server.py'),'A',str(folder/'calls.jsonl')],folder)
        client.start()
        process=client.process
        group=client.process_job
        handle=group.handle
        target={'terminate':'TerminateJobObject','query':'QueryInformationJobObject','close':'CloseHandle'}[failure]
        try:
            with patch.object(group.api,target,return_value=0):
                ctypes.set_last_error(5)
                with self.assertRaisesRegex(RuntimeError,'执行进程组清理失败') as error: client.close()
                self.assertIsInstance(error.exception.__cause__,OSError)
            self.assertTrue(client.cleanup_pending)
            self.assertIs(client.process_job,group)
            self.assertEqual(group.handle,handle)
            with patch.object(client,'send',wraps=client.send) as send:
                with self.assertRaisesRegex(RuntimeError,'清理'):client.start()
                with self.assertRaisesRegex(RuntimeError,'清理'):
                    client.run_turn('old','blocked','A','000-A',{},lambda x:None,lambda:None)
                send.assert_not_called()
            events=[]
            node=NodeService(Settings(),folder/'node',lambda k,v:events.append((k,v)))
            node.connected=True;node.client=client
            node._admit_start({'request_id':'blocked','topic':'blocked','rounds':1})
            self.assertTrue(node.commands.empty())
            self.assertTrue(any(k=='error' and '清理' in v['message'] for k,v in events))
            client.close()
            self.assertFalse(client.cleanup_pending)
            self.assertIsNotNone(process.poll())
            self.assertIsNone(client.process_job)
            client.start();client.close()
            self.assertFalse((folder/'calls.jsonl').exists())
            (folder/'result.json').write_text(json.dumps({'failure':failure,'reported':str(error.exception),
                'retained_handle':int(handle),'no_model_requests':True,'admission_blocked':True,
                'old_server_pid':process.pid,'old_server_exited':True,'reconnect_after_verified_cleanup':True},
                ensure_ascii=False,indent=2),encoding='utf-8')
        finally:client.close()

    def test_terminate_failure(self):self.exercise('terminate')
    def test_query_failure(self):self.exercise('query')
    def test_close_failure(self):self.exercise('close')

    def test_wait_timeout_retains_handle_and_reports(self):
        from app.process_job import ProcessJob
        group=ProcessJob();handle=group.handle
        try:
            with patch.object(group,'active_processes',return_value=1), patch('app.process_job.time.monotonic',side_effect=[0,6]):
                with self.assertRaisesRegex(TimeoutError,'清理超时'):group.close()
            self.assertEqual(group.handle,handle)
        finally:group.close()

if __name__=='__main__':unittest.main(verbosity=2)
