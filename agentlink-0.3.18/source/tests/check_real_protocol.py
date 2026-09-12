"""Validate installed Codex RPC without authenticating or invoking a model."""
import json
import os
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.protocol import RpcClient
from app.storage import find_codex

scratch = ROOT / 'test-output' / 'real-protocol'
scratch.mkdir(parents=True, exist_ok=True)
os.environ['CODEX_HOME'] = str(scratch / 'isolated-codex-home')
Path(os.environ['CODEX_HOME']).mkdir(exist_ok=True)
exe = sys.argv[1] if len(sys.argv) > 1 else find_codex()
client = RpcClient([exe, 'app-server', '--listen', 'stdio://'], scratch / 'logs')
try:
    client.start()
    tid = client.new_thread({'model': 'gpt-6-astra', 'sandbox': 'read-only'}, str(scratch),
                            'Protocol validation only; no model turn will be started.')
    capabilities = client.capabilities(str(scratch))
    result = {'initialize': True, 'thread_start': bool(tid), 'read_only': True,
              'model_turns': 0, 'isolated_profile': True, 'capability_errors': capabilities['errors']}
    (scratch / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))
finally:
    client.close()
