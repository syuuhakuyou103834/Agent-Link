from fixture_paths import fs, entries
"""Controlled in-flight fixture and real local discussion lease; no hard crash or SMB."""
import json
from pathlib import Path
import sys
import threading
import time
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from test_repairs import RepairComponentTests, Fixture
from app.engine import NodeService, SAFETY_FEATURE
from app.storage import Settings, FileLock, atomic_json, read_json

class AuthorityTests(RepairComponentTests):
    def authority_window(self, fault):
        self.client.block=True
        # Use the actual initiator loop to acquire and own discussion.lease.
        atomic_json(self.box.root/'nodes/B-owner.json', {'role':'B','instance':self.node.instance})
        worker=threading.Thread(target=self.node.run_initiator,args=('held old model request',1))
        worker.start()
        try:
            self.assertTrue(self.client.entered.wait(5))
            old=self.node.active.copy()
            own_path=self.box.root/'nodes/B.json'
            atomic_json(own_path,dict(read_json(own_path),status='running',updated=time.time()))
            path=self.box.root/'nodes/A.json'
            peer=read_json(path)
            if fault=='stale':
                self.node.liveness.last_progress -= 31
            elif fault=='role_lock_lost':
                self.peer_locks[0].close()
            elif fault=='instance_replaced':
                atomic_json(self.box.root/'nodes/A-owner.json',{'role':'A','instance':'c'*32})
                atomic_json(path,dict(peer,instance='c'*32))
            elif fault=='executor_role_lock_lost':
                self.peer_locks[1].close()
            elif fault=='executor_instance_replaced':
                self.peer_locks[1].close()
                replacement=FileLock(self.box.root/'nodes/B.lease').acquire()
                self.peer_locks.append(replacement)
                atomic_json(self.box.root/'nodes/B-owner.json',{'role':'B','instance':'c'*32})
                atomic_json(own_path,dict(read_json(own_path),instance='c'*32))
            # A separate service sees a fresh B peer, so rejection must come from
            # execution ownership, not merely the failed peer compatibility gate.
            events=[]
            contender_role='B' if fault.startswith('executor_') else 'A'
            contender=NodeService(Settings(role=contender_role,shared_root=str(self.box.root)),
                self.root/'contender',lambda k,v:events.append((k,v)))
            contender.box,contender.connected=self.box,True
            contender.client=Fixture(self.root/'contender')
            __import__("liveness_fixture").respond(contender)
            contender._check_peer_compatibility()
            contender._admit_start({'request_id':'challenger-'+fault,'topic':'must not take over','rounds':1})
            self.assertTrue(worker.is_alive())
            self.assertTrue(contender.commands.empty())
            self.assertEqual(len(list(entries(self.box.root/'jobs','iterdir'))),1)
            self.assertEqual(contender.client.calls,[])
            self.assertTrue(any(k=='error' and '冲突' in v['message'] for k,v in events))
            with self.assertRaises(RuntimeError):
                FileLock(self.box.root/'discussion.lease').acquire()
            # Explicit terminal fence while the old response remains held.
            contender._edit_control(old['id'],'cancel','')
            before=(fs(self.box.job(old['id'])/'state.json')).read_bytes()
            contender._admit_start({'request_id':'after-fence-'+fault,'topic':'still held','rounds':1})
            self.assertTrue(contender.commands.empty())
            self.assertTrue(worker.is_alive())
            self.client.release.set()
            worker.join(5)
            self.assertFalse(worker.is_alive())
            self.assertEqual((fs(self.box.job(old['id'])/'state.json')).read_bytes(),before)
            self.assertFalse((fs(self.box.job(old['id'])/'turn-000-B.json')).exists())
            self.assertFalse((fs(self.box.job(old['id'])/'request-001-A.json')).exists())
            self.assertEqual(len(self.client.calls),1)
            with FileLock(self.box.root/'discussion.lease'):
                pass
            (fs(self.root/'authority-result.json')).write_text(json.dumps({
                'fault':fault,'old_job':old['id'],'old_requests':1,'contender_requests':0,
                'worker_alive_during_both_rejections':True,'discussion_lease_held_until_worker_exit':True,
                'late_result_rejected':True,'terminal_unchanged':True,
                'layer':'local service loop, in-process blocked mock, filesystem locks; no process crash',
                'contender_events':events},ensure_ascii=False,indent=2),encoding='utf-8')
        finally:
            self.client.release.set()
            worker.join(5)

    def test_T12_stale_peer_does_not_release_inflight_discussion(self):
        self.authority_window('stale')
    def test_T12_peer_role_lock_lost_does_not_release_inflight_discussion(self):
        self.authority_window('role_lock_lost')
    def test_T12_peer_instance_replaced_does_not_release_inflight_discussion(self):
        self.authority_window('instance_replaced')
    def test_T12_executor_role_lock_lost_does_not_release_inflight_discussion(self):
        self.authority_window('executor_role_lock_lost')
    def test_T12_executor_instance_replaced_does_not_release_inflight_discussion(self):
        self.authority_window('executor_instance_replaced')

if __name__=='__main__':
    suite=unittest.TestSuite(AuthorityTests(n) for n in AuthorityTests.__dict__ if n.startswith('test_'))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(not result.wasSuccessful())
