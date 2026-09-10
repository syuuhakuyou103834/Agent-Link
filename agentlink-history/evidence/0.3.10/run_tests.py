import concurrent.futures
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

root=Path(__file__).resolve().parent
source=root/'source'
env=os.environ.copy()
env.pop('AGENTLINK_TEST_SHARE_ROOT',None)
env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8')
batch=time.strftime('%Y%m%d-%H%M%S')
folder=root/'evidence'/batch
folder.mkdir()
names=sys.argv[1:] or [p.stem[5:] for p in sorted((source/'tests').glob('test_*.py'))]
def run(name):
    command=[sys.executable,'tests/test_'+name+'.py']
    started=time.monotonic()
    log=folder/(name+'.log')
    try:
        with log.open('wb') as handle:
            proc=subprocess.run(command,cwd=source,env=env,stdout=handle,stderr=subprocess.STDOUT,
                                timeout=300,creationflags=subprocess.CREATE_NO_WINDOW)
        result={'suite':name,'exit_code':proc.returncode}
    except Exception as error:
        result={'suite':name,'error':repr(error)}
    result.update(seconds=round(time.monotonic()-started,2),log=str(log),command=command)
    text=log.read_text(encoding='utf-8',errors='replace')
    match=re.search(r'Ran (\d+) tests?',text)
    result['tests']=int(match[1]) if match else None
    print(json.dumps(result),flush=True)
    return result
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    results=list(pool.map(run,names))
(folder/'results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
sys.exit(int(any(r.get('exit_code')!=0 for r in results)))
