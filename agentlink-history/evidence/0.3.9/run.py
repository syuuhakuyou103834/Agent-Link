import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import sys
import time
ROOT = Path(__file__).resolve().parent
env = os.environ.copy()
env.pop('AGENTLINK_TEST_SHARE_ROOT', None)
env.update(PYTHONIOENCODING='utf-8', PYTHONDONTWRITEBYTECODE='1')
stamp = time.strftime('%H%M%S')
def run(name):
    log_path = ROOT / 'evidence' / (stamp + '-' + name + '.log')
    command = [sys.executable, 'tests/test_' + name + '.py']
    started = time.monotonic()
    with log_path.open('wb') as log:
        result = subprocess.run(command, cwd=ROOT / 'source', env=env, stdout=log,
            stderr=subprocess.STDOUT, timeout=900, creationflags=subprocess.CREATE_NO_WINDOW)
    return dict(suite=name, returncode=result.returncode, seconds=round(time.monotonic()-started, 2),
                log=str(log_path), command=command)
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    results = list(pool.map(run, sys.argv[1:]))
(ROOT / 'evidence' / (stamp + '-checks.json')).write_text(json.dumps(results, indent=2), encoding='utf-8')
print(json.dumps(results, indent=2), flush=True)
sys.exit(any(r['returncode'] for r in results))
