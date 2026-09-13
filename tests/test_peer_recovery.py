"""0.3.19 peer interruption and explicit recovery; local services and subprocess mocks only."""
import copy
import json
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from test_conversation import ConversationTests
from test_repairs import RepairComponentTests
from test_system import until
from app import engine
from app.storage import read_json, atomic_json
from app.interruption import TechnicalInterruption, PeerStateError, LEGACY_PREFIX, LEGACY_REASONS, legacy_peer_failure


class PeerComponents(RepairComponentTests):
    def test_stale_diagnostics_preserve_exact_origin_and_age(self):
        meta=self.ready();self.node.active=meta
        self.box.put(meta['id'],'state.json',{'status':'running','index':1})
        peer=read_json(self.box.root/'nodes/A.json')
        peer['updated']=time.time()-13
        self.node.liveness.last_progress-=31
        atomic_json(self.box.root/'nodes/A.json',peer)
        with self.assertRaises(TechnicalInterruption) as caught:self.node._control()
        self.node._failed(caught.exception)
        state=self.box.get(meta['id'],'state.json')
        self.assertEqual(state['status'],'failed')
        self.assertEqual(state['interruption']['origin'],'B')
        self.assertEqual(state['interruption']['code'],'peer_heartbeat_stale')
        self.assertGreaterEqual(state['interruption']['local_silence_seconds'],30)
        self.assertEqual(state['interruption']['request_state'],'not_sent')
        self.assertFalse(self.client.calls)

    def test_ui_and_execution_both_accept_clock_ahead_after_handshake(self):
        self.ready();peer=read_json(self.box.root/'nodes/A.json');peer['updated']=time.time()+2
        self.assertIsNone(self.node._peer_problem(peer))
        self.assertEqual(self.node._check_peer_compatibility(peer),peer['instance'])
        self.assertFalse(self.client.calls)

    def test_fresh_occupied_peer_is_accepted(self):
        self.ready();peer=read_json(self.box.root/'nodes/A.json')
        self.assertIsNone(self.node._peer_problem(peer))
        self.assertEqual(self.node._check_peer_compatibility(peer),peer['instance'])

    def test_no_late_error_overwrites_user_stop(self):
        meta=self.ready();self.node.active=meta
        self.node._edit_control(meta['id'],'cancel','')
        before=(self.box.job(meta['id'])/'state.json').read_bytes()
        self.node._failed(TechnicalInterruption('late peer failure',{'kind':'peer_unavailable'}))
        self.assertEqual((self.box.job(meta['id'])/'state.json').read_bytes(),before)


