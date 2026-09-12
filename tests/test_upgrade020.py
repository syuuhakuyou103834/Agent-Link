"""0.3.19 review regressions. Real local files; no services or model requests."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import copy
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid
ROOT = Path(os.environ.get('AGENTLINK_REGRESSION_SOURCE', Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(ROOT))
from fixture_paths import output_root
from app.engine import NodeService
from app.storage import Settings, Mailbox, io_path, read_json, atomic_json
from app.conversation import Conversations, fingerprint
from app.interruption import TechnicalInterruption
from app import artifacts, __version__


class Upgrade020(unittest.TestCase):
    def setUp(self):
        self.root = output_root() / ('u20-' + uuid.uuid4().hex[:8])
        self.root.mkdir(parents=True)
        self.node = NodeService(Settings(shared_root=str(self.root/'share'), auto_connect=False), self.root/'A', lambda *a: None)
        self.box = self.node.box = Mailbox(self.root/'share', self.root/'A')
        self.box.connect()
        self.node.client = SimpleNamespace(cleanup_pending=False, process=None)
        self.node._unified_compatible = lambda: 'peer-instance'
        self.node._assert_execution_idle = lambda: None
        self.node._model_context = lambda value: 'context'
        self.brief = dict(goal='test', directory='', permission='discuss', allowed_changes='none', acceptance=['review'], review_focus='review', round_limit=1)

    def waiting(self):
        c = self.node.conversations.create('test')
        with self.node.conversations.edit(c['id']) as value:
            value.update(phase='waiting_peer', confirmed=self.brief, confirmation={'brief_sha256':fingerprint(self.brief)})
        return self.node.conversations.get(c['id'])

    def test_A01_creation_failure_does_not_leave_running_orphan(self):
        c = self.waiting(); put = self.box.put
        def fail(job, name, value):
            if name == 'conversation-context.json': raise OSError('injected context failure')
            return put(job, name, value)
        with patch.object(self.box, 'put', side_effect=fail), self.assertRaises(OSError):
            self.node._start_unified_job(c)
        self.assertTrue(all(self.box.get(p.name,'state.json',{}).get('status') in ('failed','cancelled') for p in self.box.jobs()))
        self.node._start_unified_job(self.node.conversations.get(c['id']))
        self.assertEqual(self.node.conversations.get(c['id'])['phase'], 'working')

    def test_A02_stop_during_creation_never_revives(self):
        c = self.waiting(); put = self.box.put
        def stop(job, name, value):
            if name == 'conversation-context.json': self.node.unified_control(c['id'], 'cancel')
            return put(job, name, value)
        with patch.object(self.box, 'put', side_effect=stop):
            self.node._start_unified_job(c)
        latest = self.node.conversations.get(c['id'])
        self.assertEqual(latest['phase'], 'cancelled')
        self.assertTrue(all(self.box.get(p.name,'control.json',{}).get('cancelled') for p in self.box.jobs()))

    def test_A06_long_conversation_is_listed(self):
        c = Conversations(self.root/'long', self.root/'cache')
        cid = 'conversation-'+'a'*32
        padding = 262 - len(str(c.path(cid))) - 1
        c.root = c.root / ('x'*padding)
        self.assertEqual(len(str(c.path(cid))),262)
        atomic_json(c.path(cid),dict(schema=1,id=cid,created=1))
        self.assertIsNotNone(c.get(cid))
        self.assertEqual([v['id'] for v in c.list()],[cid])

    def input_job(self):
        meta = self.box.create('input',1,unlimited=True)
        meta['participants']={'A':self.node.instance,'B':'peer'}
        self.box.put(meta['id'],'meta.json',meta)
        self.node.active=meta
        key=uuid.uuid4().hex
        self.node.send_node_input(meta['id'],'A','KEEP-USER-CONSTRAINT',key)
        return meta['id'],key

    def test_B03_candidate_prompt_does_not_consume_input(self):
        job,key=self.input_job()
        first=self.node.node_input_prompt('000-A')
        self.assertIn('KEEP-USER-CONSTRAINT',first)
        self.assertEqual(self.box.get(job,'input-'+key+'.json')['state'],'queued')
        self.assertEqual(self.node.node_input_prompt('000-A'),first)
        self.assertFalse(list(io_path(self.box.job(job)).glob('*.claim')))
        self.assertFalse(list(io_path(self.box.job(job)).glob('call-*.json')))

    def test_A05_observer_reports_executor_receipt(self):
        job,_=self.input_job()
        self.box.put(job,'state.json',{'status':'running','index':1})
        self.box.put(job,'request-001-B.json',{'index':1,'phase':'review','job_id':job})
        self.box.put(job,'call-001-B.json',{'status':'interrupted_uncertain','step':'001-B','role':'B'})
        self.node._failed(TechnicalInterruption('peer failure',{'peer':'B'}))
        detail=self.box.get(job,'state.json')['interruption']
        self.assertEqual(detail['step'],'001-B')
        self.assertEqual(detail['request_state'],'interrupted_uncertain')

    def test_A04_successful_receive_removes_payload(self):
        src=self.root/'src';src.mkdir();(src/'file.txt').write_text('data')
        receipt,manifest=artifacts.publish(src,self.root/'packages','f'*32,'job',1)
        received,_=artifacts.receive(self.root/'packages',self.root/'received',receipt)
        artifacts.verify(received,manifest)
        self.assertEqual(list(io_path(self.root/'received').glob('.partial-*/payload.zip')),[])

    def test_B02_native_window_title_matches_source(self):
        from PyQt5.QtWidgets import QApplication
        from app.ui_conversation import MainWindow
        app=QApplication.instance() or QApplication([])
        w=MainWindow(self.node.settings,self.root/'ui',start_service=False)
        try: self.assertIn(__version__,w.windowTitle())
        finally: w.close();app.processEvents()

    def test_A03_discuss_B_review_constructs_readonly_scratch(self):
        from app import review_workflow
        self.node.settings.role='B'
        meta=self.box.create('discuss',1,unlimited=True)
        meta.update(project={'id':'f'*32},task_brief={'permission':'discuss'})
        self.node.active=meta
        source=self.root/'snapshot';source.mkdir()
        self.node._project=lambda *a,**k:dict(id='f'*32,directory=str(self.root/'received'),dependencies=[])
        self.node.recovery_scope=lambda *a:None
        captured=[]
        def capture(base,src,scratch,phase,deps):
            settings=original(base,src,scratch,phase,deps)
            captured.append((scratch,settings));raise RuntimeError('CAPTURED_SCOPE')
        original=review_workflow.scoped_settings
        with patch.object(artifacts,'receive',return_value=(source,{'entries':[],'omitted':[]})), patch.object(review_workflow,'scoped_settings',side_effect=capture):
            with self.assertRaisesRegex(RuntimeError,'CAPTURED_SCOPE'):
                self.node._perform_code_owned(dict(index=1,phase='review',revision=1,artifact={}))
        scratch,settings=captured[0]
        self.assertEqual(settings['permission_profile']['filesystem'][str(scratch.resolve())],'read')

    def test_A01_process_loss_reconciles_without_replaying(self):
        class PowerLoss(BaseException):pass
        c=self.waiting();put=self.box.put
        def crash(job,name,value):
            if name=='conversation-context.json':raise PowerLoss()
            return put(job,name,value)
        with patch.object(self.box,'put',side_effect=crash),self.assertRaises(PowerLoss):
            self.node._start_unified_job(c)
        self.assertIn('creation',self.node.conversations.get(c['id']))
        self.node._start_unified_job(self.node.conversations.get(c['id']))
        latest=self.node.conversations.get(c['id'])
        self.assertNotIn('creation',latest)
        running=[p for p in self.box.jobs() if self.box.get(p.name,'state.json',{}).get('status')=='running']
        self.assertEqual(len(running),1)
        self.assertFalse(list(io_path(self.box.root).glob('jobs/*/*.claim')))

    def test_A01_write_cutpoints_and_conversation_commit(self):
        from app import conversation
        for filename in ('meta.json','control.json','state.json','conversation-context.json','conversation.json'):
            with self.subTest(filename=filename):
                self.setUp();c=self.waiting();put=self.box.put;write=conversation.atomic_json;hit=[]
                def fail(job,name,value):
                    if name==filename and not hit:hit.append(name);raise OSError('cutpoint')
                    return put(job,name,value)
                def fail_conv(path,value):
                    if filename=='conversation.json' and value.get('phase')=='working' and not hit:
                        hit.append(filename);raise OSError('cutpoint')
                    return write(path,value)
                with patch.object(self.box,'put',side_effect=fail),patch.object(conversation,'atomic_json',side_effect=fail_conv),self.assertRaises(OSError):
                    self.node._start_unified_job(c)
                self.assertTrue(hit)
                self.assertFalse(any(self.box.get(p.name,'state.json',{}).get('status')=='running' for p in self.box.jobs()))
                self.node._start_unified_job(self.node.conversations.get(c['id']))
                self.assertEqual(self.node.conversations.get(c['id'])['phase'],'working')

    def test_A02_pause_and_stale_start_do_not_overwrite_current(self):
        c=self.waiting();put=self.box.put
        def pause(job,name,value):
            if name=='conversation-context.json':self.node.unified_control(c['id'],'pause')
            return put(job,name,value)
        with patch.object(self.box,'put',side_effect=pause):self.node._start_unified_job(c)
        self.assertEqual(self.node.conversations.get(c['id'])['phase'],'paused')
        count=len(self.box.jobs());self.node._start_unified_job(c)
        self.assertEqual(len(self.box.jobs()),count)

    def test_B03_budget_preflight_preserves_queued_message(self):
        from app.context import PromptBudgetError
        job,key=self.input_job()
        self.node.active.update(project={'id':'f'*32},task_brief={'permission':'review'})
        src=self.root/'project';src.mkdir();(src/'main.py').write_text('print(1)')
        self.node._project=lambda *a,**k:dict(id='f'*32,directory=str(src),dependencies=[])
        self.node.recovery_scope=lambda *a:None
        self.node._pump=lambda:None
        self.node._control=lambda:{'notes':[]}
        self.node.active_context=None
        self.node.unified_formal_context=lambda *a:'x'*280001
        with self.assertRaises(PromptBudgetError):
            self.node._perform_code_owned(dict(index=0,phase='implement',revision=1,artifact=None))
        self.assertEqual(self.box.get(job,'input-'+key+'.json')['state'],'queued')
        self.assertIn('KEEP-USER-CONSTRAINT',self.node.node_input_prompt('000-A'))
        self.assertFalse(list(io_path(self.box.job(job)).glob('*.claim')))
        self.assertFalse(list(io_path(self.box.job(job)).glob('call-*.json')))

    def test_B03_ledger_failure_and_uncertain_commit_are_distinct(self):
        from app.node_input import ordered_inputs
        job,key=self.input_job();self.node.node_input_prompt('000-A');put=self.box.put
        ledger=dict(job_id=job,step='000-A',role='A',status='send_pending')
        def fail(j,name,value):
            if name.startswith('call-'):raise OSError('ledger denied')
            return put(j,name,value)
        with patch.object(self.box,'put',side_effect=fail),self.assertRaises(OSError):
            self.node._commit_node_inputs('000-A',ledger)
        self.assertIn('KEEP-USER-CONSTRAINT',self.node.node_input_prompt('000-A'))
        self.node._commit_node_inputs('000-A',ledger)
        self.assertEqual(ordered_inputs(self.box.job(job))[0][1]['state'],'uncertain')
        self.assertEqual(self.node.node_input_prompt('000-A'),'')
        ledger['status']='result_received';put(job,'call-000-A.json',ledger)
        self.assertEqual(ordered_inputs(self.box.job(job))[0][1]['state'],'delivered')

    def test_B03_changed_input_rejected_before_commit(self):
        job,key=self.input_job();self.node.node_input_prompt('000-A')
        value=self.box.get(job,'input-'+key+'.json');value['text']='changed'
        self.box.put(job,'input-'+key+'.json',value)
        with self.assertRaisesRegex(ValueError,'补充消息已变化'):
            self.node._commit_node_inputs('000-A',dict(step='000-A',status='send_pending'))
        self.assertFalse(self.box.get(job,'call-000-A.json'))

    def test_A03_permission_matrix(self):
        from app.review_workflow import permission_phase,scoped_settings
        for permission in ('discuss','review','edit'):
            for role in ('A','B'):
                for phase in ('implement','review','summary'):
                    if role=='B' and phase=='implement':continue
                    with self.subTest(permission=permission,role=role,phase=phase):
                        settings=scoped_settings({},self.root/'source',self.root/'scratch',permission_phase(permission,phase),[])
                        rules=settings['permission_profile']['filesystem']
                        self.assertEqual(rules[str((self.root/'source').resolve())], 'write' if permission=='edit' and phase=='implement' else 'read')
                        self.assertEqual(rules[str((self.root/'scratch').resolve())], 'read' if permission=='discuss' or phase=='summary' else 'write')

    def test_A06_long_snapshot_end_to_end(self):
        for length in (259,260,262,320):
            with self.subTest(length=length):
                src=self.root/('source'+str(length));src.mkdir()
                path=src/('中'*70)/('x'*70)/'data.txt'
                path=path.parent/('y'*(length-len(str(path.parent))-1))
                self.assertEqual(len(str(path)),length)
                io_path(path.parent).mkdir(parents=True,exist_ok=True);io_path(path).write_text('payload',encoding='utf-8')
                packages=self.root/('packages'+str(length))
                receipt,manifest=artifacts.publish(src,packages,'f'*32,'job',1)
                received,_=artifacts.receive(packages,self.root/('received'+str(length)),receipt)
                artifacts.verify(received,manifest)
                self.assertEqual(io_path(received/path.relative_to(src)).read_text(encoding='utf-8'),'payload')

    def test_A05_missing_executor_is_unknown(self):
        job,_=self.input_job();self.box.put(job,'state.json',{'status':'running','index':2})
        self.node._failed(TechnicalInterruption('peer failure',{}))
        self.assertEqual(self.box.get(job,'state.json')['interruption']['request_state'],'UNKNOWN')

    def test_A04_failed_receive_keeps_diagnostic_without_duplicate_payload(self):
        src=self.root/'src';src.mkdir();(src/'file').write_text('preserved')
        receipt,_=artifacts.publish(src,self.root/'packages','f'*32,'job',1)
        with patch.object(artifacts,'verify',side_effect=ValueError('injected corrupt snapshot')):
            with self.assertRaisesRegex(ValueError,'corrupt snapshot'):
                artifacts.receive(self.root/'packages',self.root/'received',receipt)
        stage=next(io_path(self.root/'received').glob('.partial-*'))
        self.assertTrue((stage/'failure.json').is_file())
        self.assertFalse((stage/'payload.zip').exists())
        self.assertFalse((stage/'tree').exists())
        self.assertTrue((self.root/'packages'/receipt['manifest_sha256']/'source.zip').is_file())

    def test_A04_cleanup_failure_does_not_hide_published_snapshot(self):
        src=self.root/'src';src.mkdir();(src/'file').write_text('preserved')
        receipt,manifest=artifacts.publish(src,self.root/'packages','f'*32,'job',1)
        original=Path.unlink
        def deny(path,*a,**k):
            if path.name=='payload.zip':raise PermissionError('injected file held open')
            return original(path,*a,**k)
        with patch.object(Path,'unlink',deny):
            received,_=artifacts.receive(self.root/'packages',self.root/'received',receipt)
        artifacts.verify(received,manifest)

    def test_A01_ready_gate_blocks_dispatch_during_creation(self):
        c=self.waiting();put=self.box.put;seen=[]
        def observe(job,name,value):
            if name=='conversation-context.json':
                meta=self.box.get(job,'meta.json');seen.append(meta['ready'])
                self.node._unified_formal(dict(c,job=job))
                self.assertFalse(list(io_path(self.box.job(job)).glob('request-*.json')))
            return put(job,name,value)
        with patch.object(self.box,'put',side_effect=observe):self.node._start_unified_job(c)
        self.assertEqual(seen,[False])

    def test_B03_final_send_guard_rejects_committed_stop(self):
        from app.protocol import RpcClient,Cancelled
        job,key=self.input_job()
        client=RpcClient([],self.root/'rpc');self.node.client=client
        self.node._wait_unpaused=lambda i:None
        self.node.node_input_prompt('000-A')
        self.node._commit_node_inputs('000-A',dict(step='000-A',status='send_pending'))
        self.box.put(job,'control.json',dict(cancelled=True))
        with patch.object(client,'send') as send,self.assertRaises(Cancelled):
            client.request('turn/start',{})
        send.assert_not_called()


if __name__=='__main__': unittest.main(verbosity=2)
