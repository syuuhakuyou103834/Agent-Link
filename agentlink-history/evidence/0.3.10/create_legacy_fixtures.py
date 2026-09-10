"""Generate migration inputs with actual 0.3.4 code; no production writes."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys

base = Path(__file__).resolve().parent
old = Path(r'C:\AgentLink-review-20260911\v034')
sys.path.insert(0, str(old))
from app import __version__
from app.storage import Settings, Mailbox, read_json

out = base / 'source' / 'tests' / 'fixtures'
out.mkdir(exist_ok=True)
temp = base / 'legacy-generation'
Settings(codex='mock.exe', auto_connect=False, timeout_seconds=900).save(temp)
(out / '034-settings.json').write_bytes((temp / 'settings.json').read_bytes())
box = Mailbox(temp / 'share', temp / 'local')
box.connect()
meta = box.create('0.3.4 真实格式的已完成中文历史', 1, unlimited=True)
turns = []
for index in range(3):
    role = 'A' if index % 2 == 0 else 'B'
    turns.append({'role':role, 'index':index, 'step':f'{index:03d}-{role}',
                  'job_id':meta['id'], 'status':'completed', 'answer':'LEGACY-034-ANSWER-' + str(index)})
fixture = {'meta':meta, 'control':{'notes':['LEGACY-NOTE']}, 'turns':turns, 'state':{'status':'completed'}}
(out / '034-history.json').write_text(json.dumps(fixture,ensure_ascii=False,indent=2),encoding='utf-8')
(out / '034-origin.json').write_text(json.dumps({'version':__version__, 'source':str(old),
    'storage_sha256':hashlib.sha256((old/'app/storage.py').read_bytes()).hexdigest(),
    'method':'Settings.save(timeout_seconds=900) and Mailbox.create(unlimited=True)'},indent=2),encoding='utf-8')
