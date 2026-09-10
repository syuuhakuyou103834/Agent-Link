import concurrent.futures
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import zipfile

root = Path(__file__).resolve().parent
archive = Path(r'C:\Users\infin\AppData\Local\AgentLinkGUI\workspace\cleanup-review-20260910\dist\AgentLink-GUI-0.3.9-Windows-x64.zip')
with zipfile.ZipFile(archive) as handle:
    for name in handle.namelist():
        if name.startswith('source/tests/') and name.endswith('.py'):
            target = root / 'v039' / name.removeprefix('source/')
            assert target.resolve().is_relative_to((root / 'v039').resolve())
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(handle.read(name))
old = Path(r'C:\AgentLink-GUI\dist\AgentLink-GUI-0.3.4\source\tests')
(root / 'v034' / 'tests').mkdir(exist_ok=True)
for path in old.glob('*.py'):
    shutil.copy2(path, root / 'v034' / 'tests' / path.name)
env = os.environ.copy()
env.pop('AGENTLINK_TEST_SHARE_ROOT', None)
env.update(PYTHONIOENCODING='utf-8', PYTHONDONTWRITEBYTECODE='1')
jobs = [('v034', 'waiting', ['WaitingTests']), ('v039', 'gaps', []),
        ('v039', 'freshness', []), ('v039', 'process_job', []),
        ('v039', 'cleanup_failures', []), ('v039', 'cleanup_admission', [])]
def run(job):
    version, name, args = job
    start = time.monotonic()
    cmd = [sys.executable, 'tests/test_' + name + '.py', *args]
    with (root / (version + '-' + name + '.log')).open('wb') as log:
        result = subprocess.run(cmd, cwd=root / version, env=env, stdout=log,
            stderr=subprocess.STDOUT, timeout=120, creationflags=subprocess.CREATE_NO_WINDOW)
    return {'version': version, 'suite': name, 'exit_code': result.returncode,
            'seconds': round(time.monotonic()-start, 2), 'command': cmd}
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    results = list(pool.map(run, jobs))
(root / 'regression-results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
print(json.dumps(results, indent=2))
