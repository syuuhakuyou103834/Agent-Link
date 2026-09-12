import json
from pathlib import Path
import sys
import unittest
import uuid
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from test_system import SystemTests, until
from app.projects import Projects
from app.storage import read_json


class CodeWorkflowTests(SystemTests):
    # Use the same two-process mock harness without re-running inherited text cases here.
    def setUp(self):
        super().setUp()
        self.project = self.root / 'official'; self.project.mkdir()
        (self.project / 'main.py').write_text('print("untracked 中文")', encoding='utf-8')
        self.pid = uuid.uuid4().hex
        store = Projects(self.root / 'A')
        store.save('测试项目', str(self.project), 'A', self.pid)
        store.publish(self.shared, 'A')

    def run_code(self, initiator='A', topic='独立审查项目', rounds=3):
        self.nodes[initiator].command('start', topic=topic, rounds=rounds, mode='code', project=self.pid)
        until(lambda: self.state() in ('completed', 'failed', 'cancelled'), 90)
        if self.state() != 'completed':
            self.fail(str(read_json(self.job() / 'state.json')))
        until(lambda: all(not n.active for n in self.nodes.values()))
        return read_json(self.job() / 'state.json')

    def test_code_A_early_pass_has_three_requests_and_readonly_summary(self):
        state = self.run_code(topic='独立审查 [SIDE_ISSUE]')
        self.assertEqual(state['outcome'], 'passed')
        self.assertEqual([len(self.calls(r)) for r in ('A','B')], [2,1])
        a, b = self.calls('A'), self.calls('B')
        self.assertNotEqual(a[0]['thread'], a[1]['thread'])
        rules = next(iter(a[-1]['thread_params']['config']['permissions'].values()))['filesystem']
        self.assertNotIn('write', rules.values())
        b_rules = next(iter(b[0]['thread_params']['config']['permissions'].values()))['filesystem']
        self.assertNotIn(str(self.project), b_rules)
        self.assertIsNotNone(b[0]['output_schema'])
        issues = read_json(self.shared / 'projects' / self.pid / 'issues.json')['issues']
        self.assertEqual(len(issues),1)
        self.assertIn('另一个范围外问题', a[-1]['prompt'])

    def test_code_B_initiation_keeps_fixed_roles(self):
        self.run_code('B')
        turns = [read_json(p) for p in sorted(self.job().glob('turn-*.json'))]
        self.assertEqual([(t['role'], t['phase']) for t in turns], [('A','implement'),('B','review'),('A','summary')])

    def test_code_budget_exhaustion_requires_user_decision(self):
        state = self.run_code(topic='修改建议 [NEEDS_CHANGES]')
        self.assertEqual(state['outcome'], 'needs_user_decision')
        self.assertEqual(sum(len(self.calls(r)) for r in ('A','B')), 7)

    def test_code_blocked_review_does_not_spend_remaining_pairs(self):
        state = self.run_code(topic='审查 [BLOCK_REVIEW]')
        self.assertEqual(state['outcome'], 'blocked')
        self.assertEqual(sum(len(self.calls(r)) for r in ('A','B')), 3)

    def test_code_A_disagreement_requires_user_decision(self):
        state = self.run_code(topic='审查 [A_DISAGREES]')
        self.assertEqual(state['outcome'], 'needs_user_decision')
        self.assertEqual(sum(len(self.calls(r)) for r in ('A','B')), 3)

    def test_code_final_mutation_invalidates_result(self):
        self.nodes['A'].command('start', topic='审查 [MUTATE_SUMMARY]', rounds=3, mode='code', project=self.pid)
        until(lambda: self.state() == 'failed', 90)
        self.assertIn('源码发生变化', read_json(self.job() / 'state.json')['error'])


if __name__ == '__main__':
    suite = unittest.TestSuite(CodeWorkflowTests(name) for name in dir(CodeWorkflowTests) if name.startswith('test_code_'))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(not result.wasSuccessful())
