"""Verify existing archive; native process enumeration avoids WMI discovery."""
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import zipfile
ROOT=Path(__file__).resolve().parent
EXTRACT=ROOT/'p2'
archive=ROOT/'source/dist/AgentLink-GUI-0.3.10-Windows-x64.zip'
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
files=[]
with zipfile.ZipFile(archive) as z:
    for name in z.namelist():
        if name.endswith('/'):continue
        sha=hashlib.sha256(z.read(name)).hexdigest()
        assert digest(EXTRACT/name)==sha,name
        files.append({'path':name,'sha256':sha})
for p in (ROOT/'source/app').glob('*.py'):
    assert digest(p)==digest(EXTRACT/'app'/p.name)==digest(EXTRACT/'source/app'/p.name)
env=os.environ.copy()
env.update(PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1',QT_QPA_PLATFORM='windows')
checks=[]
for name,command in [('identity',[str(EXTRACT/'runtime/python.exe'),'-c','import app;assert app.__version__=="0.3.10";print(app.__version__)']),
    ('windows',[str(EXTRACT/'runtime/python.exe'),str(EXTRACT/'source/tests/test_windows_startup.py')])]:
    with (ROOT/'evidence'/('final-package-'+name+'.log')).open('wb') as log:
        p=subprocess.run(command,cwd=EXTRACT,env=env,stdout=log,stderr=subprocess.STDOUT,
            timeout=50,creationflags=subprocess.CREATE_NO_WINDOW)
        assert p.returncode==0
        checks.append({'name':name,'returncode':0})
class ProcessEntry(ctypes.Structure):
    _fields_=[('dwSize',wintypes.DWORD),('cntUsage',wintypes.DWORD),('th32ProcessID',wintypes.DWORD),
        ('th32DefaultHeapID',ctypes.c_size_t),('th32ModuleID',wintypes.DWORD),('cntThreads',wintypes.DWORD),
        ('th32ParentProcessID',wintypes.DWORD),('pcPriClassBase',wintypes.LONG),('dwFlags',wintypes.DWORD),
        ('szExeFile',wintypes.WCHAR*260)]
api=ctypes.WinDLL('kernel32',use_last_error=True)
api.CreateToolhelp32Snapshot.argtypes=[wintypes.DWORD,wintypes.DWORD]
api.CreateToolhelp32Snapshot.restype=wintypes.HANDLE
api.Process32FirstW.argtypes=[wintypes.HANDLE,ctypes.POINTER(ProcessEntry)]
api.Process32NextW.argtypes=[wintypes.HANDLE,ctypes.POINTER(ProcessEntry)]
api.CloseHandle.argtypes=[wintypes.HANDLE]
api.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
api.OpenProcess.restype=wintypes.HANDLE
api.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
api.TerminateProcess.argtypes=[wintypes.HANDLE,wintypes.UINT]
def children(parent):
    snap=api.CreateToolhelp32Snapshot(2,0)
    assert snap!=ctypes.c_void_p(-1).value
    rows=[]
    try:
        entry=ProcessEntry();entry.dwSize=ctypes.sizeof(entry)
        found=api.Process32FirstW(snap,ctypes.byref(entry))
        while found:
            if entry.th32ParentProcessID==parent:rows.append(entry.th32ProcessID)
            found=api.Process32NextW(snap,ctypes.byref(entry))
    finally:api.CloseHandle(snap)
    return rows
user=ctypes.WinDLL('user32',use_last_error=True)
callback=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
user.EnumWindows.argtypes=[callback,wintypes.LPARAM]
user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
user.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
data=ROOT/'launcher-final/AgentLinkGUI';data.mkdir(parents=True)
(data/'settings.json').write_text(json.dumps({'timeout_seconds':0,'role':'B','auto_connect':False,'model':'test-preserved',
    'sandbox':'read-only','shared_root':str(ROOT/'unused-share'),'workspace':str(ROOT/'unused-workspace')}),encoding='utf-8')
sha=digest(data/'settings.json')
env['LOCALAPPDATA']=str(data.parent)
launches=[]
for attempt in range(2):
    p=subprocess.Popen([str(EXTRACT/'AgentLink.exe')],cwd=EXTRACT,env=env,creationflags=subprocess.CREATE_NO_WINDOW)
    handles={};windows=[]
    try:
        deadline=time.monotonic()+20
        def visit(hwnd,_):
            pid=wintypes.DWORD();user.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
            if pid.value in handles and user.IsWindowVisible(hwnd):
                title=ctypes.create_unicode_buffer(512);user.GetWindowTextW(hwnd,title,512)
                if 'AgentLink' in title.value:windows.append((hwnd,title.value,pid.value))
            return True
        while not windows and time.monotonic()<deadline:
            for pid in children(p.pid):
                if pid not in handles:
                    handle=api.OpenProcess(0x100001,False,pid)
                    assert handle
                    handles[pid]=handle
            user.EnumWindows(callback(visit),0)
            time.sleep(.1)
        assert windows,('native launcher discovery failed',p.poll(),list(handles))
        for hwnd,_,_ in windows:user.PostMessageW(hwnd,0x10,0,0)
        assert p.wait(15)==0
        assert all(api.WaitForSingleObject(h,5000)==0 for h in handles.values())
        assert digest(data/'settings.json')==sha
        assert not (data/'gui-errors.log').exists()
        launches.append({'attempt':attempt+1,'launcher_pid':p.pid,'child_pids':list(handles),
            'titles':[w[1] for w in windows],'settings_unchanged':True,'all_exited':True})
    finally:
        for h in handles.values():
            if api.WaitForSingleObject(h,0)!=0:api.TerminateProcess(h,89)
            api.CloseHandle(h)
        if p.poll() is None:p.kill();p.wait(10)
result={'zip':str(archive),'sha256':digest(archive),'verified_files':len(files),'files':files,
    'checks':checks,'launcher_checks':launches,
    'verification_method':'native Toolhelp and window enumeration'}
(ROOT/'evidence/package-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
(ROOT/'source/dist/SHA256SUMS-0.3.10.txt').write_text(digest(archive)+'  '+archive.name+'\n',encoding='ascii')
print(json.dumps({k:v for k,v in result.items() if k!='files'},ensure_ascii=False,indent=2))
