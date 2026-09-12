from pathlib import Path
import json,os,sys,tempfile,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.storage import resolve_codex,find_codex,Settings

class RuntimeDiscoveryTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
  self.env=patch.dict(os.environ,{'LOCALAPPDATA':str(self.root)});self.env.start()
  self.base=self.root/'OpenAI'/'Codex'/'bin';self.new=self.base/'newversion'/'codex.exe'
  self.new.parent.mkdir(parents=True);self.new.write_bytes(b'fixture')
  self.legacy=self.base/'codex.exe';self.legacy.write_bytes(b'legacy')
 def tearDown(self):
  self.env.stop();self.temp.cleanup()
 def test_legacy_and_missing_managed_paths_follow_installed_runtime(self):
  self.assertEqual(resolve_codex(str(self.legacy)),str(self.new))
  self.assertEqual(resolve_codex(str(self.base/'removed'/'codex.exe')),str(self.new))
 def test_explicit_custom_and_existing_version_are_preserved(self):
  custom=self.root/'custom'/'codex.exe'
  self.assertEqual(resolve_codex(str(custom)),str(custom))
  old=self.base/'old'/'codex.exe';old.parent.mkdir();old.write_bytes(b'old')
  self.assertEqual(resolve_codex(str(old)),str(old))
 def test_auto_discovery_prefers_managed_runtime_over_legacy_path(self):
  with patch('shutil.which',return_value=str(self.legacy)):
   self.assertEqual(find_codex(),str(self.new))
 def test_no_managed_replacement_preserves_legacy(self):
  self.new.unlink()
  self.assertEqual(resolve_codex(str(self.legacy)),str(self.legacy))
 def test_settings_migration_preserves_other_fields_and_disk(self):
  data=self.root/'data';data.mkdir();p=data/'settings.json'
  raw={'codex':str(self.legacy),'role':'B','shared_root':str(self.root/'share'),'model':'mock','sandbox':'read-only'}
  p.write_text(json.dumps(raw),encoding='utf-8');before=p.read_bytes()
  settings=Settings.load(data)
  self.assertEqual(settings.codex,str(self.new));self.assertEqual(settings.role,'B')
  self.assertEqual(settings.model,'mock');self.assertEqual(settings.sandbox,'read-only')
  self.assertEqual(p.read_bytes(),before)

if __name__=='__main__':unittest.main(verbosity=2)
