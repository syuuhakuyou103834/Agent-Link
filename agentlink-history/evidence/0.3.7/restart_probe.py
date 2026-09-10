"""Hard-kill a local two-service host at four persisted execution windows.

Both services are on A's computer; this does not claim two-PC SMB validation.
"""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'source'
sys.path[:0] = [str(SOURCE), str(SOURCE / 'tests')]
from app.engine import NodeService
from app.storage import Settings, read_json, FileLock
import app.storage as storage
from test_system import until

def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')

def calls(folder):
    rows = []
    for role in ('A','B'):
        p = folder / (role + '-calls.jsonl')
        if p.exists(): rows += [json.loads(line) for line in p.read_text(encoding='utf-8').splitlines()]
    return rows

def host(folder, mode, recovering):
    shared = folder / 'share'
    nodes, events = {}, []
    def emit(kind, value):
        events.append((kind, value))
    for role in ('A','B'):
        nodes[role] = NodeService(Settings(role=role, shared_root=str(shared), auto_connect=True),
            folder / role, emit,
            [sys.executable, str(SOURCE/'tests/mock_server.py'), role, str(folder/(role+'-calls.jsonl')), '.01'])
        nodes[role].start()
    until(lambda:all(n.connected for n in nodes.values()))
    until(lambda:all(read_json(shared/'nodes'/(r+'.json'),{}).get('features') for r in nodes))
    save(folder / ('restart-pids.json' if recovering else 'host-pids.json'),
         {'host':os.getpid(), 'servers':{r:n.client.process.pid for r,n in nodes.items()}})
    try:
        if recovering:
            old = next((shared/'jobs').iterdir())
            before_calls = len(calls(folder))
            old_turn_ids = {r['turn'] for r in calls(folder)}
            time.sleep(1.5)
            assert len(calls(folder)) == before_calls
            nodes['A'].command('start', topic='must be rejected while old state nonterminal', rounds=1)
            until(lambda:not nodes['A'].start_pending)
            assert len(list((shared/'jobs').iterdir())) == 1
            assert len(calls(folder)) == before_calls
            assert any(k=='error' and '旧场次' in v.get('message','') for k,v in events)
            nodes['A'].selected = old.name
            nodes['A'].command('cancel')
            until(lambda:read_json(old/'state.json',{}).get('status')=='cancelled')
            terminal = (old/'state.json').read_bytes()
            nodes['A'].command('start', topic='valid next discussion after killed executors', rounds=1)
            until(lambda:len(list((shared/'jobs').iterdir()))==2)
            new = next(p for p in (shared/'jobs').iterdir() if p!=old)
            until(lambda:read_json(new/'state.json',{}).get('status')=='completed')
            until(lambda:all(not n.active and not n.start_pending for n in nodes.values()))
            assert len(calls(folder)) == before_calls + 3
            assert (old/'state.json').read_bytes() == terminal
            turns = [read_json(p) for p in sorted(new.glob('turn-*.json'))]
            assert [t['role'] for t in turns] == ['A','B','A']
            assert all(t['job_id']==new.name for t in turns)
            assert {t['turn_id'] for t in turns} == {r['turn'] for r in calls(folder)} - old_turn_ids
            save(folder/'recovery.json', {'passed':True, 'old_job':old.name, 'new_job':new.name,
                'old_requests':before_calls, 'new_requests':3, 'no_automatic_replay':True,
                'blocked_before_explicit_stop':True, 'old_terminal_unchanged':True,
                'new_order':[t['role'] for t in turns]})
            return

        def barrier():
            active = nodes['A'].active
            save(folder/'barrier.json', {'mode':mode, 'job_id':active['id'],
                'requests':len(calls(folder)), 'time':time.time()})
            while True: time.sleep(.1)

        if mode in ('before_send', 'inflight'):
            original_turn = nodes['A'].client.run_turn
            def run_turn(*args, **kwargs):
                if mode == 'before_send': barrier()
                return original_turn(*args, **kwargs)
            nodes['A'].client.run_turn = run_turn
        else:
            original_atomic = storage.atomic_json
            def atomic(path, value):
                path = Path(path)
                target = path.name=='turn-000-A.json' and path.parent.parent==shared/'jobs'
                if target and mode=='saved_unpublished': barrier()
                result = original_atomic(path,value)
                if target and mode=='published_unconfirmed': barrier()
                return result
            storage.atomic_json = atomic
        nodes['A'].command('start', topic='[LONG] held' if mode=='inflight' else 'hard crash', rounds=1)
        if mode=='inflight':
            until(lambda:len(calls(folder))==1)
            barrier()
        while True: time.sleep(.1)
    finally:
        for node in nodes.values(): node.stop()
        for node in nodes.values(): node.thread.join(15)
        save(folder/('recovery-events.json' if recovering else 'events.json'), events)

