"""Independent A-node behavior comparison, no real model or production state."""
import json
import os
from pathlib import Path
from types import SimpleNamespace
import sys
import time
from unittest.mock import patch

root = Path(sys.argv[1]).resolve()
sys.path[:0] = [str(root), str(root / 'tests')]
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from app import __version__, protocol
from app.storage import Mailbox, Settings, atomic_json, read_json
from app.context import prepare_context
from app.protocol import RpcClient, TurnView
from app.engine import NodeService

data = root / 'independent-probe'
data.mkdir(exist_ok=False)
results = {'version': __version__, 'scope': 'local synthetic comparison; zero external model calls', 'cases': {}}
def record(name, action):
    try:
        results['cases'][name] = {'result': action()}
    except Exception as error:
        results['cases'][name] = {'error_type': type(error).__name__, 'error': str(error)}

settings_dir = data / 'migrated-settings'
atomic_json(settings_dir / 'settings.json', {'timeout_seconds': 0, 'auto_connect': False, 'codex': 'mock.exe'})
record('load_034_settings_timeout_zero', lambda: {'timeout': Settings.load(settings_dir).timeout_seconds})
record('default_timeout', lambda: Settings().timeout_seconds)

box = Mailbox(data / 'share', data / 'local')
box.connect()
parent = box.create('0.3.4 无时限完整历史', 1)
parent.update(protocol=2, expires=None, wait_policy='unlimited')
box.put(parent['id'], 'meta.json', parent)
box.put(parent['id'], 'state.json', {'status': 'completed'})
for index in range(3):
    role = 'A' if index % 2 == 0 else 'B'
    step = f'{index:03d}-{role}'
    box.put(parent['id'], 'turn-' + step + '.json', {
        'role': role, 'index': index, 'step': step, 'status': 'completed', 'answer': '历史答复 ' + str(index)})
record('continue_034_protocol2_history', lambda: len(prepare_context(box, parent['id'])['discussions']))

view = TurnView('A', '002-A', 'same-thread')
view.turn_id = 'new-turn'
view.feed('turn/completed', {'threadId': 'same-thread', 'turnId': 'old-turn',
    'turn': {'id': 'old-turn', 'status': 'completed', 'items': [
        {'type': 'agentMessage', 'id': 'old', 'text': 'STALE-ANSWER', 'phase': 'final_answer'}]}})
record('late_old_turn_event', lambda: {'status': view.status, 'answer': view.snapshot()['answer']})

events = []
node = NodeService(Settings(auto_connect=False), data / 'service', lambda *args: events.append(args))
node.box, node.connected = box, True
old = box.create('old selection', 1)
new = box.create('new selection', 1)
for meta in (old, new):
    box.put(meta['id'], 'state.json', {'status': 'running'})
node.selected = old['id']
node.command('cancel')
node.selected = new['id']
node._drain_controls()
record('queued_cancel_after_selection_changed', lambda: {
    'old_status': box.get(old['id'], 'state.json')['status'],
    'new_status': box.get(new['id'], 'state.json')['status']})
notes = box.create('notes', 1)
node.selected = notes['id']
for ident in ('same', 'same', 'different'):
    node.command('note', note_id=ident, text='同样内容')
node._drain_controls()
record('note_id_dedup', lambda: box.get(notes['id'], 'control.json')['notes'])

class Clock:
    value = 100.
    def monotonic(self): return self.value
    def sleep(self, seconds): self.value += seconds

class ScriptedRpc(RpcClient):
    def __init__(self, clock):
        super().__init__([], data)
        self.process = SimpleNamespace(poll=lambda: None)
        self.clock, self.sent = clock, []
        self.script = [(0, 'ack'), (901, None), (1, 'done')]
    def send(self, message): self.sent.append(message)
    def poll(self, timeout=0):
        if not self.script: raise AssertionError('Fixture exhausted')
        elapsed, event = self.script.pop(0)
        self.clock.value += elapsed
        if event == 'ack':
            self.messages.put({'id': self.sent[0]['id'], 'result': {'turn': {'id': 't1'}}})
        elif event == 'done':
            self.messages.put({'method': 'turn/completed', 'params': {'threadId': 'thread1', 'turnId': 't1',
                'turn': {'id': 't1', 'status': 'completed', 'items': [
                    {'type': 'agentMessage', 'id': 'a1', 'phase': 'final_answer', 'text': '正常完成'}]}}})
        super().poll(0)

clock = Clock()
client = ScriptedRpc(clock)
def long_turn():
    with patch.object(protocol, 'time', clock), patch.object(protocol, 'stop_process_tree'):
        return client.run_turn('thread1', 'probe', 'A', '000-A',
            {'model': 'mock', 'timeout_seconds': 900}, lambda v: None, lambda: None)['status']
record('healthy_turn_over_900_seconds_virtual_clock', long_turn)
results['cases']['healthy_turn_over_900_seconds_virtual_clock']['client_methods'] = [r['method'] for r in client.sent]

from PyQt5 import QtWidgets as W
from app.ui import MainWindow
app = W.QApplication([])
window = MainWindow(Settings(auto_connect=False), data / 'gui', start_service=False)
window.snapshot = {'meta': {'id': old['id'], 'topic': '部分导出', 'rounds': 1}, 'turns': [], 'live': [
    {'step': '000-A', 'index': 0, 'role': 'A', 'status': 'running', 'answer': 'PARTIAL-UNIQUE',
     'blocks': [{'text': 'PARTIAL-UNIQUE'}], 'thread_id': 'PARTIAL-TASK-ID'}]}
exported = data / 'partial-export.txt'
with patch.object(W.QFileDialog, 'getSaveFileName', return_value=(str(exported), '')):
    window.export_report()
content = exported.read_text(encoding='utf-8-sig')
record('export_unfinished_progress', lambda: {'partial_present': 'PARTIAL-UNIQUE' in content,
    'task_id_present': 'PARTIAL-TASK-ID' in content})
record('execution_status_display', lambda: hasattr(window, 'execution_label'))
window.close()
result_path = root.parent / (__version__ + '-independent-results.json')
result_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(results, ensure_ascii=False, indent=2))
