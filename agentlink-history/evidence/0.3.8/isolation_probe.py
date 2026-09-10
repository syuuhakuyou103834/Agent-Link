"""Owned fixture trees plus an unrelated sentinel; real process handles."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT/'source'),str(ROOT/'source/tests')]
from app.protocol import RpcClient
from test_system import until
from app.storage import read_json
api=ctypes.WinDLL('kernel32',use_last_error=True)
api.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
api.OpenProcess.restype=wintypes.HANDLE
api.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
api.TerminateProcess.argtypes=[wintypes.HANDLE,wintypes.UINT]
api.CloseHandle.argtypes=[wintypes.HANDLE]
def save(p,v):p.write_text(json.dumps(v,indent=2),encoding='utf-8')
def launch(folder):
    folder.mkdir()
    c=RpcClient([sys.executable,str(ROOT/'crash_probe.py'),'server',str(folder)],folder/'logs')
    c.start();c.request('turn/start',{'input':[{'text':'isolated fixture'}]})
    until(lambda:(folder/'request.json').exists())
    return c,read_json(folder/'pids.json')
def open_handles(pids):
    handles={name:api.OpenProcess(0x100001,False,pid) for name,pid in pids.items()}
    assert all(handles.values())
    return handles
def exited(handles):return {name:api.WaitForSingleObject(h,0)==0 for name,h in handles.items()}
def cleanup(handles):
    for h in handles.values():
        if api.WaitForSingleObject(h,0)!=0:api.TerminateProcess(h,90);api.WaitForSingleObject(h,5000)
        api.CloseHandle(h)

if len(sys.argv)>1 and sys.argv[1]=='samehost':
    folder=Path(sys.argv[2]);clients=[];handles=[]
    try:
        for name in ('target','sibling'):
            c,pids=launch(folder/name);clients.append(c);handles.append(open_handles(pids))
        client_pids=[read_json(folder/name/'pids.json') for name in ('target','sibling')]
        clients[0].close()
        target=exited(handles[0]);sibling=exited(handles[1])
        assert all(target.values()) and not any(sibling.values())
        assert clients[1].call('initialize',{})=={}
        save(folder/'result.json',{'mode':'same_host_service_close','host_pid':os.getpid(),
            'pids':client_pids,'target_exited':target,'sibling_exited':sibling,'sibling_rpc_responded':True,'passed':True})
    finally:
        for c in clients:c.close()
        for h in handles:cleanup(h)
    sys.exit(0)

folder=ROOT/'evidence/isolation';folder.mkdir()
sentinel=subprocess.Popen([sys.executable,'-c','import time;time.sleep(180)'],creationflags=subprocess.CREATE_NO_WINDOW)
hosts=[];handles=[];logs=[]
try:
    same=folder/'samehost';same.mkdir()
    with (same/'host.log').open('wb') as log:
        p=subprocess.run([sys.executable,__file__,'samehost',str(same)],stdout=log,stderr=subprocess.STDOUT,
            timeout=40,creationflags=subprocess.CREATE_NO_WINDOW)
    assert p.returncode==0
    assert sentinel.poll() is None
    for name in ('target','sibling'):
        target=folder/name;target.mkdir()
        log=(target/'host.log').open('wb');logs.append(log)
        host=subprocess.Popen([sys.executable,str(ROOT/'crash_probe.py'),'host',str(ROOT/'source'),str(target)],
            stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
        hosts.append(host)
        until(lambda:(target/'request.json').exists())
        handles.append(open_handles(read_json(target/'pids.json')))
    hosts[0].kill();hosts[0].wait(10)
    until(lambda:all(exited(handles[0]).values()))
    assert hosts[1].poll() is None and not any(exited(handles[1]).values())
    assert sentinel.poll() is None
    result={'mode':'independent_host_kill','target_host_pid':hosts[0].pid,'sibling_host_pid':hosts[1].pid,
        'target_pids':read_json(folder/'target/pids.json'),'sibling_pids':read_json(folder/'sibling/pids.json'),
        'target_exited':exited(handles[0]),'sibling_exited':exited(handles[1]),
        'unrelated_sentinel_pid':sentinel.pid,'unrelated_sentinel_alive':True,'passed':True}
    save(folder/'result.json',result)
    save(ROOT/'evidence/isolation-results.json',[read_json(same/'result.json'),result])
    print(json.dumps(result,indent=2))
finally:
    for p in hosts:
        if p.poll() is None:p.kill();p.wait(10)
    for h in handles:cleanup(h)
    for log in logs:log.close()
    sentinel.terminate();sentinel.wait(10)
