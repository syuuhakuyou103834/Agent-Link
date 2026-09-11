from pathlib import Path
import sys,json,time
sys.path.insert(0,str(Path(__file__).parent))
from test_code_workflow import CodeWorkflowTests
from test_system import until
from app.storage import read_json
import unittest

class InterventionTests(CodeWorkflowTests):
 def test_new_recovery_b_preserves_a_and_thread(self):
  self.nodes['A'].command('start',topic='审查 [QUOTA_B_ONCE]',rounds=1,mode='code',project=self.pid)
  until(lambda:self.state()=='failed',45)
  until(lambda:all(not n.active for n in self.nodes.values()))
  parent=self.job();original=(parent/'state.json').read_bytes()
  self.assertEqual([len(self.calls(r)) for r in ('A','B')],[1,1])
  self.assertIn('部分独立检查',read_json(parent/'live-B.json')['answer'])
  time.sleep(.5);self.assertEqual(len(self.calls('B')),1)
  self.nodes['B'].command('start',topic='审查 [QUOTA_B_ONCE]',rounds=1,mode='code',project=self.pid,
    recovery={'parent_id':parent.name,'target':'B','text':'额度恢复，继续未完成步骤'})
  until(lambda:(parent/'recovery-child.json').exists(),20)
  child=self.shared/'jobs'/read_json(parent/'recovery-child.json')['job_id']
  until(lambda:read_json(child/'state.json',{}).get('status') in ('completed','failed'),60)
  self.assertEqual(read_json(child/'state.json')['status'],'completed',str(read_json(child/'state.json')))
  until(lambda:all(not n.active for n in self.nodes.values()))
  self.assertEqual([len(self.calls(r)) for r in ('A','B')],[2,2])
  self.assertEqual(self.calls('B')[0]['thread'],self.calls('B')[1]['thread'])
  self.assertEqual((parent/'state.json').read_bytes(),original)
  self.assertEqual(read_json(child/'turn-000-A.json')['inherited_from']['job_id'],parent.name)
  self.assertIn('累计请求尝试数：4',read_json(child/'report.json')['text'])
 def failed_parent(self):
  self.nodes['A'].command('start',topic='审查 [QUOTA_B_ONCE]',rounds=1,mode='code',project=self.pid)
  until(lambda:self.state()=='failed',45);until(lambda:all(not n.active for n in self.nodes.values()))
  return self.job()
 def test_new_recovery_wrong_target_and_project_rejected(self):
  parent=self.failed_parent();n=self.nodes['A']
  with self.assertRaisesRegex(ValueError,'属于节点 B'):n.prepare_recovery(parent.name,'A','继续',self.pid)
  with self.assertRaisesRegex(ValueError,'同一项目'):n.prepare_recovery(parent.name,'B','继续','f'*32)
  self.assertEqual([len(self.calls(r)) for r in ('A','B')],[1,1])
 def test_new_recovery_snapshot_mutation_blocks_before_b_request(self):
  parent=self.failed_parent();scope=read_json(self.root/'B'/'runs'/parent.name/'001-B-scope.json')
  (Path(scope['source'])/'main.py').write_text('tampered',encoding='utf-8')
  self.nodes['B'].command('start',topic='审查 [QUOTA_B_ONCE]',rounds=1,mode='code',project=self.pid,
    recovery={'parent_id':parent.name,'target':'B','text':'继续'})
  until(lambda:(parent/'recovery-child.json').exists())
  child=self.shared/'jobs'/read_json(parent/'recovery-child.json')['job_id']
  until(lambda:read_json(child/'state.json',{}).get('status')=='failed')
  self.assertEqual([len(self.calls(r)) for r in ('A','B')],[1,1])
 def test_new_recovery_after_b_service_restart(self):
  from app.engine import NodeService
  parent=self.failed_parent();old=self.nodes['B'];old.stop();old.thread.join(15)
  self.assertFalse(old.thread.is_alive())
  replacement=NodeService(old.settings,self.root/'B',lambda k,v:self.events['B'].append((k,v)),old.command_override)
  self.nodes['B']=replacement;replacement.start();replacement.command('connect')
  until(lambda:replacement.connected)
  replacement.command('start',topic='审查 [QUOTA_B_ONCE]',rounds=1,mode='code',project=self.pid,
    recovery={'parent_id':parent.name,'target':'B','text':'重启后继续'})
  until(lambda:(parent/'recovery-child.json').exists())
  child=self.shared/'jobs'/read_json(parent/'recovery-child.json')['job_id']
  until(lambda:read_json(child/'state.json',{}).get('status') in ('failed','completed'),60)
  self.assertEqual(read_json(child/'state.json')['status'],'completed',str(read_json(child/'state.json')))
  self.assertEqual(self.calls('B')[0]['thread'],self.calls('B')[1]['thread'])
  with self.assertRaisesRegex(ValueError,'已有恢复记录'):replacement.prepare_recovery(parent.name,'B','再试',self.pid)
 def test_new_steer_targets_only_b_and_deduplicates(self):
  self.nodes['A'].command('start',topic='审查 [LONG]',rounds=1,mode='code',project=self.pid)
  until(lambda:self.nodes['A'].client.current and self.nodes['A'].client.current.turn_id)
  job=self.job();self.nodes['B'].command('node_input',target='A',text='仅给A：先核查证据',note_id='a'*32)
  self.nodes['B'].command('node_input',target='A',text='仅给A：先核查证据',note_id='a'*32)
  until(lambda:read_json(job/('input-'+'a'*32+'.json'),{}).get('state')=='delivered',10)
  self.nodes['A'].command('cancel');until(lambda:all(not n.active for n in self.nodes.values()))
  rpc=[json.loads(x) for x in Path(str(self.root/'A-calls.jsonl')+'.rpc.jsonl').read_text(encoding='utf-8').splitlines()]
  self.assertEqual(len([x for x in rpc if x['method']=='turn/steer']),1)
  brpc=Path(str(self.root/'B-calls.jsonl')+'.rpc.jsonl').read_text(encoding='utf-8')
  self.assertNotIn('仅给A：先核查证据',brpc)
  self.assertEqual(len(self.calls('A')),1)

if __name__=='__main__':
 suite=unittest.TestSuite(InterventionTests(n) for n in dir(InterventionTests) if n.startswith('test_new_'))
 result=unittest.TextTestRunner(verbosity=2).run(suite);sys.exit(not result.wasSuccessful())
