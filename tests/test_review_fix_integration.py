"""Service-path regressions, two local nodes and mock RPC only."""
from pathlib import Path
import sys, unittest
sys.path.insert(0,str(Path(__file__).parent))
from test_code_workflow import CodeWorkflowTests
from test_system import until
from app.storage import read_json
from app.context import prepare_context, load_context


class ReviewFixIntegration(CodeWorkflowTests):
    def test_fix_01_recovery_delivers_history_and_queued_inputs_to_real_dispatch(self):
        node=self.nodes['A'];box=node.box
        history=box.create('KEEP-HISTORY',1,unlimited=True)
        history.update(mode='code',budget=3,project={'id':self.pid})
        box.put(history['id'],'meta.json',history)
        for i,phase in enumerate(('implement','review','summary')):
            role='ABA'[i];step=f'{i:03d}-{role}'
            box.put(history['id'],'turn-'+step+'.json',dict(job_id=history['id'],step=step,index=i,role=role,phase=phase,status='completed',answer='历史完整答复'))
        box.put(history['id'],'control.json',{'notes':['KEEP-NOTE']})
        box.put(history['id'],'state.json',{'status':'completed','calls':3})
        expected=prepare_context(box,history['id'])
        node.command('start',topic='审查 [QUOTA_B_ONCE]',rounds=1,mode='code',project=self.pid,parent_job_id=history['id'])
        def new_job():
            return next((p for p in (self.shared/'jobs').iterdir() if p.name!=history['id']),None)
        until(lambda:new_job() is not None and read_json(new_job()/'state.json',{}).get('status')=='failed',45)
        until(lambda:all(not n.active for n in self.nodes.values()))
        parent=new_job();meta=read_json(parent/'meta.json');state=(parent/'state.json').read_bytes()
        # Simulate messages admitted before failure but not yet sent at the saved checkpoint.
        for i,role in enumerate('AB'):
            identifier=str(i)*32
            box.put(parent.name,'input-'+identifier+'.json',dict(id=identifier,job_id=parent.name,target=role,
                participant=meta['participants'][role],by='A',text='ONLY-'+role,state='queued',created=i,sequence=i+1))
        originals={p.name:p.read_bytes() for p in parent.glob('input-*.json')}
        self.nodes['A'].command('start',topic='审查 [QUOTA_B_ONCE]',rounds=1,mode='code',project=self.pid,
            recovery={'parent_id':parent.name,'target':'B','text':'继续'})
        until(lambda:(parent/'recovery-child.json').exists())
        child=box.job(read_json(parent/'recovery-child.json')['job_id'])
        until(lambda:read_json(child/'state.json',{}).get('status') in ('completed','failed'),60)
        self.assertEqual(read_json(child/'state.json')['status'],'completed',str(read_json(child/'state.json')))
        until(lambda:all(not n.active for n in self.nodes.values()))
        inherited=load_context(box,read_json(child/'meta.json'))
        self.assertEqual(inherited['discussions'],expected['discussions'])
        self.assertEqual([len(self.calls(r)) for r in 'AB'],[2,2])
        self.assertEqual(self.calls('B')[0]['thread'],self.calls('B')[1]['thread'])
        for role in 'AB':
            prompt=self.calls(role)[-1]['prompt']
            for token in ('KEEP-HISTORY','KEEP-NOTE','ONLY-'+role):self.assertIn(token,prompt)
            self.assertNotIn('ONLY-'+('B' if role=='A' else 'A'),prompt)
        self.assertEqual((parent/'state.json').read_bytes(),state)
        for name,data in originals.items():self.assertEqual((parent/name).read_bytes(),data)

    def test_fix_02_b_initiated_early_completed_review_continues(self):
        self.run_code('A',topic='EARLY-HISTORY',rounds=3)
        parent=self.job()
        self.nodes['A'].command('start',topic='继续既有项目',rounds=1,mode='code',project=self.pid,parent_job_id=parent.name)
        def child():return next((p for p in (self.shared/'jobs').iterdir() if p.name!=parent.name),None)
        until(lambda:child() is not None and read_json(child()/'state.json',{}).get('status') in ('completed','failed'),60)
        self.assertEqual(read_json(child()/'state.json')['status'],'completed',str(read_json(child()/'state.json')))
        until(lambda:all(not n.active for n in self.nodes.values()))
        for role in 'AB':self.assertIn('EARLY-HISTORY',self.calls(role)[-1]['prompt'])
        self.assertEqual([len(self.calls(r)) for r in 'AB'],[4,2])


if __name__=='__main__':
    suite=unittest.TestSuite(ReviewFixIntegration(n) for n in dir(ReviewFixIntegration) if n.startswith('test_fix_'))
    result=unittest.TextTestRunner(verbosity=2).run(suite);sys.exit(not result.wasSuccessful())
