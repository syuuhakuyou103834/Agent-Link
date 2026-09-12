"""Real child-process exit at creation cutpoints; no model/server is started."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.engine import NodeService
from app.storage import Settings,Mailbox,io_path
from app.conversation import fingerprint
from app.process_job import ensure_host_guard


def node(root):
    n=NodeService(Settings(shared_root=str(root/'share'),auto_connect=False),root/'A',lambda *a:None)
    n.box=Mailbox(root/'share',root/'A');n.box.connect()
    n.client=SimpleNamespace(cleanup_pending=False,process=None)
    n._unified_compatible=lambda:'fixture-peer'
    n._assert_execution_idle=lambda:None
    n._model_context=lambda value:'fixture context'
    return n


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--child');parser.add_argument('--conversation')
    args=parser.parse_args()
    if args.child:
        n=node(args.out);put=n.box.put
        def crash(job,name,value):
            if args.child=='context' and name=='conversation-context.json':os._exit(73)
            put(job,name,value)
            if args.child=='ready' and name=='state.json' and value.get('status')=='running':os._exit(73)
        n.box.put=crash
        n._start_unified_job(n.conversations.get(args.conversation))
        raise AssertionError('cutpoint not reached')
    args.out.mkdir(parents=True,exist_ok=False)
    ensure_host_guard();rows=[]
    for cut in ('context','ready'):
        root=args.out/cut;root.mkdir();n=node(root)
        c=n.conversations.create('crash test')
        brief=dict(goal='test',directory='',permission='discuss',allowed_changes='none',acceptance=['check'],review_focus='check',round_limit=1)
        with n.conversations.edit(c['id']) as value:
            value.update(phase='waiting_peer',confirmed=brief,confirmation={'brief_sha256':fingerprint(brief)})
        process=subprocess.Popen([sys.executable,'-B',str(Path(__file__).resolve()),'--out',str(root),'--child',cut,'--conversation',c['id']],creationflags=subprocess.CREATE_NO_WINDOW)
        code=process.wait(timeout=20);assert code==73,code
        restarted=node(root)
        crashed=restarted.conversations.get(c['id']);assert crashed.get('creation')
        old=crashed['creation']['job_id']
        restarted._start_unified_job(crashed)
        current=restarted.conversations.get(c['id'])
        assert current['phase']=='working' and 'creation' not in current
        assert current['job']!=old
        assert restarted.box.get(old,'state.json')['status']=='failed'
        assert sum(restarted.box.get(p.name,'state.json',{}).get('status')=='running' for p in restarted.box.jobs())==1
        assert not list(io_path(root/'share').glob('jobs/*/call-*.json'))
        assert not list(io_path(root/'share').glob('jobs/*/*.claim'))
        rows.append(dict(cutpoint=cut,child_pid=process.pid,child_exit=code,new_service_instance=True,
                         abandoned_job=old,new_job=current['job'],passed=True,claims=0,model_calls=0))
    result=dict(passed=True,scope='real Windows process exit and new service object; local filesystem only',checks=rows)
    (args.out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))

if __name__=='__main__':main()
