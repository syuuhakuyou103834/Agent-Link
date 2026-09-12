"""Reject accidental access to real UNC shares/data in the offline Python test process."""
import os
import faulthandler
from pathlib import Path
import runpy
import sys

def guard(event, args):
    if event not in ('open','os.listdir','os.scandir','os.mkdir','os.remove','os.rmdir','os.rename','os.link','os.symlink'):
        return
    paths = args[:2] if event in ('os.rename','os.link','os.symlink') else args[:1]
    for value in paths:
        if not isinstance(value, (str, bytes, os.PathLike)):
            continue
        path = os.fsdecode(value).replace('/', '\\')
        lower = path.lower()
        unc = lower.startswith('\\\\') and not lower.startswith('\\\\?\\') or lower.startswith('\\\\?\\unc\\')
        protected = str(Path(os.environ.get('LOCALAPPDATA',''))/'AgentLinkGUI').lower().rstrip('\\')
        if unc or lower == protected or lower.startswith(protected+'\\'):
            raise PermissionError('OFFLINE TEST blocked production/network path: ' + path)

if __name__ == '__main__':
    target = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(target.parent))
    sys.argv = sys.argv[1:]
    sys.dont_write_bytecode = True
    sys.addaudithook(guard)
    faulthandler.enable()
    faulthandler.dump_traceback_later(90, repeat=True)
    try:
        runpy.run_path(str(target), run_name='__main__')
    finally:
        # Keep diagnostics armed on a non-daemon service thread stuck at exit.
        import threading
        if not any(t.is_alive() and not t.daemon and t is not threading.main_thread()
                   for t in threading.enumerate()):
            faulthandler.cancel_dump_traceback_later()