class PeerRecovery(ConversationTests):
    def fail_B_before_claim(self, legacy=False):
        b=self.nodes['B'];original=b._perform_code_owned
        def fail(request):
            b.execution_stage='receiving_snapshot'
            raise TechnicalInterruption('节点 B 暂停执行：合成心跳失效',
                                        {'origin':'B','peer':'A','code':'peer_heartbeat_stale','heartbeat_age_seconds':13})
        b._perform_code_owned=fail
        project=self.root/'source';project.mkdir();(project/'main.py').write_text('print(1)',encoding='utf-8')
        self.ready('只读审查，不改代码\n'+str(project));self.send('开始')
        until(lambda:self.phase()=='interrupted',40)
        until(lambda:not b.active)
        b._perform_code_owned=original
        parent=self.shared/'jobs'/self.conv()['job']
        self.assertEqual(len(self.calls('B')),0)
        self.assertFalse((parent/'001-B.claim').exists())
        self.assertEqual(read_json(parent/'state.json')['status'],'failed')
        if legacy:
            error=LEGACY_PREFIX+LEGACY_REASONS[0]
            atomic_json(parent/'B-error.json',dict(status='cancelled',message=error,time=time.time()))
            atomic_json(parent/'state.json',dict(status='cancelled',index=1,error=error,updated=time.time()))
            with self.nodes['A'].conversations.edit(self.conv()['id']) as c:c.update(phase='interrupted',error=error)
        before={name:(parent/name).read_bytes() for name in ('state.json','B-error.json','turn-000-A.json')}
        return parent,before

    def assert_resumed(self,parent,before):
        self.send('继续')
        until(lambda:self.phase()=='completed' or len(self.conv()['jobs'])>1 and self.phase()=='interrupted',45)
        self.assertEqual(self.phase(),'completed',self.conv().get('error'))
        self.assertEqual([len(self.calls(r)) for r in ('A','B')],[3,1], 'A clarify+initial+summary; B review once')
        self.assertEqual(self.conv()['completed_rounds'],1)
        self.assertEqual(len(self.conv()['jobs']),2)
        for name,raw in before.items():self.assertEqual((parent/name).read_bytes(),raw,name)
        child=self.shared/'jobs'/self.conv()['job']
        self.assertEqual(read_json(child/'turn-000-A.json')['inherited_from']['job_id'],parent.name)
        self.assertEqual(read_json(child/'meta.json')['recovery']['index'],1)

    def test_peer_new_interruption_waits_then_resumes_B_only(self):
        parent,before=self.fail_B_before_claim()
        time.sleep(.7)
        self.assertEqual(self.phase(),'interrupted');self.assertFalse(self.calls('B'))
        state=read_json(parent/'state.json')
        self.assertEqual(state['interruption']['request_state'],'not_sent')
        self.assertEqual(state['interruption']['stage'],'receiving_snapshot')
        self.assert_resumed(parent,before)

    def test_peer_legacy_cancelled_resumes_B_only_preserves_evidence(self):
        parent,before=self.fail_B_before_claim(legacy=True)
        meta=read_json(parent/'meta.json')
        self.assertIsNotNone(legacy_peer_failure(self.nodes['A'].box,meta))
        self.assert_resumed(parent,before)

    def test_peer_user_stop_after_legacy_interruption_prevents_resume(self):
        parent,before=self.fail_B_before_claim(legacy=True)
        self.nodes['A'].command('conversation_control',conversation_id=self.conv()['id'],action='cancel')
        until(lambda:self.phase()=='cancelled')
        self.send('继续');time.sleep(.7)
        self.assertEqual(self.phase(),'cancelled')
        self.assertEqual(len(self.conv()['jobs']),1)
        self.assertEqual([len(self.calls(r)) for r in ('A','B')],[2,0])
        self.assertFalse((parent/'recovery-child.json').exists())

    def test_peer_legacy_requires_matching_error_and_control_proof(self):
        parent,_=self.fail_B_before_claim(legacy=True);box=self.nodes['A'].box;meta=read_json(parent/'meta.json')
        original_control=read_json(parent/'control.json');original_error=read_json(parent/'B-error.json')
        for control in ({},dict(original_control,cancelled=True)):
            atomic_json(parent/'control.json',control)
            self.assertIsNone(legacy_peer_failure(box,meta))
            with self.assertRaises(ValueError):self.nodes['A'].prepare_recovery(parent.name,'B','继续',meta['project']['id'])
        atomic_json(parent/'control.json',original_control)
        atomic_json(parent/'B-error.json',dict(original_error,message='unrelated'))
        self.assertIsNone(legacy_peer_failure(box,meta))

    def test_peer_legacy_resume_after_both_services_restart(self):
        parent,before=self.fail_B_before_claim(legacy=True)
        from app.engine import NodeService
        old=dict(self.nodes)
        for n in old.values():n.stop()
        for n in old.values():n.thread.join(15);self.assertFalse(n.thread.is_alive())
        self.nodes={}
        for role,n in old.items():
            new=NodeService(n.settings,n.data,lambda k,v,r=role:self.events[r].append((k,v)),n.command_override)
            self.nodes[role]=new;new.start()
        until(lambda:all(n.connected for n in self.nodes.values()))
        self.assert_resumed(parent,before)

    def test_peer_sent_B_request_never_auto_retries_and_explicit_resume_reuses_thread(self):
        b=self.nodes['B'];original=b.client.run_turn;seen=[]
        def fail_after_result(*args,**kwargs):
            view=original(*args,**kwargs)
            if not seen:
                seen.append(view)
                raise TechnicalInterruption('模拟 B 请求发送后心跳失效',{'origin':'B','peer':'A','code':'peer_heartbeat_stale'})
            return view
        b.client.run_turn=fail_after_result
        project=self.root/'source';project.mkdir();(project/'main.py').write_text('print(1)')
        self.ready('只读审查\n'+str(project));self.send('开始')
        until(lambda:self.phase()=='interrupted',40)
        parent=self.shared/'jobs'/self.conv()['job']
        until(lambda:not b.active);time.sleep(.6)
        self.assertEqual(len(self.calls('B')),1)
        self.assertEqual(read_json(parent/'call-001-B.json')['status'],'interrupted_uncertain')
        self.assertNotEqual(read_json(parent/'state.json')['interruption']['request_state'],'not_sent')
        self.send('继续','B')
        until(lambda:self.phase()=='completed' or len(self.conv()['jobs'])>1 and self.phase()=='interrupted',45)
        self.assertEqual(self.phase(),'completed',self.conv().get('error'))
        self.assertEqual([len(self.calls(r)) for r in ('A','B')],[3,2])
        self.assertEqual(self.calls('B')[0]['thread'],self.calls('B')[1]['thread'])

if __name__=='__main__':
    suite=unittest.TestSuite()
    for cls in (PeerComponents,PeerRecovery):
        suite.addTests(cls(n) for n in cls.__dict__ if n.startswith('test_'))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(not result.wasSuccessful())
