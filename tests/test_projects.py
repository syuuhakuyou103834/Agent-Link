import hashlib
import json
from pathlib import Path
import sys
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.projects import Projects, separate, add_issues, update_issue
from app import artifacts
from app.review_workflow import review_result, scoped_settings
from app.storage import atomic_json, read_json


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.root = ROOT / 'test-output' / ('project-' + uuid.uuid4().hex)
        self.source = self.root / 'source'; self.source.mkdir(parents=True)
        (self.source / 'hello.py').write_text('print("中文")\n', encoding='utf-8')
        (self.source / 'tests').mkdir(); (self.source / 'tests' / 'test_new.py').write_text('# untracked')
        (self.source / 'empty').mkdir()
        self.pid = uuid.uuid4().hex

    def package(self):
        return artifacts.publish(self.source, self.root / 'shared', self.pid, 'job', 1)

    def test_full_snapshot_includes_untracked_and_explicit_omissions(self):
        (self.source / '.env').write_text('not-to-be-read')
        (self.source / 'node_modules').mkdir()
        r, m = self.package()
        received, copied = artifacts.receive(self.root / 'shared', self.root / 'mirror', r)
        self.assertEqual(m, copied)
        self.assertTrue((received / 'tests' / 'test_new.py').exists())
        self.assertTrue((received / 'empty').is_dir())
        self.assertFalse((received / '.env').exists())
        self.assertEqual({v['path'] for v in m['omitted']}, {'.env', 'node_modules'})
        self.assertEqual(artifacts.receive(self.root / 'shared', self.root / 'mirror', r)[0], received)

    def test_corrupt_zip_blocks_before_extract(self):
        r, m = self.package()
        (self.root / 'shared' / r['manifest_sha256'] / 'source.zip').write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, '损坏'):
            artifacts.receive(self.root / 'shared', self.root / 'mirror', r)

    def test_late_modification_invalidates_snapshot(self):
        r, m = self.package(); received, _ = artifacts.receive(self.root / 'shared', self.root / 'mirror', r)
        (received / 'hello.py').write_text('modified')
        with self.assertRaises(ValueError): artifacts.verify(received, m)

    def test_names_reject_escape_ads_and_windows_aliases(self):
        for name in ('../escape', '/root', 'x\\y', 'file:ads', 'NUL.txt', 'a/../b', 'a.', 'a//b'):
            with self.subTest(name=name), self.assertRaises(ValueError): artifacts.safe_name(name)

    def test_hardlink_rejected(self):
        import os
        os.link(self.source / 'hello.py', self.source / 'alias.py')
        with self.assertRaisesRegex(ValueError, '硬链接'): self.package()

    def test_nested_bindings_and_shared_root_rejected(self):
        p = Projects(self.root / 'data'); p.save('one', str(self.source), 'A', self.pid)
        with self.assertRaises(ValueError): p.save('two', str(self.source / 'empty'), 'A')
        with self.assertRaises(ValueError): p.bound(self.pid, 'A', self.source / 'shared')

    def test_project_catalog_does_not_publish_local_path(self):
        p = Projects(self.root / 'data'); p.save('one', str(self.source), 'A', self.pid)
        p.publish(self.root / 'shared', 'A')
        catalog = read_json(self.root / 'shared' / 'projects' / 'A.json')
        self.assertNotIn('directory', catalog['projects'][0])

    def test_review_needs_hash_all_changes_and_test_evidence(self):
        r, m = self.package()
        base = dict(snapshot=r['manifest_sha256'], decision='passed', summary='ok', scope=m['changed'], tests=['command passed'], unverified=[], unrelated_issues=[])
        self.assertEqual(review_result(json.dumps(base), r, m)['decision'], 'passed')
        for delta in ({'snapshot':'wrong'}, {'scope':[]}, {'tests':[]}, {'unverified':['not tested']}):
            with self.assertRaises(ValueError): review_result(json.dumps(dict(base, **delta)), r, m)

    def test_permissions_and_issues(self):
        cfg = scoped_settings({}, self.source, self.root / 'scratch', 'review', [])
        rules = cfg['permission_profile']['filesystem']
        self.assertEqual(rules[str(self.source.resolve())], 'read')
        self.assertNotIn(':root', rules)
        summary = scoped_settings({}, self.source, self.root / 'scratch', 'summary', [])
        self.assertNotIn('write', summary['permission_profile']['filesystem'].values())
        add_issues(self.root, self.pid, 'job', 1, ['outside scope'])
        value = add_issues(self.root, self.pid, 'job', 1, ['outside scope'])
        self.assertEqual(len(value['issues']), 1)
        update_issue(self.root, self.pid, value['issues'][0]['id'], 'deferred')
        self.assertEqual(read_json(self.root / 'projects' / self.pid / 'issues.json')['issues'][0]['status'], 'deferred')

    def test_protocol_refuses_unconfirmed_permission_profile(self):
        from app.protocol import RpcClient
        client = RpcClient([], self.root)
        cfg = scoped_settings({'model':'mock'}, self.source, self.root/'scratch', 'review', [])
        calls=[]
        def fake(method, params, **kw):
            calls.append(method)
            return {'config':{}} if method=='config/read' else {'thread':{'id':'mock'}, 'sandbox':{'type':'dangerFullAccess'}}
        client.call = fake
        with self.assertRaisesRegex(RuntimeError, '未确认'):
            client.new_thread(cfg, str(self.root/'scratch'), 'test')
        self.assertNotIn('turn/start', calls)

    def test_ready_missing_and_wrong_job_rejected(self):
        r, m = self.package()
        (self.root/'shared'/r['manifest_sha256']/'ready.json').unlink()
        with self.assertRaises(ValueError): artifacts.receive(self.root/'shared', self.root/'mirror', r)
        with self.assertRaises(ValueError): artifacts.validate_manifest(m, dict(r, job_id='other'))

    def test_code_metadata_strict_budget_and_project_id(self):
        from app.storage import Mailbox
        box = Mailbox(self.root/'shared', self.root/'data'); box.connect()
        meta = box.create('test', 3, unlimited=True)
        meta.update(mode='code', project={'id':self.pid}, budget=7)
        box.validate_meta(meta, meta['id'])
        for value in (7.0, True, 9):
            with self.assertRaises(ValueError): box.validate_meta(dict(meta, budget=value),meta['id'])
        with self.assertRaises(ValueError): box.validate_meta(dict(meta,project={'id':'../other'}),meta['id'])


    def test_windows_long_project_paths_roundtrip(self):
        from app.storage import io_path
        leaf = self.source
        for i in range(5):
            leaf = leaf / ('long-project-directory-' + str(i))
        io_path(leaf).mkdir(parents=True)
        io_path(leaf/'中文-long-file.py').write_text('untracked long path', encoding='utf-8')
        r, m = self.package()
        target, _ = artifacts.receive(self.root/'shared', self.root/'mirror', r)
        copied = target / (leaf/'中文-long-file.py').relative_to(self.source)
        self.assertGreater(len(str(copied)), 260)
        self.assertEqual(io_path(copied).read_text(encoding='utf-8'), 'untracked long path')


if __name__ == '__main__': unittest.main()
