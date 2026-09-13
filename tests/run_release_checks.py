"""Bounded local release checks with owned child trees and durable result receipts."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.process_job import ProcessJob, ensure_host_guard

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--python', type=Path, default=Path(sys.executable))
    parser.add_argument('--out', type=Path)
    parser.add_argument('--names', nargs='*')
    parser.add_argument('--keep-going', action='store_true')
    parser.add_argument('--timeout', type=int, default=240)
    args = parser.parse_args()
    if args.out is None:
        args.out = Path(tempfile.gettempdir()) / ('agentlink-checks-' + uuid.uuid4().hex[:8])
    if args.timeout <= 0:
        parser.error('--timeout must be positive')
    args.root = ROOT
    args.out = args.out.resolve()
    # A failed or interrupted attempt must remain intact.
    args.out.mkdir(parents=True, exist_ok=False)
    # Existing fixture assertions use ordinary pathlib globs; deep evidence
    # paths can exceed Win32 MAX_PATH and report an existing artifact as absent.
    # Keep fixture data short and isolated; retain its exact path in the receipt.
    temp = args.out / 'temp'
    temp.mkdir(parents=True, exist_ok=False)
    (args.out / 'environment.json').write_text(json.dumps(dict(
        source=str(ROOT), python=str(args.python), temp=str(temp), share=str(temp / 'share'),
        real_model_requests=0), indent=2), encoding='utf-8')
    env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONDONTWRITEBYTECODE='1',
               TEMP=str(temp), TMP=str(temp), AGENTLINK_TEST_SHARE_ROOT=str(temp / 'share'),
               AGENTLINK_TEST_SOURCE_ROOT=str(ROOT), AGENTLINK_TEST_OUTPUT_ROOT=str(args.out), AGENTLINK_TEST_WRITE_ROOT=str(args.out))
    names = args.names if args.names else [p.name for p in sorted((args.root / 'tests').glob('test_*.py'))
                                          if p.name != 'test_endurance.py']
    if any(Path(n).name != n or not n.startswith('test_') or not (ROOT / 'tests' / n).is_file() for n in names):
        parser.error('--names must name test scripts in source/tests')
    rows = []
    ensure_host_guard()
    for name in names:
        row = dict(test=name, started=time.strftime('%Y-%m-%dT%H:%M:%S%z'), status='running')
        rows.append(row)
        receipt = args.out / 'results.json'
        def save(): receipt.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding='utf-8')
        save()
        command = [str(args.python), '-B', str(args.root / 'tests/offline_test_guard.py'), str(args.root / 'tests' / name)]
        row['command'] = command
        started = time.monotonic()
        job = ProcessJob()
        process = None
        try:
            with (args.out / (name + '.log')).open('w', encoding='utf-8') as log:
                process = subprocess.Popen(command, cwd=args.root, env=env, stdout=log, stderr=subprocess.STDOUT,
                                           creationflags=subprocess.CREATE_NO_WINDOW | 0x4)
                row['pid'] = process.pid; save()
                job.assign(process); job.resume(process)
                try:
                    row['exit_code'] = process.wait(timeout=args.timeout)
                    row['status'] = 'passed' if row['exit_code'] == 0 else 'failed'
                except subprocess.TimeoutExpired:
                    row['status'] = 'timeout'; row['exit_code'] = None
        except Exception as error:
            row.update(status='blocked', error=repr(error))
        finally:
            try:
                job.close()
                # Assignment can fail while the newly created child is suspended.
                if process is not None and process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
                row['child_tree_cleanup'] = 'confirmed'
            except Exception as error:
                row.update(status='blocked', cleanup_error=repr(error))
            row['seconds'] = round(time.monotonic() - started, 2)
            logpath = args.out / (name + '.log')
            text = logpath.read_text('utf-8', errors='replace') if logpath.exists() else ''
            row['unittest_counts'] = [int(n) for n in re.findall(r'Ran (\d+) tests? in', text)]
            save()
        print(name, row['status'], row['seconds'], flush=True)
        if row['status'] != 'passed' and not args.keep_going:
            break
    result = {'expected_scripts':len(names), 'completed_scripts':len(rows),
              'passed':len(rows)==len(names) and all(r['status']=='passed' for r in rows),
              'real_model_requests':0, 'scope':'local offline checks with subprocess mocks'}
    (args.out / 'complete.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return 0 if result['passed'] else 1

if __name__ == '__main__':
    sys.exit(main())
