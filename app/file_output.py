"""User-requested text exports: worker-owned atomic saves, including long paths."""
import os,queue,threading,uuid
from pathlib import Path
from .storage import io_path

def save_text(path,text):
    path=Path(path);temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.partial')
    try:
        with io_path(temp).open('x',encoding='utf-8-sig') as f:
            f.write(text);f.flush();os.fsync(f.fileno())
        os.replace(io_path(temp),io_path(path))
    finally:
        try:io_path(temp).unlink(missing_ok=True)
        except OSError:pass  # Never remove the user's old destination on failure.

class ExportWriter:
    def __init__(self,emit):
        self.emit=emit;self.queue=queue.Queue(maxsize=2);self.stopping=threading.Event()
        self.thread=threading.Thread(target=self.run,name='AgentLink-export',daemon=True)
        self.thread.start()
    def submit(self,path,text):
        try:self.queue.put_nowait((path,text));return True
        except queue.Full:return False
    def run(self):
        while not self.stopping.is_set() or not self.queue.empty():
            try:path,text=self.queue.get(timeout=.1)
            except queue.Empty:continue
            error=''
            try:save_text(path,text)
            except Exception as exc:error=str(exc)
            finally:self.queue.task_done()
            self.emit('export_result',{'path':path,'error':error})
    def close(self,timeout=.3):
        self.stopping.set();self.thread.join(timeout)
