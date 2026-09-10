"""Own the Windows execution tree independently of the server PID's lifetime.

The private, non-inheritable job handle dies with the GUI/service host. No
breakaway flag is permitted. Failure to establish ownership blocks RPC startup.
"""
import ctypes
from ctypes import wintypes
import threading

_host_guard = None
_host_guard_lock = threading.Lock()


def ensure_host_guard():
    """Guard process creation itself; retained until OS closes host handles.

    Membership is inherited at creation, covering a host crash between Popen
    and assignment to the narrower service job. Never close this root guard
    during normal disconnect: the GUI itself is a member.
    """
    global _host_guard
    with _host_guard_lock:
        if _host_guard is None:
            guard = ProcessJob()
            guard.api.GetCurrentProcess.restype = wintypes.HANDLE
            if not guard.api.AssignProcessToJobObject(guard.handle, guard.api.GetCurrentProcess()):
                error = ctypes.WinError(ctypes.get_last_error())
                guard.close()
                raise error
            _host_guard = guard


class BasicLimits(ctypes.Structure):
    _fields_ = [('PerProcessUserTimeLimit', ctypes.c_longlong),
                ('PerJobUserTimeLimit', ctypes.c_longlong),
                ('LimitFlags', wintypes.DWORD),
                ('MinimumWorkingSetSize', ctypes.c_size_t),
                ('MaximumWorkingSetSize', ctypes.c_size_t),
                ('ActiveProcessLimit', wintypes.DWORD),
                ('Affinity', ctypes.c_size_t),
                ('PriorityClass', wintypes.DWORD),
                ('SchedulingClass', wintypes.DWORD)]


class IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in (
        'ReadOperationCount', 'WriteOperationCount', 'OtherOperationCount',
        'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]


class ExtendedLimits(ctypes.Structure):
    _fields_ = [('BasicLimitInformation', BasicLimits), ('IoInfo', IoCounters)] + [
        (name, ctypes.c_size_t) for name in ('ProcessMemoryLimit', 'JobMemoryLimit',
                                           'PeakProcessMemoryUsed', 'PeakJobMemoryUsed')]


class ThreadEntry(ctypes.Structure):
    _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD),
                ('th32ThreadID', wintypes.DWORD), ('th32OwnerProcessID', wintypes.DWORD),
                ('tpBasePri', wintypes.LONG), ('tpDeltaPri', wintypes.LONG),
                ('dwFlags', wintypes.DWORD)]


class ProcessJob:
    def __init__(self):
        self.handle = None
        self.api = ctypes.WinDLL('kernel32', use_last_error=True)
        self.api.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
        self.api.CreateJobObjectW.restype = wintypes.HANDLE
        self.api.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                                   wintypes.LPVOID, wintypes.DWORD]
        self.api.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.api.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
        if not self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def assign(self, process):
        if not self.api.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise ctypes.WinError(ctypes.get_last_error())

    def resume(self, process):
        # Popen closes the primary thread handle. Recover it through the public
        # Toolhelp API while the process is still CREATE_SUSPENDED, before any
        # application code can spawn a child outside this job.
        api = self.api
        api.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        api.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        api.Thread32First.argtypes = [wintypes.HANDLE, ctypes.POINTER(ThreadEntry)]
        api.Thread32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(ThreadEntry)]
        api.OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        api.OpenThread.restype = wintypes.HANDLE
        api.ResumeThread.argtypes = [wintypes.HANDLE]
        api.ResumeThread.restype = wintypes.DWORD
        snapshot = api.CreateToolhelp32Snapshot(4, 0)
        if snapshot == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        ids = []
        try:
            entry = ThreadEntry()
            entry.dwSize = ctypes.sizeof(entry)
            found = api.Thread32First(snapshot, ctypes.byref(entry))
            while found:
                if entry.th32OwnerProcessID == process.pid:
                    ids.append(entry.th32ThreadID)
                entry.dwSize = ctypes.sizeof(entry)
                found = api.Thread32Next(snapshot, ctypes.byref(entry))
        finally:
            api.CloseHandle(snapshot)
        if len(ids) != 1:
            raise RuntimeError('无法唯一识别暂停的执行服务主线程，未启动接口。')
        thread = api.OpenThread(2, False, ids[0])  # THREAD_SUSPEND_RESUME
        if not thread:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if api.ResumeThread(thread) != 1:
                raise RuntimeError('执行服务主线程的暂停状态异常，未启动接口。')
        finally:
            api.CloseHandle(thread)

    def close(self):
        if self.handle:
            handle, self.handle = self.handle, None
            self.api.CloseHandle(handle)
