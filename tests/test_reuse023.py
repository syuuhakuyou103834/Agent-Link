"""Real local services/mocks: fail after receipt, explicitly resume without repeat calls."""
import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from test_conversation import ConversationTests
from test_system import until
from fixture_paths import fs

class ReuseTests(ConversationTests):
    # Reuse the harness, not all inherited test methods.
    def test_text_post_receipt_failure_reuses_original(self):
        self.reuse_formal(False)
    def test_project_post_receipt_failure_reuses_original(self):
        self.reuse_formal(True)
    def test_changed_source_cannot_receive_old_result(self):
        self.reuse_formal(True,True)
    def reuse_formal(self,code,mutate=False):
        node=self.nodes['A'];original=node._cache_received_result;injected=[]
        def cache(job,step,result,**kwargs):
            value=original(job,step,result,**kwargs)
            if step=='000-A' and not injected:
                injected.append(job);raise OSError('injected after durable receipt')
            return value
        node._cache_received_result=cache
        if code:
            project=self.root/'source023';fs(project).mkdir();fs(project/'x.py').write_text('print(1)')
            self.ready('只读审查，不修改源码\n'+str(project))
        else:self.ready('请讨论 Unicode 任务')
        self.send('开始');until(lambda:self.phase()=='interrupted',40)
        until(lambda:all(not n.active for n in self.nodes.values()))
        before=len(self.calls('A'));self.assertEqual(before,2)
        if mutate:fs(project/'x.py').write_text('print(2)')
        node._cache_received_result=original;self.send('继续')
        until(lambda:self.phase() in ('completed','needs_user_decision') or len(self.conv()['jobs'])>1 and self.phase()=='interrupted',50)
        if mutate:
            self.assertEqual(self.phase(),'interrupted');self.assertEqual(len(self.calls('A')),2);self.assertEqual(len(self.calls('B')),0)
            self.assertIn('关联证明',self.conv().get('error',''));return
        self.assertEqual(self.phase(),'completed',self.conv().get('error'))
        self.assertEqual(len(self.calls('A')),3,'Only final summary adds one call; initial result is reused')
        self.assertEqual(len(self.calls('B')),1)
    def test_chat_post_receipt_failure_reuses_original(self):
        node=self.nodes['A'];original=node._cache_received_result;injected=[]
        def cache(job,step,result):
            value=original(job,step,result)
            if step.startswith('chat-') and not injected:injected.append(step);raise OSError('injected after chat receipt')
            return value
        node._cache_received_result=cache;self.send('请讨论 Unicode 任务')
        until(lambda:self.phase()=='chat_interrupted',30);until(lambda:node.chat_active is None)
        self.assertEqual(len(self.calls('A')),1)
        node._cache_received_result=original;self.send('继续')
        until(lambda:self.phase()=='awaiting_confirmation',30)
        self.assertEqual(len(self.calls('A')),1,'Explicit resume uses original clarification with no additional request')

    def test_chat_committed_message_is_not_duplicated_on_receipt_error(self):
        node=self.nodes['A'];original=node._save_chat_attempt;injected=[]
        def save(identifier,attempt):
            if attempt['status']=='completed' and not injected:
                injected.append(attempt['id']);raise OSError('after message commit')
            return original(identifier,attempt)
        node._save_chat_attempt=save;self.send('请讨论 Unicode 任务')
        until(lambda:self.phase()=='chat_interrupted',30);until(lambda:node.chat_active is None)
        before=sum(m.get('kind')=='clarification' for m in self.conv()['messages'])
        self.assertEqual(before,1);node._save_chat_attempt=original;self.send('继续')
        until(lambda:self.phase()=='awaiting_confirmation',30)
        self.assertEqual(sum(m.get('kind')=='clarification' for m in self.conv()['messages']),before)
        self.assertEqual(len(self.calls('A')),1)

if __name__=='__main__':
    names=['test_text_post_receipt_failure_reuses_original','test_project_post_receipt_failure_reuses_original','test_chat_post_receipt_failure_reuses_original','test_changed_source_cannot_receive_old_result','test_chat_committed_message_is_not_duplicated_on_receipt_error']
    result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(ReuseTests(n) for n in names))
    raise SystemExit(0 if result.wasSuccessful() else 1)
