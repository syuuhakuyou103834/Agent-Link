"""Cleanup failure owns a shared execution lease until verified disconnect."""
import json
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from test_system import SystemTests, until
from app.storage import FileLock

class CleanupAdmission(SystemTests):
    def exercise(self, failing_role):
        target=self.nodes[failing_role]
        client=target.client
        old_process=client.process
        old_job=client.process_job
        old_handle=old_job.handle
        calls=[]
        real_stop=client._stop_process
        def stop():
            try:
                return real_stop()
            finally:
                calls.append(threading.get_ident())
        real_turn=client.run_turn
        def failure(thread,prompt,*args):
            return real_turn(thread,prompt+' [AUTH]',*args)
        with patch.object(client,'_stop_process',side_effect=stop), \
             patch.object(client,'run_turn',side_effect=failure), \
             patch.object(old_job.api,'TerminateJobObject',return_value=0):
            self.nodes['A'].command('start',topic='cleanup admission failure',rounds=1)
            until(lambda: client.cleanup_pending)
            until(lambda: self.state()=='failed' and all(not n.active for n in self.nodes.values()))
            counts=[len(self.calls(r)) for r in ('A','B')]
            self.assertEqual(counts,[1,0] if failing_role=='A' else [1,1])
            self.assertIsNone(old_process.poll())
            self.assertIs(client.process_job,old_job)
            self.assertEqual(old_job.handle,old_handle)
            for lease in ('execution.lease',f'nodes/{failing_role}.lease'):
                with self.assertRaises(RuntimeError):FileLock(self.shared/lease).acquire()
            self.assertTrue(target.execution_lock)
            before_jobs=len(list((self.shared/'jobs').iterdir()))
            for role in ('A','B'):
                start=len(self.events[role])
                self.nodes[role].command('start',topic='must reject',rounds=1)
                until(lambda r=role,s=start:any(k=='error' and ('清理' if r=='A' else '只有 A') in v['message'] for k,v in self.events[r][s:]))
                self.assertEqual(len(list((self.shared/'jobs').iterdir())),before_jobs)
            self.assertEqual([len(self.calls(r)) for r in ('A','B')],counts)
            # Disconnect fails too, preserving the client, node role lease and execution lease.
            start=len(calls)
            target.command('disconnect')
            until(lambda:len(calls)>start)
            until(lambda:client.cleanup_pending)
            self.assertIs(target.client,client)
            self.assertTrue(target.connected)
        target.command('disconnect')
        until(lambda:not target.connected and target.status=='offline' and not target.locks)
        self.assertIsNotNone(old_process.poll())
        self.assertIsNone(target.execution_lock)
        self.assertEqual(target.locks,[])
        self.assertEqual(set(calls),{target.thread.ident})
        with FileLock(self.shared/'execution.lease'):pass
        target.command('connect')
        until(lambda:target.connected and target.status=='idle')
        time.sleep(1.1)  # next owner heartbeat must be visible to both service loops
        self.nodes['A'].command('start',topic='legal request after verified cleanup',rounds=1)
        until(lambda:self.state()=='completed')
        until(lambda:all(not n.active for n in self.nodes.values()))
        self.assertEqual([len(self.calls(r)) for r in ('A','B')],[counts[0]+2,counts[1]+1])
        (self.root/'cleanup-admission-result.json').write_text(json.dumps({
            'failing_role':failing_role,'old_counts':counts,'new_counts':[2,1],
            'old_server_pid':old_process.pid,'old_server_alive_after_failed_cleanup':True,
            'old_server_exited_after_retry':True,'shared_execution_lease_retained':True,
            'role_lease_retained':True,'both_nodes_rejected_before_new_job':True,
            'cleanup_thread_ids':calls,'service_thread_id':target.thread.ident,
            'scope':'two local service threads and real mock server processes, no SMB or real model'},
            ensure_ascii=False,indent=2),encoding='utf-8')

    def test_initiator_cleanup_failure_blocks_both_then_recovers(self):self.exercise('A')
    def test_receiver_cleanup_failure_blocks_both_then_recovers(self):self.exercise('B')

if __name__=='__main__':
    suite=unittest.TestSuite(CleanupAdmission(n) for n in CleanupAdmission.__dict__ if n.startswith('test_'))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(not result.wasSuccessful())
