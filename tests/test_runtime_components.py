from fixture_paths import FixtureTemporaryDirectory
from fixture_paths import fs, entries
import json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.runtime_check import COMPANIONS,runtime_status,runtime_environment,require_project_runtime
from app.protocol import RpcClient
from app.review_workflow import ReviewWorkflow
from app.projects import FEATURE

class RuntimeComponentTests(unittest.TestCase):
 def setUp(self):
  self.tmp=FixtureTemporaryDirectory();self.root=Path(self.tmp.name)
  self.exe=self.root/'codex.exe';fs(self.exe).write_bytes(b'fixture')
  self.command=[str(self.exe),'app-server']
 def tearDown(self):self.tmp.cleanup()
 def complete(self):
  for n in COMPANIONS:(fs(self.root/n)).write_bytes(b'fixture')
 def test_missing_component_names_and_block_before_rpc(self):
  self.assertEqual(runtime_status(self.command)['missing'],list(COMPANIONS))
  c=RpcClient(self.command,self.root);sent=[];c.call=lambda *a,**kw:sent.append(a)
  with self.assertRaisesRegex(RuntimeError,'运行组件不完整'):
   c.scoped_thread({'permissions':'fixture'},str(self.root),'test')
  self.assertEqual(sent,[])
 def test_complete_runtime_passes_and_each_missing_helper_blocks(self):
  self.complete();self.assertTrue(require_project_runtime(self.command)['ready'])
  for n in COMPANIONS:
   p=self.root/n;fs(p).unlink()
   self.assertEqual(runtime_status(self.command)['missing'],[n])
   fs(p).write_bytes(b'fixture')
 def test_path_is_child_only_and_correct_directory_precedes_inherited(self):
  with patch.dict(os.environ,{'PATH':r'C:\stale-runtime'}):
   before=dict(os.environ);e=runtime_environment(self.command)
   self.assertEqual(e['PATH'].split(os.pathsep)[0],str(self.root))
   self.assertEqual(os.environ,before)
 def test_mock_command_not_treated_as_codex_install(self):
  self.assertFalse(runtime_status([sys.executable,'mock.py'])['checked'])
  self.assertTrue(runtime_status([sys.executable,'mock.py'])['ready'])
 def test_peer_missing_helpers_blocks_admission_before_a_model(self):
  peer={'features':[FEATURE],'capabilities':{'project_runtime':{'ready':False,'missing':[COMPANIONS[0]]}}}
  node=SimpleNamespace(box=SimpleNamespace(root=self.root),peer_role='B',settings=SimpleNamespace(role='A'),capabilities={'project_runtime':{'ready':True}})
  with patch('app.review_workflow.read_json',return_value=peer):
   with self.assertRaisesRegex(ValueError,'节点 B.*运行组件不完整'):ReviewWorkflow._code_compatible(node)
 def test_local_missing_helpers_blocks_admission(self):
  peer={'features':[FEATURE],'capabilities':{'project_runtime':{'ready':True}}}
  node=SimpleNamespace(box=SimpleNamespace(root=self.root),peer_role='B',settings=SimpleNamespace(role='A'),capabilities={'project_runtime':{'ready':False,'missing':[COMPANIONS[1]]}})
  with patch('app.review_workflow.read_json',return_value=peer):
   with self.assertRaisesRegex(ValueError,'节点 A.*运行组件不完整'):ReviewWorkflow._code_compatible(node)

if __name__=='__main__':unittest.main(verbosity=2)
