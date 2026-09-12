"""Regression through NodeService + subprocess mock, including 0.3.17 upgrade recovery."""
import copy
import json
from pathlib import Path
import sys
import time
from unittest import TestSuite, TextTestRunner
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from test_conversation import ConversationTests
from test_system import until
from app.engine import NodeService
from app.storage import read_json
from app.context_view import FEATURE


class ContextWorkflowTests(ConversationTests):
    def block_formal(self, role, summary_only=False):
        node=self.nodes[role];original=node._model_context
        enabled=[True]
        def context(value, settings=None):
            text=original(value,settings)
            if enabled[0] and node.active and (not summary_only or value['completed_rounds']>=1):
                text+='X'*280001
            return text
        node._model_context=context
        return enabled

    def test_context_large_tools_real_send_path_and_evidence_scope(self):
        project=self.root/'project';project.mkdir();(project/'main.py').write_text('print(1)')
        self.ready('[LARGE_TOOLS] 只读审查\n'+str(project));self.finish()
        c=self.conv()
        self.assertGreater(len(json.dumps(c['messages'],ensure_ascii=False)),280000)
        self.assertEqual([len(self.calls(r)) for r in ('A','B')],[3,1])
        self.assertEqual(c['completed_rounds'],1)
        for role in ('A','B'):
            for call in self.calls(role):
                self.assertNotIn('RAW-LARGE-TOOL',call['prompt'])
                rules=next(iter(call['thread_params']['config']['permissions'].values()))['filesystem']
                roots=[Path(k) for k,v in rules.items() if 'context-evidence' in k and v=='read']
                self.assertEqual(len(roots),1)
                self.assertTrue(roots[0].is_relative_to(self.root/role))
                self.assertTrue((roots[0]/'index.json').is_file())
        # B receives full A tool records in its local evidence; never direct A source access.
        index=read_json(next((self.root/'B'/'context-evidence').glob('*/*/index.json')))
        self.assertTrue(any(e.get('turn') for e in index['entries']))

    def test_context_text_formal_guard_is_before_claim_and_request(self):
        enabled=self.block_formal('A');self.ready();self.send('开始')
        until(lambda:self.phase()=='context_blocked')
        job=self.conv()['job'];self.assertFalse(list(self.job().glob('*.claim')))
        self.assertFalse(list(self.job().glob('call-*.json')))
        self.assertEqual([len(self.calls(r)) for r in ('A','B')],[1,0])
        time.sleep(.5);self.assertEqual(self.phase(),'context_blocked')
        self.assertFalse(self.conv()['context_error']['request_sent'])
        enabled[0]=False;self.send('继续')
        until(lambda:self.phase()=='completed',35)
        self.assertEqual(self.conv()['job'],job)
        self.assertEqual([len(self.calls(r)) for r in ('A','B')],[3,1])

    def test_context_code_formal_guard_is_before_claim_and_request(self):
        enabled=self.block_formal('B')
        project=self.root/'project';project.mkdir();(project/'main.py').write_text('print(1)')
        self.ready('只读审查\n'+str(project));self.send('开始')
        until(lambda:self.phase()=='context_blocked',35)
        job=self.conv()['job'];a=(self.job()/'turn-000-A.json').read_bytes()
        self.assertFalse((self.job()/'001-B.claim').exists());self.assertFalse(self.calls('B'))
        enabled[0]=False;self.send('继续','B')
        until(lambda:self.phase()=='completed',35)
        self.assertEqual(self.conv()['job'],job)
        self.assertEqual((self.job()/'turn-000-A.json').read_bytes(),a)
        self.assertEqual([len(self.calls(r)) for r in ('A','B')],[3,1])

    def test_context_chat_preserves_unsent_message_on_resume(self):
        node=self.nodes['A'];original=node._model_context;enabled=[True]
        node._model_context=lambda v,s=None:original(v,s)+('X'*280001 if enabled[0] else '')
        self.send('原要求必须完整保留 PENDING-18')
        until(lambda:self.phase()=='context_blocked')
        before=self.conv();pending=before['pending'][0]
        self.assertFalse(self.calls('A'));self.assertFalse(before['attempts'])
        enabled[0]=False;self.send('继续')
        until(lambda:self.phase()=='awaiting_confirmation',25)
        c=self.conv();self.assertFalse(c['pending']);self.assertEqual(len(self.calls('A')),1)
        current=json.JSONDecoder().raw_decode(self.calls('A')[0]['prompt'].split('\n当前消息：\n')[1])[0]
        self.assertEqual(current['id'],pending);self.assertIn('PENDING-18',current['text'])
        self.assertEqual(c['completed_rounds'],0);self.assertEqual(len(c['context_recoveries']),1)

    def legacy_upgrade(self, resume_role):
        self.block_formal('A',summary_only=True)
        project=self.root/'project';project.mkdir();(project/'main.py').write_text('print(1)')
        self.ready('[LARGE_TOOLS] 只读审查\n'+str(project));self.send('开始')
        until(lambda:self.phase()=='context_blocked',35)
        self.assertEqual(self.conv()['completed_rounds'],1)
        self.send('B 原补充：在本地验证想法 PENDING-B-18','B')
        until(lambda:bool(self.conv()['pending']))
        old=self.conv()['job'];old_path=self.shared/'jobs'/old
        frozen={p.name:p.read_bytes() for p in old_path.glob('turn-*.json')}
        cid=self.conv()['id']
        for node in self.nodes.values():node.stop()
        for node in self.nodes.values():node.thread.join(15);self.assertFalse(node.thread.is_alive())
        with self.nodes['A'].conversations.edit(cid) as c:
            c.update(phase='chat_interrupted',paused_from='working',error='本轮上下文超过传输上限，未截断、未发送模型请求。请缩小议题或整理交接摘要。')
            c.pop('error_code',None);c.pop('context_error',None)
        for role in ('A','B'):
            previous=self.nodes[role]
            self.nodes[role]=NodeService(previous.settings,previous.data,previous.emit,previous.command_override)
            self.nodes[role].start()
        until(lambda:all(n.connected for n in self.nodes.values()))
        time.sleep(.5)
        self.assertEqual([len(self.calls(r)) for r in ('A','B')],[2,1],'upgrade must not auto resend')
        self.send('继续',resume_role)
        until(lambda:self.phase()=='completed',40)
        c=self.conv();self.assertEqual(len(c['jobs']),2);self.assertNotEqual(c['job'],old)
        self.assertEqual([len(self.calls(r)) for r in ('A','B')],[3,2],'A implement and B review each once')
        self.assertEqual(c['completed_rounds'],1);self.assertFalse(c['pending'])
        self.assertEqual({p.name:p.read_bytes() for p in old_path.glob('turn-*.json')},frozen)
        bchat=self.calls('B')[-1]
        current=json.JSONDecoder().raw_decode(bchat['prompt'].split('\n当前消息：\n')[1])[0]
        self.assertIn('PENDING-B-18',current['text']);self.assertEqual(current['target'],'B')
        self.assertIn('PENDING-B-18',self.calls('A')[-1]['prompt'])
        self.assertNotIn('RAW-LARGE-TOOL',self.calls('A')[-1]['prompt'])

    def test_context_legacy_upgrade_A_resumes_B_pending(self):self.legacy_upgrade('A')
    def test_context_legacy_upgrade_B_resumes_B_pending(self):self.legacy_upgrade('B')

    def test_context_old_peer_feature_refused_before_job(self):
        self.ready()
        self.nodes['B']._heartbeat=lambda **kwargs:None
        # A valid live-looking old capability receipt; compatibility must still fail.
        from app.storage import atomic_json, now
        p=self.shared/'nodes'/'B.json';peer=read_json(p)
        peer['features']=[f for f in peer['features'] if f!=FEATURE];peer['updated']=now()
        atomic_json(p,peer)
        with self.assertRaisesRegex(ValueError,'0.3.18'):self.nodes['A']._unified_compatible()
        self.assertIsNone(self.job());self.assertFalse(self.calls('B'))


if __name__=='__main__':
    result=TextTestRunner(verbosity=2).run(TestSuite(ContextWorkflowTests(n) for n in dir(ContextWorkflowTests) if n.startswith('test_context_')))
    sys.exit(not result.wasSuccessful())
