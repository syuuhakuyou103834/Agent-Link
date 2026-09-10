"""History transport contracts; no model calls, accounts or production data."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.storage import Mailbox, report_text
from app.context import prepare_context, load_context, context_hash, prompt_context, check_prompt


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='agentlink-context-')
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.box = Mailbox(root / 'share', root / 'local')
        self.box.connect()

    def completed(self, topic='原议题 UNIQUE-T19', context=None, initiator='A'):
        meta = self.box.create(topic, 1, initiator, context)
        for i in range(3):
            role = initiator if i % 2 == 0 else ('B' if initiator == 'A' else 'A')
            step = f'{i:03d}-{role}'
            turn = {'step': step, 'index': i, 'role': role, 'status': 'completed',
                    'answer': '完整答复 ' + str(i) + ' 中文尾部 END',
                    'summary': 'DO-NOT-CARRY-SUMMARY', 'tools': [{'output': 'DO-NOT-CARRY-RAW-TOOL'}]}
            self.box.put(meta['id'], 'turn-' + step + '.json', turn)
        self.box.put(meta['id'], 'control.json', {'notes': ['保留用户补充 NOTE-17']})
        self.box.put(meta['id'], 'state.json', {'status': 'completed'})
        return meta

    def test_complete_snapshot_preserves_notes_answers_and_excludes_raw_events(self):
        parent = self.completed()
        context = prepare_context(self.box, parent['id'])
        text = prompt_context(context)
        for token in ('UNIQUE-T19', 'NOTE-17', '完整答复 0', '完整答复 1', '完整答复 2', 'END'):
            self.assertIn(token, text)
        self.assertNotIn('DO-NOT-CARRY', text)
        child = self.box.create('执行测试', 2, context=context)
        self.assertEqual(load_context(self.box, child), context)
        self.assertEqual(child['context']['sha256'], context_hash(context))
        self.assertIn('UNIQUE-T19', report_text(child, [], context))

    def test_chained_context_survives_missing_ancestor_directory(self):
        first = self.completed()
        first_context = prepare_context(self.box, first['id'])
        second = self.completed('第二次', first_context, initiator='B')
        # Relocate only this test's ancestor; no production files are involved.
        self.box.job(first['id']).rename(self.box.root / 'archived-test-parent')
        combined = prepare_context(self.box, second['id'])
        self.assertEqual([r['job_id'] for r in combined['discussions']], [first['id'], second['id']])
        self.assertIn('UNIQUE-T19', prompt_context(combined))

    def test_fresh_job_has_no_context(self):
        child = self.box.create('独立议题', 1)
        self.assertNotIn('context', child)
        self.assertIsNone(load_context(self.box, child))

    def test_missing_or_changed_context_fails_closed(self):
        parent = self.completed()
        context = prepare_context(self.box, parent['id'])
        child = self.box.create('后续', 1, context=context)
        changed = copy.deepcopy(context)
        changed['discussions'][0]['topic'] = '被改动'
        self.box.put(child['id'], 'context.json', changed)
        with self.assertRaisesRegex(ValueError, '校验失败'):
            load_context(self.box, child)
        (self.box.job(child['id']) / 'context.json').unlink()
        with self.assertRaises(ValueError):
            load_context(self.box, child)

    def test_incomplete_parent_is_not_treated_as_final(self):
        parent = self.completed()
        for status in ('cancelled', 'failed', 'running'):
            self.box.put(parent['id'], 'state.json', {'status': status})
            with self.assertRaisesRegex(ValueError, '已完成'):
                prepare_context(self.box, parent['id'])

    def test_missing_turn_is_rejected(self):
        parent = self.completed()
        (self.box.job(parent['id']) / 'turn-001-B.json').unlink()
        with self.assertRaisesRegex(ValueError, '不完整'):
            prepare_context(self.box, parent['id'])

    def test_oversize_is_rejected_without_truncation(self):
        parent = self.completed()
        turn = self.box.get(parent['id'], 'turn-002-A.json')
        turn['answer'] = '中' * 120001
        self.box.put(parent['id'], 'turn-002-A.json', turn)
        with self.assertRaisesRegex(ValueError, '未截断'):
            prepare_context(self.box, parent['id'])
        self.assertEqual(len(self.box.get(parent['id'], 'turn-002-A.json')['answer']), 120001)
        with self.assertRaisesRegex(ValueError, '未截断'):
            check_prompt('中' * 280001)

    def test_invalid_parent_id_is_rejected(self):
        with self.assertRaises(ValueError):
            prepare_context(self.box, '../outside')


if __name__ == '__main__':
    unittest.main(verbosity=2)
