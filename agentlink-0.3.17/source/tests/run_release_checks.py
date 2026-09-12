"""Bounded offline regression runner; records UTF-8 stdout and exact exit codes."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
out = ROOT.parent / 'evidence' / time.strftime('%Y%m%d-%H%M%S')
out.mkdir(parents=True)
temp = ROOT.parent / 'test-temp'; temp.mkdir(exist_ok=True)
env = dict(os.environ, PYTHONIOENCODING='utf-8', TEMP=str(temp), TMP=str(temp))
names = [p.name for p in sorted((ROOT / 'tests').glob('test_*.py')) if p.name not in ('test_endurance.py',)]
results = []
for name in names:
    started = time.monotonic()
    with (out / (name + '.log')).open('w', encoding='utf-8') as log:
        try:
            process = subprocess.run([sys.executable, str(ROOT / 'tests' / name)], cwd=ROOT,
                env=env, stdout=log, stderr=subprocess.STDOUT, timeout=360,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            code = process.returncode
        except subprocess.TimeoutExpired:
            code = -1
    results.append(dict(test=name, exit_code=code, seconds=round(time.monotonic()-started,2)))
    (out/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print(name, code, flush=True)
print(out, flush=True)
sys.exit(any(r['exit_code'] != 0 for r in results))
