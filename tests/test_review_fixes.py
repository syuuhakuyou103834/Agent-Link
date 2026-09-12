"""Numbered review regressions; isolated local fixtures, no real model calls."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import os
import shutil
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.context import load_context, context_hash, prepare_context, validate_context
from app.engine import NodeService
from app.node_input import FEATURE
from app.storage import Mailbox, Settings, atomic_json, read_json, io_path
from app import artifacts


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='review-fix-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.box = Mailbox(self.root / 'share', self.root / 'A')
        self.box.connect()
        self.node = NodeService(Settings(role='A'), self.root / 'A', Mock())
        self.node.box = self.box
        self.pid = 'f' * 32
        self.context = {'schema': 1, 'discussions': [{
            'job_id': '20260911-000000-' + 'a' * 32, 'topic': '历史约束 KEEP-HISTORY',
            'status': 'completed', 'initiator': 'A', 'notes': ['KEEP-NOTE'],
            'turns': [{'index': i, 'role': 'ABA'[i], 'answer': '完整答复'} for i in range(3)]}]}

    def failed_parent(self):
        meta = self.box.create('恢复测试', 1, context=self.context, unlimited=True)
        meta.update(mode='code', project={'id': self.pid}, budget=3,
                    participants={'A': 'old-A', 'B': 'old-B'})
        self.box.put(meta['id'], 'meta.json', meta)
        self.box.put(meta['id'], 'state.json', {'status': 'failed'})
        self.box.put(meta['id'], 'request-000-A.json', {
            'job_id': meta['id'], 'index': 0, 'phase': 'implement'})
        atomic_json(self.box.root / 'nodes/B.json', {'features': [FEATURE]})
        return meta

    def recover(self, parent):
        node = self.node
        for method in ('_assert_execution_idle', '_code_compatible', '_heartbeat', 'history', '_sync_selected'):
            setattr(node, method, Mock())
        node._project = Mock(return_value={'name': '测试项目'})
        node._check_peer_compatibility = Mock(return_value='new-B')
        node._failed = Mock()
        captured = []
        def dispatch(index, phase, revision, turns, receipt):
            captured.append(copy.deepcopy(node.active))
            return dict(index=index, role='B' if phase=='review' else 'A', phase=phase,
                        answer='完成', artifact=None, review={'decision':'passed'}, final_decision='agreed')
        node._code_dispatch = dispatch
        node.run_code_review('恢复测试', project=self.pid,
            recovery={'parent_id': parent['id'], 'target': 'A', 'text': '继续'})
        self.assertFalse(node._failed.called, str(node._failed.call_args))
        self.assertTrue(captured)
        return captured[0]


class RecoveryInheritanceTests(Fixture):
    def test_01_recovery_carries_validated_history_into_child(self):
        parent = self.failed_parent()
        child = self.recover(parent)
        self.assertEqual(load_context(self.box, child), self.context)
        self.assertEqual(child['context']['sha256'], context_hash(self.context))

    def test_01_queued_inputs_rebound_without_replaying_uncertain_or_delivered(self):
        parent = self.failed_parent()
        originals = {}
        for i, state in enumerate(('queued', 'queued', 'send_pending', 'uncertain', 'delivered', 'included_next_request')):
            identifier = f'{i:032x}'
            value = dict(id=identifier, job_id=parent['id'], target='AB'[i % 2],
                         participant='old-' + 'AB'[i % 2], by='A', text=f'约束-{i}', state=state, created=i)
            filename = 'input-' + identifier + '.json'
            self.box.put(parent['id'], filename, value)
            originals[filename] = (self.box.job(parent['id']) / filename).read_bytes()
        child = self.recover(parent)
        paths = list(self.box.job(child['id']).glob('input-*.json'))
        self.assertEqual(len(paths), 2)
        for path in paths:
            value = read_json(path)
            self.assertEqual(value['job_id'], child['id'])
            self.assertEqual(value['participant'], child['participants'][value['target']])
            self.assertEqual(value['state'], 'queued')
            self.assertEqual(value['inherited_from']['job_id'], parent['id'])
        for filename, data in originals.items():
            self.assertEqual((self.box.job(parent['id']) / filename).read_bytes(), data)

    def test_01_corrupt_history_blocks_before_child_creation(self):
        parent = self.failed_parent()
        bad = copy.deepcopy(self.context); bad['discussions'][0]['topic'] = 'changed'
        self.box.put(parent['id'], 'context.json', bad)
        with self.assertRaisesRegex(ValueError, '校验失败'):
            self.node.prepare_recovery(parent['id'], 'A', '继续', self.pid)
        self.assertEqual(len(list((self.box.root / 'jobs').iterdir())), 1)


class InputOrderTests(Fixture):
    def active_job(self):
        meta = self.failed_parent()
        self.box.put(meta['id'], 'state.json', {'status': 'running'})
        meta['participants']['A'] = self.node.instance
        self.box.put(meta['id'], 'meta.json', meta)
        self.node.active = meta
        return meta

    def enqueue(self, job):
        with patch('app.node_input.now', return_value=123):
            self.node.send_node_input(job, 'A', '先要求', 'f'*32)
            self.node.send_node_input(job, 'A', '后要求', '0'*32)
            self.node.send_node_input(job, 'A', '重复不应覆盖', 'f'*32)

    def test_04_prompt_respects_admission_order_even_at_same_time(self):
        meta = self.active_job(); self.enqueue(meta['id'])
        prompt = self.node.node_input_prompt('000-A')
        self.assertLess(prompt.index('先要求'), prompt.index('后要求'))
        self.assertNotIn('重复', prompt)
        self.assertEqual(self.node.node_input_prompt('000-A'), '')

    def test_04_live_steer_uses_same_order(self):
        meta = self.active_job(); self.enqueue(meta['id'])
        client = SimpleNamespace(current=SimpleNamespace(turn_id='t',thread_id='h',step='000-A',status='running'),responses={})
        client.begin_steer = Mock(side_effect=[(1,'t'),(2,'t')])
        self.node.client=client; self.node._pump_node_inputs()
        self.assertEqual([x.args[0] for x in client.begin_steer.call_args_list], ['先要求','后要求'])

    def test_04_legacy_messages_use_created_before_new_sequence(self):
        meta=self.active_job()
        for identifier,created,text in [('e'*32,10,'旧先'),('1'*32,20,'旧后')]:
            self.box.put(meta['id'],'input-'+identifier+'.json',dict(id=identifier,job_id=meta['id'],target='A',participant=self.node.instance,state='queued',created=created,text=text))
        self.enqueue(meta['id'])
        prompt=self.node.node_input_prompt('000-A')
        self.assertEqual(sorted(['旧先','旧后','先要求','后要求'],key=prompt.index),['旧先','旧后','先要求','后要求'])


class ExclusionTests(Fixture):
    def test_07_all_env_prefix_files_excluded_from_manifest_and_payload(self):
        import zipfile
        source=self.root/'source';source.mkdir()
        private=['.env','.envrc','.ENVRC','.env.example','.environment']
        # Windows is case-insensitive, so test the uppercase spelling separately.
        private.remove('.ENVRC')
        for name in private: (source/name).write_text('synthetic-secret')
        (source/'main.py').write_text('print(1)')
        (source/'environment.py').write_text('x=1')
        receipt,manifest=artifacts.publish(source,self.root/'artifacts',self.pid,'test',1)
        self.assertEqual({e['path'] for e in manifest['omitted']},set(private))
        with zipfile.ZipFile(self.root/'artifacts'/receipt['manifest_sha256']/'source.zip') as z:
            self.assertEqual(set(z.namelist()),{'main.py','environment.py'})
        (source/'.envrc').rename(source/'.ENVRC')
        self.assertIn('.ENVRC',{e['path'] for e in artifacts.inventory(source)['omitted']})


class ProjectContextTests(Fixture):
    def completed_project(self, initiator='A', rounds=3, calls=3):
        meta=self.box.create('项目历史',rounds,initiator,unlimited=True)
        meta.update(mode='code',budget=2*rounds+1,project={'id':self.pid})
        self.box.put(meta['id'],'meta.json',meta)
        for i in range(calls):
            role='B' if i%2 else 'A';step=f'{i:03d}-{role}'
            phase='summary' if i==calls-1 else 'review' if i%2 else 'implement'
            self.box.put(meta['id'],'turn-'+step+'.json',dict(job_id=meta['id'],index=i,step=step,role=role,status='completed',phase=phase,answer='完整答案'))
        self.box.put(meta['id'],'state.json',dict(status='completed',calls=calls))
        return meta

    def test_02_early_completion_uses_actual_calls(self):
        meta=self.completed_project()
        context=prepare_context(self.box,meta['id'])
        self.assertEqual(len(context['discussions'][-1]['turns']),3)

    def test_02_b_initiated_project_keeps_a_b_a_roles_and_can_chain(self):
        meta=self.completed_project('B',1)
        context=prepare_context(self.box,meta['id'])
        record=context['discussions'][-1]
        self.assertEqual(record['initiator'],'B')
        self.assertEqual([t['role'] for t in record['turns']],list('ABA'))
        child=self.box.create('后续',1,context=context)
        self.assertEqual(load_context(self.box,child),context)

    def test_02_missing_summary_bad_count_and_phase_are_rejected(self):
        meta=self.completed_project()
        for calls in (True,2,9,None):
            self.box.put(meta['id'],'state.json',dict(status='completed',calls=calls))
            with self.assertRaises(ValueError):prepare_context(self.box,meta['id'])
        self.box.put(meta['id'],'state.json',dict(status='completed',calls=3))
        p=self.box.job(meta['id'])/'turn-002-A.json'
        value=read_json(p);value['phase']='implement';atomic_json(p,value)
        with self.assertRaises(ValueError):prepare_context(self.box,meta['id'])
        p.unlink()
        with self.assertRaises(ValueError):prepare_context(self.box,meta['id'])


class OfflineHistoryTests(Fixture):
    def test_03_offline_project_history_without_mailbox(self):
        meta=self.failed_parent();self.node.selected=meta['id']
        self.node.connected=False;self.node.box=None
        captured=[];self.node.emit=lambda k,v:captured.append((k,v))
        self.node._sync_selected()
        self.assertEqual(captured[-1][1]['project_issues_source'],'unavailable')

    def test_03_connected_issues_remain_available_offline(self):
        meta=self.failed_parent();self.node.selected=meta['id'];self.node.connected=True
        issues=[{'id':'x','description':'待修复','status':'open'}]
        atomic_json(self.box.root/'projects'/self.pid/'issues.json',{'issues':issues})
        captured=[];self.node.emit=lambda k,v:captured.append((k,v))
        self.node._sync_selected()
        self.node.connected=False;self.node.box=None;self.node.last_snapshot=None
        self.node._sync_selected()
        self.assertEqual(captured[-1][1]['project_issues'],issues)
        self.assertEqual(captured[-1][1]['project_issues_source'],'cache')


class ArchiveRaceTests(Fixture):
    def test_05_transient_change_during_zip_never_publishes_ready(self):
        from contextlib import contextmanager
        source=self.root/'source';source.mkdir();p=source/'main.py';p.write_bytes(b'original')
        original=artifacts.project_file;calls=0
        @contextmanager
        def swap(path,root):
            nonlocal calls
            calls+=1
            transient=calls==2
            if transient:p.write_bytes(b'modified')
            try:
                with original(path,root) as f:yield f
            finally:
                if transient:p.write_bytes(b'original')
        with patch.object(artifacts,'project_file',swap):
            with self.assertRaisesRegex(ValueError,'打包'):
                artifacts.publish(source,self.root/'packages',self.pid,'test',1)
        self.assertEqual(p.read_bytes(),b'original')
        self.assertFalse(list((self.root/'packages').rglob('ready.json')))

    def test_05_unchanged_archive_still_delivers_exact_bytes(self):
        source=self.root/'source';source.mkdir();data=b'original'*100
        (source/'main.py').write_bytes(data)
        receipt,manifest=artifacts.publish(source,self.root/'packages',self.pid,'test',1)
        result,_=artifacts.receive(self.root/'packages',self.root/'received',receipt)
        self.assertEqual((result/'main.py').read_bytes(),data)


@unittest.skipUnless(os.name == 'nt','Windows path regression')
class WindowsPathTests(Fixture):
    def test_06_mailbox_creates_long_local_and_shared_paths(self):
        deep=self.root/('long-'+'x'*100)/('y'*100)/('z'*70)
        cleanup=deep.parents[1]
        assert cleanup.is_relative_to(self.root) and cleanup != self.root
        self.addCleanup(lambda:shutil.rmtree('\\\\?\\'+str(cleanup)))
        box=Mailbox(deep/'share',deep/'local')
        box.connect();meta=box.create('long path',1)
        self.assertEqual(box.get(meta['id'],'meta.json')['id'],meta['id'])
        self.assertTrue(box.claim(meta['id'],'000-A'))
        self.assertFalse(box.claim(meta['id'],'000-A'))

    def test_06_recovery_compares_prefixed_and_plain_paths(self):
        meta=self.failed_parent();self.node.active={'recovery':{'parent_id':meta['id'],'index':0,'text':'继续'}}
        bound=self.root/'source';bound.mkdir()
        scratch=self.node.data/'project-tests'/self.pid/'job'/'1';scratch.mkdir(parents=True)
        atomic_json(self.node.data/'runs'/meta['id']/'000-A-scope.json',{
            'phase':'implement','source':'\\\\?\\'+str(bound), 'scratch':'\\\\?\\'+str(scratch),'snapshot':None})
        result=self.node.recovery_scope({'index':0,'phase':'implement','artifact':None},{'id':self.pid,'directory':str(bound)})
        self.assertEqual(result['source'],bound.resolve())
        self.assertEqual(result['scratch'],scratch.resolve())

    def test_06_outside_path_stays_rejected_after_normalization(self):
        meta=self.failed_parent();self.node.active={'recovery':{'parent_id':meta['id'],'index':0,'text':'继续'}}
        atomic_json(self.node.data/'runs'/meta['id']/'000-A-scope.json',{
            'phase':'implement','source':str(self.root/'source'),'scratch':'\\\\?\\'+str(self.root/'outside'),'snapshot':None})
        with self.assertRaisesRegex(ValueError,'范围'):
            self.node.recovery_scope({'index':0,'phase':'implement'},{'id':self.pid,'directory':str(self.root/'source')})


if __name__ == '__main__':
    unittest.main(verbosity=2)
