import ctypes
from ctypes import wintypes
import json
api=ctypes.WinDLL('user32',use_last_error=True)
callback=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
api.EnumWindows.argtypes=[callback,wintypes.LPARAM]
api.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
api.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
rows=[]
def collect(hwnd,_):
    pid=wintypes.DWORD();api.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
    if pid.value in (45416,42932):
        text=ctypes.create_unicode_buffer(1000)
        api.GetWindowTextW(hwnd,text,1000)
        rows.append({'hwnd':hwnd,'pid':pid.value,'title':text.value,'visible':bool(api.IsWindowVisible(hwnd))})
        api.PostMessageW(hwnd,0x10,0,0)
    return True
api.EnumWindows(callback(collect),0)
print(json.dumps(rows,ensure_ascii=False))
