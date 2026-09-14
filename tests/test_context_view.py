from fixture_paths import FixtureTemporaryDirectory
from fixture_paths import fs, entries
"""Bounded send views, immutable evidence and exact pre-send limits; no models."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.context import check_prompt, PromptBudgetError
from app.context_view import prepare, project, digest
from app.conversation import append_message
from app.storage import read_json, atomic_json


def sample():
    c=dict(id='conversation-'+'a'*32,messages=[],confirmed={'goal':'保留所有用户约束'},
           confirmation={'message_id':'confirmation-id','brief_sha256':'hash'},pending=[],phase='working',completed_rounds=1)
    append_message(c,'user','只读审查；不改变权限；中文 END','input',origin='A',target='A')
    for i,role in enumerate(('A','B')):
        turn=dict(role=role,answer='重复正文',blocks=[{'text':'重复正文'}],tools=[{'output':'RAW-TOOL-'+str(i)+'中'*11980} for _ in range(19)],
                  status='completed',step=f'{i:03d}-{role}',phase='implement' if i==0 else 'review')
        if i:turn['review']={'decision':'changes_requested'}
        append_message(c,role,'可读完整答复 '+str(i),'formal',job_id='job',step=turn['step'],turn=turn)
    m=append_message(c,'user','你作为B可以在本地验证想法','input',origin='B',target='B')
    c['pending'].append(m['id'])
    return c


class ContextViewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=FixtureTemporaryDirectory(prefix='al18-',dir=__import__('app.storage',fromlist=['io_path']).io_path(tempfile.gettempdir()));self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)

    def test_large_tools_are_files_and_original_is_unchanged(self):
        value=sample();before=copy.deepcopy(value)
        self.assertGreater(len(json.dumps(value,ensure_ascii=False)),280000)
        text,root,receipt=prepare(value,self.root)
        view=json.loads(text)
        self.assertLess(len(text),10000);self.assertNotIn('RAW-TOOL',text);self.assertNotIn('重复正文',text)
        self.assertEqual(value,before)
        self.assertEqual([m['text'] for m in view['messages']],[m['text'] for m in value['messages']])
        for field in ('pending','confirmed','confirmation','completed_rounds','phase'):
            self.assertEqual(view[field],value[field])
        index=read_json(root/'index.json');self.assertEqual(digest(index),receipt['index_sha256'])
        for entry in index['entries']:
            self.assertEqual(digest(read_json(root/entry['file'])),entry['sha256'])
            if entry.get('turn'):
                original=next(m['turn'] for m in value['messages'] if m['id']==entry['id'])
                self.assertEqual(read_json(root/entry['turn']['file']),original)
                self.assertEqual(digest(original),entry['turn']['sha256'])

    def test_each_node_reconstructs_local_evidence_not_peer_path(self):
        value=sample()
        a,ar,ra=prepare(value,self.root/'A');b,br,rb=prepare(value,self.root/'B')
        self.assertNotEqual(ar,br);self.assertEqual(ra['index_sha256'],rb['index_sha256'])
        self.assertNotIn(str(ar),b);self.assertIn(str(br).replace('\\','\\\\'),b)

    def test_changed_evidence_is_rejected_not_overwritten(self):
        value=sample();_,root,_=prepare(value,self.root)
        original=read_json(root/'index.json');atomic_json(root/'index.json',{'tampered':True})
        with self.assertRaisesRegex(ValueError,'被改动'):prepare(value,self.root)
        self.assertEqual(read_json(root/'index.json'),{'tampered':True})
        self.assertIn('entries',original)

    def test_old_answers_use_explicit_lossless_references(self):
        value=sample()
        # The old B changes_requested decision and all user text must stay inline.
        value['messages'][1]['text']='OLD-'+('长文本'*70000)+'-END'
        for i in range(5):append_message(value,'A','最近回答 '+str(i),'supplement')
        before=copy.deepcopy(value);text,root,receipt=prepare(value,self.root)
        message=json.loads(text)['messages'][1]
        self.assertFalse('text' in message);self.assertIn('archived_body',message)
        self.assertEqual(read_json(root/message['archived_body']['file'])['text'],before['messages'][1]['text'])
        self.assertEqual(receipt['archived_sequences'],[2]);self.assertEqual(value,before)
        self.assertIn('你作为B可以在本地验证想法',text);self.assertIn('changes_requested',text)

    def test_protected_huge_text_still_blocks_with_exact_metrics(self):
        for slot in (0,2,3):  # user requirement, unresolved review, pending user supplement
            with self.subTest(slot=slot):
                value=sample();value['messages'][slot]['text']='中'*280001
                with self.assertRaises(PromptBudgetError) as cm:prepare(value,self.root/str(slot))
                self.assertFalse(cm.exception.details['request_sent'])
                self.assertGreater(cm.exception.details['chars'],280000)
                self.assertTrue(list(entries(self.root/str(slot),'glob','*/index.json')))

    def test_character_and_json_byte_boundaries(self):
        check_prompt('x'*280000)
        with self.assertRaises(PromptBudgetError) as cm:check_prompt('x'*280001,'验证阶段')
        self.assertEqual(cm.exception.details['chars'],280001)
        self.assertEqual(cm.exception.details['stage'],'验证阶段')
        # Astral Unicode is 4 UTF-8 bytes per Python character. Wire quoting adds 2.
        check_prompt('😀'*237499+'aa')  # 950000 bytes exactly
        with self.assertRaises(PromptBudgetError) as cm:check_prompt('😀'*237500)
        self.assertEqual(cm.exception.details['bytes'],950002)
        self.assertLess(cm.exception.details['chars'],280000)
        self.assertIn('JSON 字节',str(cm.exception))


if __name__=='__main__':unittest.main(verbosity=2)
