"""0.3.21 audit regressions: real local child/lease probes, no model calls."""
import gc
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import unittest
from unittest.mock import patch
import uuid
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from app import artifacts, context_view
from app.conversation import append_message
from app.engine import NodeService
from app.interruption import TechnicalInterruption
from app.protocol import RpcClient
from app.storage import FileLock, Mailbox, Settings, atomic_json, io_path, read_json
from test_context_view import sample


class AuditRegressions(unittest.TestCase):
    def setUp(self):
        self.root=__import__('fixture_paths').output_root()/('audit022-'+uuid.uuid4().hex[:8])
        io_path(self.root).mkdir(parents=True)

    def probe(self, path):
        command=[sys.executable,'-B','-c',
            'import sys;sys.path.insert(0,sys.argv[1]);from app.storage import FileLock;'
            'lease=FileLock(sys.argv[2]).acquire();print("acquired");lease.close()',str(ROOT),str(path)]
        p=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',errors='replace',
                         creationflags=subprocess.CREATE_NO_WINDOW,timeout=10)
        return dict(exit_code=p.returncode,stdout=p.stdout,stderr=p.stderr)

    def test_chat_cleanup_exception_keeps_lease_until_child_exit(self):
        node=NodeService(Settings(role='A',shared_root=str(self.root/'share')),self.root/'A',lambda *_:None)
        node.box=Mailbox(node.settings.shared_root,node.data);node.box.connect();node.connected=True
        client=RpcClient([sys.executable,str(ROOT/'tests/mock_server.py'),'A',str(self.root/'calls.jsonl')],self.root/'logs')
        node.client=client
        value=node.conversations.create('local cleanup test')
        with node.conversations.edit(value['id']) as current:
            msg=append_message(current,'user','local cleanup test','input',origin='A',target='A')
            current['pending'].append(msg['id'])
        value=node.conversations.get(value['id'])
        client.start();process=client.process;group=client.process_job
        path=node.box.root/'execution.lease'
        # Positive control: the independent process really observes a held lock.
        with FileLock(path): self.assertNotEqual(self.probe(path)['exit_code'],0)
        cleanup_error=None
        try:
            with patch.object(client,'new_thread',side_effect=RuntimeError('original preflight failure')), \
                 patch.object(group.api,'TerminateJobObject',return_value=0):
                try:node._unified_chat(value,msg)
                except RuntimeError as error:cleanup_error=str(error)
            gc.collect()
            probe=self.probe(path)
            receipt=dict(child_alive=process.poll() is None,lease_retained=node.execution_lock is not None,
                         chat_active=getattr(node,'chat_active',None),probe=probe,cleanup_error=cleanup_error,
                         real_model_requests=0)
            atomic_json(self.root/'cleanup-receipt.json',receipt)
            self.assertTrue(receipt['child_alive'])
            self.assertNotEqual(probe['exit_code'],0,'live old child must exclude another executor')
            self.assertIsNotNone(node.execution_lock)
            self.assertIsNone(getattr(node,'chat_active',None))
            with self.assertRaisesRegex(RuntimeError,'清理'):node._assert_execution_idle()
            self.assertIn('original preflight failure',str(node.conversations.get(value['id'])['attempts']))
        finally:
            client.close();node._release_execution()
        self.assertIsNotNone(process.poll())
        self.assertEqual(self.probe(path)['exit_code'],0)
        self.assertFalse(io_path(self.root/'calls.jsonl').exists())

    def test_heartbeat_failure_survives_interleaved_regular_pumps(self):
        node=NodeService(Settings(role='A',shared_root=str(self.root/'share')),self.root/'A',lambda *_:None)
        node.box=Mailbox(node.settings.shared_root,node.data);node.box.connect();node.connected=True
        node.active={'id':'fixture'};node.last_history=10000
        instant=[100.0];failures=[];interrupted=None
        def heartbeat(): failures.append(instant[0]);raise OSError('injected heartbeat I/O')
        with patch('app.engine.time.monotonic',side_effect=lambda:instant[0]), \
             patch.object(node.liveness,'clock',side_effect=lambda:instant[0]), \
             patch.object(node,'_heartbeat',side_effect=heartbeat),patch.object(node,'_control'), \
             patch.object(node,'_pump_node_inputs'),patch.object(node,'_drain_controls'),patch.object(node,'report_error'):
            for i in range(401):
                instant[0]=100+i/10
                try:node._pump()
                except TechnicalInterruption as error:
                    interrupted=dict(at=instant[0],details=error.details);break
        atomic_json(self.root/'heartbeat-receipt.json',dict(failures=failures,interruption=interrupted))
        self.assertIsNotNone(interrupted,'ordinary active pumps must not erase heartbeat outage')
        self.assertGreaterEqual(interrupted['at'],130)
        self.assertLess(interrupted['at'],132)

    def test_existing_index_deleted_is_rejected_without_recreation(self):
        value=sample();_,root,_=context_view.prepare(value,self.root/'evidence')
        io_path(root/'index.json').unlink()
        with self.assertRaises(ValueError):context_view.prepare(value,self.root/'evidence')
        self.assertFalse(io_path(root/'index.json').exists())

    def test_existing_index_null_is_rejected_without_overwrite(self):
        value=sample();_,root,_=context_view.prepare(value,self.root/'evidence')
        atomic_json(root/'index.json',None)
        with self.assertRaises(ValueError):context_view.prepare(value,self.root/'evidence')
        self.assertIsNone(read_json(root/'index.json'))

    def test_committed_whole_bundle_deleted_is_rejected(self):
        value=sample();_,root,_=context_view.prepare(value,self.root/'evidence')
        shutil.rmtree(io_path(root))
        with self.assertRaises(ValueError):context_view.prepare(value,self.root/'evidence')
        self.assertFalse(io_path(root).exists())

    def test_repeated_publish_reuses_receipt_without_partial_zip(self):
        source=self.root/'src';io_path(source).mkdir();io_path(source/'file.txt').write_text('content')
        args=(source,self.root/'delivery',uuid.uuid4().hex,'job',1)
        first,manifest=artifacts.publish(*args)
        for _ in range(3):
            current,copied=artifacts.publish(*args)
            self.assertEqual(current,first);self.assertEqual(copied,manifest)
        self.assertEqual(list(io_path(self.root/'delivery').glob('.partial-*')),[])


if __name__=='__main__':unittest.main(verbosity=2)
