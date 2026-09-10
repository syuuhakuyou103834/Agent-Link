from pathlib import Path
import hashlib
import json
import sys

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / 'SHA256SUMS.json').read_text(encoding='utf-8'))
errors = []
for row in manifest['files']:
    p = root / row['path']
    if not p.is_file():
        errors.append(row['path'] + ': missing')
    elif hashlib.sha256(p.read_bytes()).hexdigest() != row['sha256']:
        errors.append(row['path'] + ': hash mismatch')
print(json.dumps({'ok': not errors, 'files': len(manifest['files']), 'errors': errors}, ensure_ascii=False, indent=2))
sys.exit(bool(errors))
