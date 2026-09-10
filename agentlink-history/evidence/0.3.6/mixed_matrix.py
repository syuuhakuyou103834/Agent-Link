"""Local old/new service code matrix. Records acceptance separately from script success."""
import importlib
import importlib.util
import json
from pathlib import Path
import sys
import uuid
ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / 'source'), str(ROOT / 'source/tests')]
from app.engine import NodeService
from app.storage import Settings, read_json
from test_system import until
results = []
for version, folder in [('0.3.4','completion-20260910'), ('0.3.5','followup-20260910')]:
    old = ROOT.parent / folder / 'source/app'
    alias = 'legacy_' + version.replace('.','_')
    spec = importlib.util.spec_from_file_location(alias, old / '__init__.py', submodule_search_locations=[str(old)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[alias] = module
    spec.loader.exec_module(module)
    old_engine = importlib.import_module(alias + '.engine')
    old_storage = importlib.import_module(alias + '.storage')
    for new_role in ('A','B'):
        old_role = 'B' if new_role == 'A' else 'A'
        root = ROOT / 'evidence' / ('mix-' + uuid.uuid4().hex[:8])
        root.mkdir()
        nodes, events = {}, []
        try:
            for role, cls, settings in ((new_role,NodeService,Settings),
                                       (old_role,old_engine.NodeService,old_storage.Settings)):
                nodes[role] = cls(settings(role=role,shared_root=str(root / 'share')),root / role,
                    lambda k,v:events.append((k,v)), [sys.executable,str(ROOT / 'source/tests/mock_server.py'),
                                                     role,str(root / (role + '-calls.jsonl'))])
                nodes[role].start()
            until(lambda: all(n.connected for n in nodes.values()) and all(
                read_json(root / 'share/nodes' / (r + '.json')) for r in ('A','B')))
            def calls(role):
                path = root / (role + '-calls.jsonl')
                return [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines()] if path.exists() else []
            nodes[new_role].command('start',topic='new initiator checks old capability',rounds=1)
            until(lambda:not nodes[new_role].start_pending)
            assert len(calls(new_role)) == len(calls(old_role)) == 0
            assert not list((root / 'share/jobs').iterdir())
            results.append(dict(new_version='0.3.6',old_version=version,new_role=new_role,old_role=old_role,
                initiator_version='0.3.6',requests_A=0,requests_B=0,status='PASS_REJECTED',evidence=str(root)))
            nodes[old_role].command('start',topic='old initiator behavior',rounds=1)
            if version == '0.3.4':
                until(lambda:len(calls(old_role))==1)
                until(lambda:nodes[old_role].active and read_json(root / 'share/jobs' /
                    nodes[old_role].active['id'] / 'state.json',{}).get('status')=='waiting_peer')
            else:
                until(lambda:not nodes[old_role].start_pending)
            assert len(calls(old_role)) == (1 if version=='0.3.4' else 0)
            assert len(calls(new_role)) == 0
            results.append(dict(new_version='0.3.6',old_version=version,new_role=new_role,old_role=old_role,
                initiator_version=version,requests_A=len(calls('A')),requests_B=len(calls('B')),
                status='FAIL_ZERO_REQUEST_CONTRACT' if version=='0.3.4' else 'PASS_REJECTED',evidence=str(root)))
        finally:
            for node in nodes.values():
                node.stop()
            for node in nodes.values():
                node.thread.join(15)
                assert not node.thread.is_alive()
(ROOT / 'evidence/mixed-version-matrix.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
print(json.dumps(results,indent=2),flush=True)
