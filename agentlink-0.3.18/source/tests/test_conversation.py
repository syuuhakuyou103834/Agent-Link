"""Real NodeService threads and App Server subprocess mocks; no model requests."""
import json
from pathlib import Path
import sys
import time
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from test_system import SystemTests, until
from app.storage import read_json
from app.conversation import Conversations, round_count


class ConversationTests(SystemTests):
    def conv(self):
        values=Conversations(self.shared,self.root/'A').list()
        return values[0] if values else None

    def phase(self):
        v=self.conv();return v['phase'] if v else None

    def send(self,text,role='A'):
        v=self.conv()
        self.nodes[role].command('chat',text=text,conversation_id=v['id'] if v else None)

    def ready(self,text='请讨论 Unicode 任务'):
        self.send(text)
        until(lambda:self.phase() in ('awaiting_confirmation','chat_interrupted'),25)
        self.assertEqual(self.phase(),'awaiting_confirmation',self.conv().get('error'))

    def finish(self):
        self.send('开始')
        until(lambda:self.phase() in ('completed','needs_user_decision','interrupted','chat_interrupted'),35)
        self.assertNotIn(self.phase(),('interrupted','chat_interrupted'),self.conv().get('error'))

    def test_unified_confirmation_and_one_round(self):
        self.ready()
        self.assertEqual([len(self.calls(r)) for r in ('A','B')],[1,0])
        self.assertIsNone(self.job())
        self.finish()
        self.assertEqual(self.conv()['completed_rounds'],1)
        self.assertEqual([len(self.calls(r)) for r in ('A','B')],[3,1])
        for role in ('A','B'):
            for call in self.calls(role):
                profile=next(iter(call['thread_params']['config']['permissions'].values()))
                self.assertNotIn('write',profile['filesystem'].values())
        self.assertEqual(self.phase(),'completed')

    def test_unified_A_only_and_no_duplicate_submit(self):
        self.send('B 尝试创建任务','B');time.sleep(.3)
        self.assertIsNone(self.conv());self.assertFalse(self.calls('B'))
        self.assertFalse(self.nodes['B'].command('start',topic='禁止',rounds=1))
        self.nodes['A'].command('chat',text='请讨论同一任务',conversation_id=None,message_id='idempotent')
        until(lambda:self.conv() is not None)
        cid=self.conv()['id']
        self.nodes['A'].command('chat',text='请讨论同一任务',conversation_id=cid,message_id='idempotent')
        until(lambda:self.phase()=='awaiting_confirmation')
        self.assertEqual(sum(m['speaker']=='user' for m in self.conv()['messages']),1)

    def test_unified_offline_B_clarifies_then_waits(self):
        self.nodes['B'].command('disconnect');until(lambda:not self.nodes['B'].connected)
        self.ready();self.send('开始');until(lambda:self.phase()=='waiting_peer')
        time.sleep(.5);self.assertEqual(len(self.calls('A')),1);self.assertIsNone(self.job())
        self.nodes['B'].command('connect')
        until(lambda:self.phase() in ('completed','interrupted'),35)
        self.assertEqual(self.phase(),'completed',self.conv().get('error'))

    def test_unified_code_review_readonly_full_snapshot(self):
        project=self.root/'review-src';project.mkdir();(project/'中文.py').write_text('print(1)',encoding='utf-8')
        self.ready('只读审查，不改代码\n'+str(project));self.finish()
        meta=read_json(self.job()/'meta.json');self.assertEqual(meta['task_brief']['permission'],'review')
        a=self.calls('A')[1]
        rules=next(iter(a['thread_params']['config']['permissions'].values()))['filesystem']
        self.assertEqual(rules[str(project)],'read')
        self.assertEqual((project/'中文.py').read_text(encoding='utf-8'),'print(1)')
        b=self.calls('B')[0];b_rules=next(iter(b['thread_params']['config']['permissions'].values()))['filesystem']
        self.assertNotIn(str(project),b_rules)
        self.assertTrue(list(self.job().glob('artifacts/*/source.zip')))

    def test_unified_edit_permissions_and_round_upper_bound(self):
        project=self.root/'edit-src';project.mkdir();(project/'main.py').write_text('print(1)')
        self.ready('[EDIT] [NEEDS_CHANGES] 4轮\n'+str(project));self.finish()
        self.assertEqual(self.phase(),'needs_user_decision')
        self.assertEqual(self.conv()['completed_rounds'],4)
        self.assertEqual(len(self.calls('A'))+len(self.calls('B')),10)
        rules=next(iter(self.calls('A')[1]['thread_params']['config']['permissions'].values()))['filesystem']
        self.assertEqual(rules[str(project)],'write')

    def test_unified_two_rounds_and_followup_context(self):
        self.ready('[TWO_ROUNDS] 讨论两轮');self.finish()
        self.assertEqual(self.conv()['completed_rounds'],2)
        self.send('再解释一下之前的结论')
        until(lambda:self.phase()=='awaiting_confirmation')
        self.assertIn('模拟最终总结',self.calls('A')[-1]['prompt'])

    def test_unified_B_post_complete_review_does_not_restart_A(self):
        self.ready();self.finish();a=len(self.calls('A'));count=self.conv()['completed_rounds']
        self.send('[RELAY] 请记录建议以后修改','B')
        until(lambda:len(self.calls('B'))==2)
        until(lambda:not self.conv()['pending'])
        self.assertEqual(len(self.calls('A')),a)
        self.assertEqual(self.conv()['completed_rounds'],count)
        self.assertEqual(self.phase(),'completed')
        self.assertTrue(any(m['kind']=='relay' for m in self.conv()['messages']))

    def test_unified_chat_quota_explicit_resume_no_auto_retry(self):
        self.send('[CHAT_QUOTA] 请讨论问题')
        until(lambda:self.phase()=='chat_interrupted')
        time.sleep(.5);self.assertEqual(len(self.calls('A')),1)
        self.send('继续');until(lambda:self.phase()=='awaiting_confirmation',25)
        self.assertEqual(len(self.calls('A')),2)
        self.assertEqual(self.calls('A')[0]['thread'],self.calls('A')[1]['thread'])

    def test_unified_formal_quota_resumes_B_only(self):
        project=self.root/'quota-src';project.mkdir();(project/'main.py').write_text('print(1)')
        self.ready('[QUOTA_B_ONCE] 只读审查\n'+str(project));self.send('开始')
        until(lambda:self.phase()=='interrupted',35)
        old=self.conv()['job'];self.assertEqual(self.conv()['completed_rounds'],0)
        self.send('继续','B')
        until(lambda:self.phase() in ('completed','chat_interrupted') or len(self.conv()['jobs'])>1 and self.phase()=='interrupted',40)
        self.assertEqual(self.phase(),'completed',self.conv().get('error'))
        self.assertEqual(len(self.calls('A')),3,'clarify, implement once, summary')
        self.assertEqual(len(self.calls('B')),2)
        self.assertEqual(read_json(self.shared/'jobs'/old/'state.json')['status'],'failed')
        self.assertEqual(self.conv()['completed_rounds'],1)

    def test_unified_conflict_holds_next_step(self):
        self.ready('[SLOW] 请讨论问题');self.send('开始')
        until(lambda:self.nodes['A'].active is not None)
        self.send('[CONFLICT] 新要求与原要求矛盾')
        until(lambda:self.phase()=='conflict',25)
        before=len(self.calls('B'));time.sleep(.5)
        self.assertEqual(len(self.calls('B')),before)
        self.assertEqual(self.conv()['completed_rounds'],0)

    def test_unified_pause_cancel_no_late_resurrection(self):
        self.ready('[SLOW] 问题');self.send('开始');until(lambda:self.nodes['A'].active is not None)
        self.nodes['A'].command('conversation_control',conversation_id=self.conv()['id'],action='cancel')
        until(lambda:self.phase()=='cancelled')
        until(lambda:not self.nodes['A'].active)
        self.assertEqual(len(self.calls('B')),0)
        self.assertEqual(self.phase(),'cancelled')

    def test_unified_pause_resumes_via_same_input(self):
        self.ready('[SLOW] 暂停后继续');self.send('开始')
        until(lambda:self.nodes['A'].active is not None)
        self.nodes['A'].command('conversation_control',conversation_id=self.conv()['id'],action='pause')
        until(lambda:self.phase()=='paused')
        time.sleep(.5);self.assertEqual(len(self.calls('B')),0)
        self.send('继续')
        until(lambda:self.phase() in ('completed','interrupted'),35)
        self.assertEqual(self.phase(),'completed',self.conv().get('error'))
        self.assertEqual(self.conv()['completed_rounds'],1)

    def test_unified_cancelled_A_can_clarify_B_cannot_revive(self):
        self.ready();cid=self.conv()['id']
        self.nodes['A'].command('conversation_control',conversation_id=cid,action='cancel')
        until(lambda:self.phase()=='cancelled')
        self.send('新问题需要讨论')
        until(lambda:self.phase()=='awaiting_confirmation')
        self.assertEqual(len(self.calls('A')),2)
        self.assertIsNone(self.job())

    def test_unified_text_quota_recovery(self):
        self.ready('[QUOTA_B_ONCE] 普通任务');self.send('开始')
        until(lambda:self.phase()=='interrupted')
        self.send('继续','B')
        until(lambda:self.phase()=='completed',35)
        self.assertEqual([len(self.calls(r)) for r in ('A','B')],[3,2])
        self.assertEqual(self.conv()['completed_rounds'],1)


if __name__=='__main__':
    suite=unittest.TestSuite(ConversationTests(n) for n in dir(ConversationTests) if n.startswith('test_unified_'))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(not result.wasSuccessful())
