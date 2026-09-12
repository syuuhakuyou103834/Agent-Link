"""An unsuccessful version check cannot discard the original unsent message."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from test_conversation_guards import Guards
from app.conversation import append_message
import unittest

class ResumeGuard(Guards):
    def test_context_upgrade_check_keeps_original_pending(self):
        cid=self.node.conversations.create('旧任务')['id']
        with self.node.conversations.edit(cid) as c:
            c.update(phase='chat_interrupted',paused_from='working',job='20260912-000000-'+'b'*32,
                     error='本轮上下文超过传输上限，未发送模型请求。')
            m=append_message(c,'user','原 B 补充必须保留','input',origin='B',target='B')
            c['pending']=[m['id']]
        def incompatible():raise ValueError('需要双方升级至 0.3.18')
        self.node._unified_compatible=incompatible
        for _ in range(2):
            self.node.unified_submit('继续',cid)
            self.assertTrue(self.node._consume_unified_input(self.node.conversations.get(cid)))
            c=self.node.conversations.get(cid)
            self.assertEqual(c['phase'],'context_blocked')
            self.assertTrue(self.node._is_context_blocked(c))
            self.assertEqual(c['pending'],[m['id']])
            self.assertEqual(c['paused_from'],'working')
            self.assertFalse(c['attempts'])
            self.assertIn('原消息保留',c['error'])

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite([ResumeGuard('test_context_upgrade_check_keeps_original_pending')]))
    sys.exit(not result.wasSuccessful())
