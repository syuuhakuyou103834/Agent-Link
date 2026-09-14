"""Independent receipt/body corruption, capacity and I/O failure boundary checks."""
import json,os,socket,sys,threading,time,unittest,uuid
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from fixture_paths import fs,output_root
from app import received_results as rr
from app.context_view import digest
from app.storage import atomic_json
from app.file_output import save_text,ExportWriter
from app.diagnostics import DetailedErrors

class ResultContracts(unittest.TestCase):
    def setUp(self):self.root=output_root()/('results023-'+uuid.uuid4().hex[:8]);fs(self.root).mkdir()
    def test_null_wrong_type_and_invalid_identity_block(self):
        for n,value in enumerate((None,[],False,'text',{'job_id':'wrong'})):
            data=self.root/str(n);atomic_json(rr.directory(data,'job','000-A')/'result.json',value)
            with self.assertRaises(ValueError):rr.load(data,'job','000-A','A')
    def test_missing_record_only_allowed_when_not_required(self):
        self.assertIsNone(rr.load(self.root,'job','000-A','A'))
        with self.assertRaisesRegex(ValueError,'缺失'):rr.load(self.root,'job','000-A','A',True)
    def test_large_body_roundtrip_idempotence_and_corruption(self):
        result={'answer':'中文'*(1400000),'status':'completed'}
        receipt=rr.save(self.root,'job','000-A','A','instance',result)
        self.assertLess(fs(receipt).stat().st_size,4096)
        body=receipt.parent/'body.json';self.assertGreater(fs(body).stat().st_size,8*1024*1024)
        self.assertEqual(rr.load(self.root,'job','000-A','A')['result'],result)
        self.assertEqual(rr.save(self.root,'job','000-A','A','new-instance',result),receipt)
        original=fs(body).read_bytes();fs(body).write_bytes(original+b' ')
        with self.assertRaisesRegex(ValueError,'长度或摘要'):rr.load(self.root,'job','000-A','A')
    def test_legacy_large_result_is_accepted_without_rewriting(self):
        value={'answer':'x'*(8*1024*1024)}
        path=rr.directory(self.root,'job','000-A')/'result.json'
        atomic_json(path,dict(schema=1,job_id='job',step='000-A',role='A',host=socket.gethostname(),result=value,sha256=digest(value)))
        original=fs(path).read_bytes()
        self.assertEqual(rr.load(self.root,'job','000-A','A')['result'],value)
        self.assertEqual(rr.save(self.root,'job','000-A','A','i',value),path)
        self.assertEqual(fs(path).read_bytes(),original)
    def test_incomplete_commit_and_oversize_preserve_body_but_block(self):
        value={'answer':'retained original'}
        with patch.object(rr,'MAX_BODY',4):
            with self.assertRaisesRegex(ValueError,'原始正文已保留'):rr.save(self.root,'job','000-A','A','i',value)
        bodies=list(fs(rr.directory(self.root,'job','000-A')).glob('result-v2.partial-*/body.json'))
        self.assertEqual(len(bodies),1);self.assertEqual(json.loads(bodies[0].read_text(encoding='utf-8')),value)
        with self.assertRaisesRegex(ValueError,'未提交'):rr.load(self.root,'job','000-A','A')
    def test_file_access_denial_never_becomes_absent(self):
        with patch.object(rr,'_exists',side_effect=PermissionError('denied')):
            with self.assertRaises(PermissionError):rr.load(self.root,'job','000-A','A')

class OutputContracts(unittest.TestCase):
    def setUp(self):self.root=output_root()/('output023-'+uuid.uuid4().hex[:8]);fs(self.root).mkdir()
    def deep(self,name):
        path=self.root/('中文目录'*12)/('深目录'*18)/('目标目录'*12)/('末级长目录'*18)/name;fs(path.parent).mkdir(parents=True,exist_ok=True)
        self.assertGreater(len(str(path)),260);return path
    def test_export_atomic_unicode_deep_and_failure_preserves_old(self):
        path=self.deep('handoff.md');save_text(path,'原始内容')
        original=fs(path).read_bytes();self.assertTrue(original.startswith(b'\xef\xbb\xbf'))
        with patch('app.file_output.os.replace',side_effect=PermissionError('denied')):
            with self.assertRaises(PermissionError):save_text(path,'替换内容')
        self.assertEqual(fs(path).read_bytes(),original)
        save_text(path,'新内容');self.assertEqual(fs(path).read_text(encoding='utf-8-sig'),'新内容')
    def test_export_worker_returns_without_waiting_for_slow_disk(self):
        gate=threading.Event();started=threading.Event();events=[]
        def slow(*_):started.set();gate.wait(5)
        with patch('app.file_output.save_text',side_effect=slow):
            worker=ExportWriter(lambda *v:events.append(v))
            try:
                self.assertTrue(worker.submit(str(self.root/'x'),'body'));self.assertTrue(started.wait(2))
                self.assertTrue(worker.thread.is_alive());self.assertFalse(events)
            finally:gate.set();worker.close(3)
        self.assertEqual(events[0][0],'export_result');self.assertEqual(events[0][1]['error'],'')
    def test_error_log_long_path_and_failure_health_are_separate(self):
        path=self.deep('agentlink-errors.jsonl');health=[]
        writer=DetailedErrors(path.parent,health.append)
        try:
            writer.submit({'message':'first failure','traceback':'test'})
            until=lambda:None
            deadline=time.monotonic()+3
            while writer.written<1 and time.monotonic()<deadline:time.sleep(.02)
            self.assertEqual(json.loads(fs(path).read_text(encoding='utf-8'))['message'],'first failure')
            with patch.object(writer,'_write',side_effect=PermissionError('disk denied')):
                writer.submit({'message':'second failure'})
                deadline=time.monotonic()+3
                while writer.write_failures<1 and time.monotonic()<deadline:time.sleep(.02)
                self.assertEqual(writer.write_failures,1)
                self.assertTrue(any(h['write_failures']==1 for h in health))
        finally:writer.close(3)

    def test_original_zip_receipt_rejects_wrong_hash_and_unsafe_entries(self):
        import hashlib,zipfile
        from app.evidence_receipt import verify
        archive=self.root/'evidence.zip'
        with zipfile.ZipFile(fs(archive),'w') as z:z.writestr('report.md','independent fixture')
        sha=hashlib.sha256(fs(archive).read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError,'SHA-256 不匹配'):
            verify(archive,'0'*64,self.root/'bad','conversation','job','001-B','B','A')
        self.assertFalse(fs(self.root/'bad').exists())
        record=verify(archive,sha,self.root/'ok','conversation','job','001-B','B','A')
        self.assertEqual(record['status'],'hash_verified');self.assertFalse(record['agent_read']);self.assertFalse(record['tests_executed'])
        with zipfile.ZipFile(fs(archive),'w') as z:z.writestr('../outside.txt','bad')
        sha=hashlib.sha256(fs(archive).read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError,'不安全'):verify(archive,sha,self.root/'unsafe','conversation','job','001-B','B','A')

if __name__=='__main__':unittest.main(verbosity=2)
