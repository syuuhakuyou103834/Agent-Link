from fixture_paths import FixtureTemporaryDirectory
from fixture_paths import fs, entries
import copy,json,sys,tempfile,unittest,uuid
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.engine import NodeService
from app.storage import Settings,Mailbox
from app.conversation import validate_brief,user_directories,round_count,fingerprint

class Guards(unittest.TestCase):
    def setUp(self):
        self.temp=FixtureTemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.node=NodeService(Settings(shared_root=str(self.root/'share')),self.root/'A',lambda *a:None)
        self.node.box=Mailbox(self.root/'share',self.root/'A');self.node.box.connect();self.node.connected=True
        self.node.client=SimpleNamespace(cleanup_pending=False,process=None)
        self.brief=dict(goal='限定问题',directory='',permission='discuss',allowed_changes='无',acceptance=['核查回答'],review_focus='核查',round_limit=3)

    def test_unmentioned_directory_rejected(self):
        p=self.root/'project';fs(p).mkdir()
        with self.assertRaisesRegex(ValueError,'未由 A'):
            validate_brief(dict(self.brief,directory=str(p),permission='edit'),[])
        self.assertEqual(validate_brief(dict(self.brief,directory=str(p),permission='edit'),[str(p)])['directory'],str(p))

    def test_only_A_user_can_nominate_directory(self):
        p=self.root/'项目 with space';fs(p).mkdir()
        messages=[dict(speaker='B',origin='B',text=str(p)),dict(speaker='user',origin='B',text=str(p))]
        self.assertEqual(user_directories(messages),[])
        messages.append(dict(speaker='user',origin='A',text='目录：`'+str(p)+'`'))
        self.assertEqual(user_directories(messages),[str(p)])

    def test_confirm_cannot_approve_later_brief(self):
        cid=self.node.unified_submit('开始')
        with self.node.conversations.edit(cid) as c:c.update(phase='awaiting_confirmation',brief=self.brief)
        self.node._consume_unified_input(self.node.conversations.get(cid))
        c=self.node.conversations.get(cid)
        self.assertIsNone(c['confirmed']);self.assertEqual(c['phase'],'awaiting_confirmation');self.assertFalse(c['pending'])

    def test_confirm_digest_matches_exact_brief(self):
        cid=self.node.conversations.create('任务')['id']
        with self.node.conversations.edit(cid) as c:c.update(phase='awaiting_confirmation',brief=self.brief)
        self.node.unified_submit('开始',cid)
        with self.node.conversations.edit(cid) as c:c['brief']['goal']='变更目标'
        self.node._consume_unified_input(self.node.conversations.get(cid))
        self.assertIsNone(self.node.conversations.get(cid)['confirmed'])
        self.node.unified_submit('开始',cid);self.node._consume_unified_input(self.node.conversations.get(cid))
        c=self.node.conversations.get(cid);self.assertEqual(c['phase'],'waiting_peer')
        self.assertEqual(c['confirmation']['brief_sha256'],fingerprint(c['confirmed']))

    def test_partial_B_and_summary_do_not_count(self):
        a=dict(index=0,phase='implement',status='completed')
        b=dict(index=1,phase='review',status='running')
        self.assertEqual(round_count([a,b]),0)
        b['status']='completed'
        self.assertEqual(round_count([a,b,dict(index=2,phase='summary',status='completed')]),1)

    def test_stale_pending_attempt_requires_explicit_resume(self):
        cid=self.node.unified_submit('某任务')
        with self.node.conversations.edit(cid) as c:
            c['attempts'].append(dict(id=uuid.uuid4().hex,role='A',message_id=c['pending'][0],status='send_pending',instance='old'))
        self.assertTrue(self.node._consume_unified_input(self.node.conversations.get(cid)))
        c=self.node.conversations.get(cid);self.assertEqual(c['phase'],'chat_interrupted')
        self.assertFalse(self.node._consume_unified_input(c))

    def test_waiting_confirmation_survives_new_service(self):
        cid=self.node.conversations.create('任务')['id']
        with self.node.conversations.edit(cid) as c:c.update(phase='waiting_peer',confirmed=self.brief)
        other=NodeService(self.node.settings,self.node.data,lambda *a:None)
        c=other.conversations.get(cid)
        self.assertEqual(c['phase'],'waiting_peer');self.assertEqual(c['confirmed'],self.brief)

    def test_noop_read_does_not_republish(self):
        cid=self.node.conversations.create('任务')['id'];p=self.node.conversations.path(cid)
        self.node.conversations.get(cid);stamp=fs(p).stat().st_mtime_ns
        with self.node.conversations.edit(cid):pass
        self.assertEqual(fs(p).stat().st_mtime_ns,stamp)

if __name__=='__main__':unittest.main(verbosity=2)
