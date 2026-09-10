"""Observe real old/new service code locally. Diagnostic exit 0 is NOT mixed-version acceptance."""
import importlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import uuid
ROOT = Path(__file__).resolve().parent
OLD = ROOT.parent / 'completion-20260910/source/app'
sys.path[:0] = [str(ROOT / 'source'), str(ROOT / 'source/tests')]
spec = importlib.util.spec_from_file_location('legacy034', OLD / '__init__.py', submodule_search_locations=[str(OLD)])
module = importlib.util.module_from_spec(spec)
sys.modules['legacy034'] = module
spec.loader.exec_module(module)
legacy_engine = importlib.import_module('legacy034.engine')
legacy_storage = importlib.import_module('legacy034.storage')
from app.engine import NodeService
from app.storage import Settings, read_json
from test_system import until
results = []
for new_role in ('A','B'):
    old_role = 'B' if new_role == 'A' else 'A'
    root = ROOT / 'evidence' / ('mix-' + uuid.uuid4().hex[:8])
    root.mkdir()
    nodes, events = {}, []
    try:
        for role, engine, settings in ((new_role, NodeService, Settings),
                                      (old_role, legacy_engine.NodeService, legacy_storage.Settings)):
            nodes[role] = engine(settings(role=role, shared_root=str(root / 'share')),
                root / role, lambda k,v: events.append((k,v)),
                [sys.executable, str(ROOT / 'source/tests/mock_server.py'), role, str(root / (role + '-calls.jsonl'))])
            nodes[role].start()
        until(lambda: all(n.connected for n in nodes.values()) and all(
            read_json(root / 'share/nodes' / (r + '.json')) for r in ('A','B')))
        def calls(role):
            path = root / (role + '-calls.jsonl')
            return [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines()] if path.exists() else []
        nodes[new_role].command('start', topic='new initiator must reject legacy capability', rounds=1)
        until(lambda: not nodes[new_role].start_pending)
        assert len(calls(new_role)) == len(calls(old_role)) == 0
        assert not list((root / 'share/jobs').iterdir())
        nodes[old_role].command('start', topic='legacy initiator still sends its draft', rounds=1)
        until(lambda: len(calls(old_role)) == 1)
        until(lambda: any(k == 'error' and '兼容' in v.get('message','') for k,v in events))
        # Wait for the old initiator to reach its peer wait, proving first call completed.
        until(lambda: nodes[old_role].active and read_json(
            root / 'share/jobs' / nodes[old_role].active['id'] / 'state.json', {}).get('status') == 'waiting_peer')
        assert len(calls(old_role)) == 1 and len(calls(new_role)) == 0
        results.append({'new_role':new_role, 'old_role':old_role, 'evidence':str(root),
            'new_initiator_requests':0, 'new_receiver_requests':0, 'old_initiator_requests':1,
            'whole_system_zero_request_contract':'FAIL',
            'meaning':'new node refuses safely; unmodified 0.3.4 initiator lacks the pre-send compatibility gate'})
    finally:
        for node in nodes.values():
            node.stop()
        for node in nodes.values():
            node.thread.join(15)
            assert not node.thread.is_alive()
(ROOT / 'evidence/mixed-version-observation.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
print(json.dumps(results, indent=2), flush=True)
