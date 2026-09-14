from fixture_paths import fs, entries
"""Fault boundaries and compatibility for the 0.3.22 stability release."""
import copy,json,os,shutil,sys,threading,time,unittest,uuid
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from fixture_paths import fs,output_root
from app import artifacts,context_view
from app.conversation import control_word
from app.diagnostics import RuntimeJournal
from app.engine import NodeService
from app.process_job import process_creation
from app.storage import Settings,atomic_json,read_json
from test_context_view import sample


class StabilityTests(unittest.TestCase):
    def setUp(self):
        self.root=output_root()/('stability-'+uuid.uuid4().hex[:8]);fs(self.root).mkdir()

    def test_old_host_alive_never_clears_pending_cleanup_on_restart(self):
        node=NodeService(Settings(shared_root=str(self.root/'share')),self.root/'node',lambda *_:None)
        record=dict(status='cleanup_pending',host_guard=True,host_pid=os.getpid(),
                    host_created=process_creation(os.getpid()),pid=None)
        atomic_json(node.data/'execution-cleanup.json',record)
        with self.assertRaisesRegex(RuntimeError,'宿主仍存活'):node._reconcile_cleanup()
        self.assertEqual(read_json(node.data/'execution-cleanup.json'),record)
        self.assertIsNone(node.client)

    def test_restart_reconciliation_checks_creation_identity_and_denials(self):
        node=NodeService(Settings(shared_root=str(self.root/'share')),self.root/'node',lambda *_:None)
        record=dict(status='cleanup_pending',host_guard=True,host_pid=100,host_created=111,pid=200,process_created=222)
        atomic_json(node.data/'execution-cleanup.json',record)
        with patch('app.process_job.process_creation',side_effect=PermissionError('probe denied')):
            with self.assertRaises(PermissionError):node._reconcile_cleanup()
        self.assertEqual(read_json(node.data/'execution-cleanup.json'),record)
        with patch('app.process_job.process_creation',side_effect=[None,222]):
            with self.assertRaisesRegex(RuntimeError,'旧执行进程仍存活'):node._reconcile_cleanup()
        with patch('app.process_job.process_creation',side_effect=[333,444]):node._reconcile_cleanup()
        self.assertEqual(read_json(node.data/'execution-cleanup.json')['status'],'cleanup_confirmed')

    def test_missing_ownership_proof_is_not_assumed_clean(self):
        node=NodeService(Settings(shared_root=str(self.root/'share')),self.root/'node',lambda *_:None)
        atomic_json(node.data/'execution-cleanup.json',{'status':'cleanup_pending','pid':123})
        with self.assertRaisesRegex(RuntimeError,'缺少进程归属'):node._reconcile_cleanup()

    def test_null_cleanup_record_is_not_assumed_clean(self):
        node=NodeService(Settings(shared_root=str(self.root/'share')),self.root/'node',lambda *_:None)
        atomic_json(node.data/'execution-cleanup.json',None)
        with self.assertRaisesRegex(RuntimeError,'损坏'):node._reconcile_cleanup()

    def test_received_result_survives_cleanup_failure_and_cannot_be_overwritten(self):
        from types import SimpleNamespace
        node=NodeService(Settings(shared_root=str(self.root/'share')),self.root/'node',lambda *_:None)
        result={'answer':'already returned','status':'completed'}
        path=node._cache_received_result('job','000-A',result)
        def failed_close():raise RuntimeError('injected cleanup error')
        node.client=SimpleNamespace(close=failed_close,process=None,cleanup_pending=True)
        with self.assertRaisesRegex(RuntimeError,'cleanup error'):node._close_execution()
        self.assertEqual(node._load_received_result('job','000-A')['result'],result)
        with self.assertRaisesRegex(ValueError,'拒绝覆盖'):node._cache_received_result('job','000-A',{'answer':'replacement'})
        self.assertEqual(node._load_received_result('job','000-A')['result'],result)

    def test_io_channels_recover_independently_and_new_failure_restarts_clock(self):
        node=NodeService(Settings(shared_root=str(self.root/'share')),self.root/'node',lambda *_:None)
        instant=[100.]
        with patch.object(node.liveness,'clock',side_effect=lambda:instant[0]),patch.object(node,'report_error'):
            node._peer_io_error(OSError('heartbeat'),'heartbeat')
            instant[0]=105;node._peer_io_error(OSError('control'),'execution')
            node._io_recovered('execution');self.assertEqual(node.share_lost,100)
            node._io_recovered('heartbeat');self.assertIsNone(node.share_lost)
            instant[0]=200;node._peer_io_error(OSError('new heartbeat'),'heartbeat')
            self.assertEqual(node.share_lost,200)

    def test_legacy_valid_bundle_is_adopted_but_prior_receipt_missing_tree_blocks(self):
        value=sample();_,root,receipt=context_view.prepare(value,self.root/'evidence')
        anchor=self.root/'evidence'/'.committed'/(receipt['bundle']+'.json')
        fs(anchor).unlink()  # emulate a valid 0.3.21 bundle without the new marker
        context_view.prepare(value,self.root/'evidence',[receipt]);self.assertTrue(fs(anchor).is_file())
        fs(anchor).unlink();shutil.rmtree(fs(root))
        with self.assertRaisesRegex(ValueError,'缺失'):context_view.prepare(value,self.root/'evidence',[receipt])
        self.assertFalse(fs(root).exists())

    def package(self):
        source=self.root/'source';fs(source).mkdir();fs(source/'main.txt').write_text('payload')
        return (source,self.root/'delivery',uuid.uuid4().hex,'job',1)

    def test_corrupted_published_zip_is_not_reused_or_overwritten(self):
        args=self.package();receipt,_=artifacts.publish(*args)
        archive=args[1]/receipt['manifest_sha256']/'source.zip';fs(archive).write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError,'损坏'):artifacts.publish(*args)
        self.assertEqual(fs(archive).read_bytes(),b'corrupt')
        self.assertFalse(list(fs(args[1]).glob('.partial-*')))

    def test_mid_publish_failure_cleans_only_owned_stage_and_keeps_failure(self):
        args=self.package();fs(args[1]).mkdir();sentinel=args[1]/'.partial-unrelated';fs(sentinel).mkdir()
        fs(sentinel/'keep').write_text('other operation')
        def pump():
            if len([p for p in fs(args[1]).glob('.partial-*') if fs(p).is_dir()])>1:raise RuntimeError('injected publish interruption')
        with self.assertRaisesRegex(RuntimeError,'injected'):artifacts.publish(*args,pump=pump)
        self.assertEqual(fs(sentinel/'keep').read_text(),'other operation')
        self.assertEqual([p.name for p in fs(args[1]).glob('.partial-*') if fs(p).is_dir()],['.partial-unrelated'])
        self.assertEqual(len(list(fs(args[1]).glob('*-failure.json'))),1)

    def test_original_zip_and_receipt_available_outside_verified_source(self):
        args=self.package();receipt,manifest=artifacts.publish(*args)
        source,copied=artifacts.receive(args[1],self.root/'mirror',receipt)
        original=artifacts.received_package(self.root/'mirror',receipt)
        self.assertEqual(artifacts.digest(original/'source.zip'),receipt['zip_sha256'])
        self.assertEqual(read_json(original/'ready.json'),receipt)
        self.assertEqual(read_json(original/'manifest.json'),manifest)
        self.assertIn('not established',read_json(original/'delivery.json')['scope'])
        artifacts.verify(source,copied)
        self.assertFalse(original.is_relative_to(source))
        artifacts.receive(args[1],self.root/'mirror',receipt)
        self.assertEqual(len(list(fs(self.root/'mirror'/'.received').glob('*/source.zip'))),1)

    def test_resume_aliases_are_exact_not_substring_commands(self):
        for text in ('继续执行','恢复任务','继续！','resume'):self.assertEqual(control_word(text),'继续')
        for text in ('解释继续执行的风险','停止后不要继续执行','请说明如何恢复任务'):
            self.assertEqual(control_word(text),text)

    def test_diagnostics_rotation_and_metadata_only(self):
        log=RuntimeJournal(self.root/'logs',max_bytes=300,backups=2);log.start()
        try:
            for i in range(12):log.emit('request_written',request_id=i,request_state='pipe_written',prompt='SECRET',token='SECRET')
            deadline=time.monotonic()+5
            while log.written<12 and time.monotonic()<deadline:time.sleep(.01)
            self.assertEqual(log.written,12)
        finally:log.close(1)
        files=list(fs(self.root/'logs').glob('runtime-events.jsonl*'))
        self.assertLessEqual(len(files),3)
        text=''.join(fs(p).read_text(encoding='utf-8') for p in files)
        self.assertNotIn('SECRET',text);self.assertNotIn('prompt',text)
        self.assertEqual(read_json(self.root/'logs'/'runtime-state.json')['request_id'],11)

    def test_diagnostics_slow_or_failed_disk_never_blocks_producer(self):
        log=RuntimeJournal(self.root/'logs',capacity=2);entered=threading.Event();release=threading.Event()
        def slow(row):entered.set();release.wait(3);raise PermissionError('injected log disk failure')
        with patch.object(log,'_write',side_effect=slow):
            log.start();log.emit('start');self.assertTrue(entered.wait(1))
            started=time.monotonic()
            for i in range(100):log.emit('event',request_id=i)
            self.assertLess(time.monotonic()-started,.2);self.assertGreater(log.dropped,0)
            release.set();log.close(2)
        self.assertGreater(log.write_failures,0)
        self.assertFalse(log.thread.is_alive())

if __name__=='__main__':unittest.main(verbosity=2)