if len(sys.argv)>1 and sys.argv[1]=='host':
    host(Path(sys.argv[2]), sys.argv[3], sys.argv[4]=='recover')
    sys.exit(0)

api = ctypes.WinDLL('kernel32', use_last_error=True)
api.OpenProcess.argtypes = [wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
api.OpenProcess.restype = wintypes.HANDLE
api.WaitForSingleObject.argtypes = [wintypes.HANDLE,wintypes.DWORD]
api.CloseHandle.argtypes = [wintypes.HANDLE]
api.TerminateProcess.argtypes = [wintypes.HANDLE,wintypes.UINT]

results=[]
label = sys.argv[1] + '-' if len(sys.argv)>1 else ''
for mode in ('before_send','inflight','saved_unpublished','published_unconfirmed'):
    folder=ROOT/'evidence'/('restart-'+label+mode)
    folder.mkdir()
    handles=[]
    with (folder/'host.log').open('wb') as log:
        proc=subprocess.Popen([sys.executable,__file__,'host',str(folder),mode,'initial'],
            stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            until(lambda:(folder/'barrier.json').exists())
            pids=read_json(folder/'host-pids.json')
            for pid in pids['servers'].values():
                handle=api.OpenProcess(0x100001,False,pid)
                assert handle
                handles.append(handle)
            marker=read_json(folder/'barrier.json')
            job=folder/'share/jobs'/marker['job_id']
            assert marker['requests']==(0 if mode=='before_send' else 1)
            assert (job/'000-A.claim').exists()
            if mode=='saved_unpublished':
                assert (folder/'A/runs'/job.name/'turn-000-A.json').exists()
                assert not (job/'turn-000-A.json').exists()
            if mode=='published_unconfirmed': assert (job/'turn-000-A.json').exists()
            proc.kill();proc.wait(10)
            for handle in handles: assert api.WaitForSingleObject(handle,5000)==0
            for role in ('A','B'):
                with FileLock(folder/'share/nodes'/(role+'.lease')): pass
            with FileLock(folder/'share/discussion.lease'): pass
            restore=subprocess.run([sys.executable,__file__,'host',str(folder),mode,'recover'],
                stdout=log,stderr=subprocess.STDOUT,timeout=45,creationflags=subprocess.CREATE_NO_WINDOW)
            assert restore.returncode==0, str(folder/'host.log')
            result={'mode':mode,'pids':pids,'all_servers_exited_before_restart':True,
                'role_and_dispatch_locks_released':True,**read_json(folder/'recovery.json')}
            results.append(result)
            save(folder/'result.json',result)
        finally:
            if proc.poll() is None:proc.kill();proc.wait(10)
            for handle in handles:
                if api.WaitForSingleObject(handle,0)!=0:api.TerminateProcess(handle,99)
                api.CloseHandle(handle)
save(ROOT/('evidence/'+label+'restart-results.json'),results)
print(json.dumps(results,indent=2),flush=True)
