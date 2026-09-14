"""Bounded, non-blocking, metadata-only runtime diagnostics. Never sends data."""
from pathlib import Path
import json
import os
import queue
import threading
import time
from .storage import atomic_json, io_path

FIELDS=frozenset(('role','instance','host_pid','server_pid','job_id','conversation_id','status',
    'previous_status','peer_instance','peer_status','peer_seq','heartbeat_seq','peer_verified',
    'peer_age_seconds','execution_locked','cleanup_pending','reason_code','channel','outage_seconds',
    'method','request_id','thread_id','turn_id','request_state','step','elapsed_seconds'))


class RuntimeJournal:
    def __init__(self, directory, capacity=256, max_bytes=4*1024*1024, backups=4):
        self.directory=Path(directory)
        self.events=queue.Queue(maxsize=capacity)
        self.max_bytes,self.backups=max_bytes,backups
        self.dropped=0;self.write_failures=0;self.last_error_type='';self.written=0
        self.stopping=threading.Event();self.thread=None

    def start(self):
        if self.thread is not None:return
        self.thread=threading.Thread(target=self._run,name='AgentLink-diagnostics',daemon=True)
        self.thread.start()

    def emit(self,event,**fields):
        if self.thread is None or self.stopping.is_set():return
        row=dict(schema=1,event=str(event)[:64],wall_time=time.time(),monotonic=time.monotonic())
        row.update({k:(v[:256] if isinstance(v,str) else v) for k,v in fields.items()
                    if k in FIELDS and (v is None or type(v) in (str,int,float,bool))})
        try:self.events.put_nowait(row)
        except queue.Full:self.dropped+=1

    def health(self):
        return dict(dropped_events=self.dropped,write_failures=self.write_failures,
                    last_error_type=self.last_error_type,written_events=self.written,
                    queue_size=self.events.qsize(),writer_alive=bool(self.thread and self.thread.is_alive()))

    def _write(self,row):
        io_path(self.directory).mkdir(parents=True,exist_ok=True)
        path=self.directory/'runtime-events.jsonl'
        if io_path(path).exists() and io_path(path).stat().st_size>=self.max_bytes:
            io_path(self.directory/('runtime-events.jsonl.'+str(self.backups))).unlink(missing_ok=True)
            for n in range(self.backups-1,0,-1):
                old=self.directory/('runtime-events.jsonl.'+str(n))
                if io_path(old).exists():os.replace(io_path(old),io_path(self.directory/('runtime-events.jsonl.'+str(n+1))))
            os.replace(io_path(path),io_path(self.directory/'runtime-events.jsonl.1'))
        row=dict(row,diagnostics=self.health())
        with io_path(path).open('a',encoding='utf-8') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
        atomic_json(self.directory/'runtime-state.json',row)

    def _run(self):
        while not self.stopping.is_set() or not self.events.empty():
            try:row=self.events.get(timeout=.1)
            except queue.Empty:continue
            try:self._write(row);self.written+=1;self.last_error_type=''
            except Exception as error:
                self.write_failures+=1;self.last_error_type=type(error).__name__
            finally:self.events.task_done()

    def close(self,timeout=.3):
        self.stopping.set()
        if self.thread:self.thread.join(timeout)


class DetailedErrors(RuntimeJournal):
    """Separate private error channel; its failures cannot hide behind event health."""
    def __init__(self,directory,notify):
        super().__init__(directory,capacity=64)
        self.notify=notify
    def submit(self,record):
        if self.thread is None:self.start()
        record=dict(record)
        for field in ('message','traceback'):
            if len(record.get(field,''))>65536:
                record[field]=record[field][:65536];record[field+'_truncated']=True
        try:self.events.put_nowait(record)
        except queue.Full:
            self.dropped+=1;self._notify()
    def _notify(self):
        try:self.notify(self.health())
        except Exception:pass
    def _write(self,row):
        io_path(self.directory).mkdir(parents=True,exist_ok=True)
        path=self.directory/'agentlink-errors.jsonl'
        if io_path(path).exists() and io_path(path).stat().st_size>=self.max_bytes:
            io_path(self.directory/'agentlink-errors.jsonl.4').unlink(missing_ok=True)
            for n in (3,2,1):
                old=self.directory/('agentlink-errors.jsonl.'+str(n))
                if io_path(old).exists():os.replace(io_path(old),io_path(self.directory/('agentlink-errors.jsonl.'+str(n+1))))
            os.replace(io_path(path),io_path(self.directory/'agentlink-errors.jsonl.1'))
        with io_path(path).open('a',encoding='utf-8') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
    def _run(self):
        while not self.stopping.is_set() or not self.events.empty():
            try:row=self.events.get(timeout=.1)
            except queue.Empty:continue
            try:self._write(row);self.written+=1;self.last_error_type=''
            except Exception as error:
                self.write_failures+=1;self.last_error_type=type(error).__name__
            finally:self.events.task_done();self._notify()
