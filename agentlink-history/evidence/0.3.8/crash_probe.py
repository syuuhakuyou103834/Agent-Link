"""Real Windows process termination, exclusively owned offline fixtures."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
def save(path, value):
    path.write_text(json.dumps(value, indent=2), encoding='utf-8')

if len(sys.argv) > 1 and sys.argv[1] == 'server':
    folder = Path(sys.argv[2])
    for raw in sys.stdin:
        value = json.loads(raw)
        if value.get('method') == 'initialize':
            print(json.dumps({'id': value['id'], 'result': {}}), flush=True)
        elif value.get('method') == 'turn/start':
            child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(180)'],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW)
            save(folder / 'pids.json', {'server':os.getpid(), 'worker':child.pid})
            save(folder / 'request.json', value)
            print(json.dumps({'id':value['id'], 'result':{'turn':{'id':'held'}}}), flush=True)
    sys.exit(0)

if len(sys.argv) > 1 and sys.argv[1] == 'host':
    source, folder = Path(sys.argv[2]), Path(sys.argv[3])
    sys.path.insert(0, str(source))
    from app.protocol import RpcClient
    if folder.name.endswith('pre_assign'):
        from app.process_job import ProcessJob
        def held_assignment(job, process):
            save(folder / 'pids.json', {'server':process.pid})
            save(folder / 'request.json', {'method':'none; held before job assignment'})
            while True: time.sleep(.1)
        ProcessJob.assign = held_assignment
    client = RpcClient([sys.executable, str(Path(__file__)), 'server', str(folder)], folder / 'logs')
    try:
        client.start()
        client.run_turn('fixture', 'offline', 'A', '000-A', {'model':'mock','timeout_seconds':60},
            lambda view:None, lambda:None)
    except Exception as exc:
        save(folder / 'host-error.json', {'type':type(exc).__name__, 'message':str(exc)})
    finally:
        client.close()
    sys.exit(0)

kernel = ctypes.WinDLL('kernel32', use_last_error=True)
kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel.OpenProcess.restype = wintypes.HANDLE
kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel.CloseHandle.argtypes = [wintypes.HANDLE]
kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]

def until(predicate, timeout=15):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate(): return True
        time.sleep(.05)
    return False

if __name__ == '__main__':
    source = Path(sys.argv[1]).resolve()
    label = sys.argv[2]
    results = []
    modes = ('host_kill', 'server_kill') if label == 'baseline' else ('host_kill','server_kill','pre_assign')
    for mode in modes:
        folder = ROOT / 'evidence' / (label + '-' + mode)
        folder.mkdir()
        handles = {}
        with (folder / 'host.log').open('wb') as log:
            host = subprocess.Popen([sys.executable, str(Path(__file__)), 'host', str(source), str(folder)],
                stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                assert until(lambda:(folder / 'request.json').exists()), 'fixture failed before request'
                pids = json.loads((folder / 'pids.json').read_text())
                for name,pid in pids.items():
                    handles[name] = kernel.OpenProcess(0x100001, False, pid)
                    assert handles[name], (name,pid,ctypes.get_last_error())
                if mode in ('host_kill','pre_assign'):
                    host.kill(); host.wait(10)
                else:
                    assert kernel.TerminateProcess(handles['server'], 77)
                    host.wait(15)
                exited = {name:until(lambda h=handle:kernel.WaitForSingleObject(h,0)==0,5)
                          for name,handle in handles.items()}
                result = {'mode':mode, 'host_pid':host.pid, 'pids':pids, 'exited_before_cleanup':exited,
                    'request_count':0 if mode=='pre_assign' else 1,
                    'passed':all(exited.values()), 'source':str(source)}
                results.append(result)
                save(folder / 'result.json', result)
            finally:
                if host.poll() is None: host.kill(); host.wait(10)
                for handle in handles.values():
                    if kernel.WaitForSingleObject(handle,0)!=0:
                        kernel.TerminateProcess(handle, 88)
                        kernel.WaitForSingleObject(handle,5000)
                    kernel.CloseHandle(handle)
    save(ROOT / 'evidence' / (label + '-results.json'), results)
    print(json.dumps(results, indent=2))
    sys.exit(not all(row['passed'] for row in results))
