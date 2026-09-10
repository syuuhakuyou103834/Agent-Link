"""Portable offline review entry point; no Codex host, account or network used."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import uuid
ROOT=Path(__file__).resolve().parent
for _ in range(256):
    run=ROOT/('v'+uuid.uuid4().hex[:2])
    try:
        run.mkdir()
        break
    except FileExistsError:
        continue
else:
    raise RuntimeError('请解压到一个新的短目录后运行核验。')
(run/'evidence').mkdir()
result={'host':socket.gethostname(),'started':time.time(),'scope':'local offline mocks; not two-PC/SMB/permission acceptance',
        'model_requests':0,'run_dir':str(run),'steps':[],'status':'RUNNING'}
def save():
    (run/'RESULT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(result['status'],str(run/'RESULT.json'),flush=True)
try:
    if len(str(ROOT))>83:
        raise RuntimeError('核验包所在路径过长。请完整解压到较短目录，例如 C:\\AgentLinkReview，再运行 VERIFY.cmd。')
    manifest=json.loads((ROOT/'KIT-SHA256.json').read_text(encoding='utf-8'))
    for name,expected in manifest.items():
        path=(ROOT/name).resolve()
        assert path.is_relative_to(ROOT.resolve()),name
        assert hashlib.sha256(path.read_bytes()).hexdigest()==expected,name
    result['verified_input_files']=len(manifest)
    shutil.copytree(ROOT/'source',run/'source',ignore=shutil.ignore_patterns('__pycache__','*.pyc','test-output'))
    for name in ('run.py','crash_probe.py','restart_probe.py','isolation_probe.py'):
        shutil.copy2(ROOT/name,run/name)
    env=os.environ.copy()
    env.pop('AGENTLINK_TEST_SHARE_ROOT',None)
    env.update(PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1')
    commands=[('unit', [sys.executable,str(run/'run.py'),'cleanup_failures','process_job','repairs','peer_review','authority']),
        ('crash',[sys.executable,str(run/'crash_probe.py'),str(run/'source'),'portable']),
        ('restart',[sys.executable,str(run/'restart_probe.py'),'portable']),
        ('isolation',[sys.executable,str(run/'isolation_probe.py')])]
    for name,command in commands:
        print('Running offline verification:',name,flush=True)
        with (run/(name+'.log')).open('wb') as log:
            code=subprocess.run(command,cwd=run,env=env,stdout=log,stderr=subprocess.STDOUT,
                timeout=240,creationflags=subprocess.CREATE_NO_WINDOW).returncode
        result['steps'].append({'name':name,'returncode':code,'log':name+'.log'})
        if code:raise RuntimeError(name+' verification failed; see '+str(run/(name+'.log')))
    result['status']='PASS'
except Exception as error:
    result['status']='FAIL'
    result['error']=str(error)
finally:
    result['finished']=time.time()
    save()
sys.exit(result['status']!='PASS')
