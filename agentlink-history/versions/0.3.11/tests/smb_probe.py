"""Concurrent mailbox test; touches only a unique diagnostic subdirectory."""
import argparse
import collections
import json
import os
from pathlib import Path
import sys
import threading
import time
import uuid
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.storage import read_json, atomic_json, FileLock


def old_read(path):
    with path.open('rb') as handle:
        return json.loads(handle.read().decode('utf-8'))


def old_write(path, value):
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.partial')
    with temp.open('xb') as handle:
        handle.write(json.dumps(value, ensure_ascii=False).encode('utf-8'))
        handle.flush()
    for attempt in range(5):
        try:
            os.replace(temp, path)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(.05)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    parser.add_argument('--legacy', action='store_true')
    parser.add_argument('--guard', action='store_true')
    parser.add_argument('--seconds', type=int, default=12)
    parser.add_argument('--result', required=True)
    args = parser.parse_args()
    folder = Path(args.root) / ('probe-' + uuid.uuid4().hex)
    folder.mkdir(parents=True)
    target = folder / 'heartbeat.json'
    writer, reader = (old_write, old_read) if args.legacy else (atomic_json, read_json)
    if args.guard:
        def guarded(action):
            def invoke(*values):
                lock = FileLock(folder / 'probe-io.lease')
                deadline = time.monotonic() + 5
                while True:
                    try:
                        lock.acquire()
                        break
                    except RuntimeError:
                        if time.monotonic() >= deadline:
                            raise
                        time.sleep(.01)
                try:
                    return action(*values)
                finally:
                    lock.close()
            return invoke
        writer, reader = guarded(writer), guarded(reader)
    payload = '中文一致性校验 23℃；' * 500
    writer(target, {'sequence': 0, 'text': payload})
    errors, counts = [], collections.Counter()
    end = time.monotonic() + args.seconds
    def run_writer():
        sequence = 1
        while time.monotonic() < end:
            try:
                writer(target, {'sequence': sequence, 'text': payload})
                counts['writes'] += 1
            except OSError as e:
                errors.append({'operation': 'write', 'errno': e.errno, 'winerror': getattr(e, 'winerror', None), 'error': str(e)})
            sequence += 1
            time.sleep(.001)
    def run_reader(index):
        while time.monotonic() < end:
            try:
                value = reader(target)
                if not isinstance(value, dict) or value['text'] != payload:
                    errors.append({'operation': 'integrity', 'error': repr(value)[:100]})
                counts['reads_' + str(index)] += 1
            except (OSError, ValueError) as e:
                errors.append({'operation': 'read', 'errno': getattr(e, 'errno', None), 'winerror': getattr(e, 'winerror', None), 'error': str(e)})
    workers = [threading.Thread(target=run_writer)] + [threading.Thread(target=run_reader, args=(i,)) for i in range(4)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    result = {'mode': 'legacy-0.3.0' if args.legacy else 'fixed', 'folder': str(folder),
              'counts': dict(counts), 'error_count': len(errors), 'samples': errors[:12]}
    Path(args.result).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))
    return 0 if args.legacy or not errors else 1


if __name__ == '__main__':
    sys.exit(main())
