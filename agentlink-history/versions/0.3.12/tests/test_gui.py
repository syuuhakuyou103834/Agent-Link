"""Exercise real PyQt widgets with two offline model fixtures."""
import os
import json
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
import sys
import time
import uuid
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PyQt5 import QtCore, QtGui, QtWidgets as W, QtTest
from app.storage import Settings
from app.ui import MainWindow, SettingsDialog

app = W.QApplication([])
for name in ('msyh.ttc', 'msyhbd.ttc'):
    QtGui.QFontDatabase.addApplicationFont(str(Path('C:/Windows/Fonts') / name))
app.setStyle('Fusion')
root = ROOT / 'test-output' / ('gui-' + uuid.uuid4().hex)
root.mkdir(parents=True)
windows = {}


def wait(predicate, timeout=25):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if predicate():
            return
        time.sleep(.02)
    raise AssertionError('GUI test timeout')


try:
    for role in ('A', 'B'):
        settings = Settings(role=role, shared_root=str(root / 'share'), auto_connect=True)
        command = [sys.executable, str(ROOT / 'tests' / 'mock_server.py'), role, str(root / (role + '-calls.jsonl'))]
        window = MainWindow(settings, root / role, command_override=command)
        window.show(); windows[role] = window
    wait(lambda: all(w.connected and w.peer.get('online') for w in windows.values()))
    b = windows['B']
    b.prompt.setPlainText('GUI-ORIGIN 测试 PyQt5 界面：两台均可发起，中文完整呈现。')
    b.rounds.setValue(2)
    QtTest.QTest.mouseClick(b.start_button, QtCore.Qt.LeftButton)
    wait(lambda: all(w.snapshot.get('status') == 'completed' for w in windows.values()))
    wait(lambda: all(not w.active_id for w in windows.values()))
    for role, window in windows.items():
        assert '中文传递正确' in window.panes['A'].toPlainText()
        assert '中文传递正确' in window.panes['B'].toPlainText()
        assert 'B 节点模拟回答' in window.final_view.toPlainText()
        assert '公开摘要' in window.summary_view.toPlainText()
        assert '模拟校验通过' in window.tools_view.toPlainText()
        assert window.history_list.count() == 1
        window.copy_final()
        assert W.QApplication.clipboard().text() == window.final_text()
    original_id = b.snapshot['meta']['id']
    a = windows['A']
    wait(lambda: a.start_button.isEnabled())
    assert a.start_button.text() == '继续讨论'
    assert '将继续所选讨论' in a.context_hint.text()
    a.prompt.setPlainText('GUI-CONTINUE 按上一轮结论开始测试')
    QtTest.QTest.mouseClick(a.start_button, QtCore.Qt.LeftButton)
    wait(lambda: a.snapshot['meta'].get('id') != original_id)
    wait(lambda: all(w.snapshot.get('status') == 'completed' and not w.active_id for w in windows.values()))
    for role, window in windows.items():
        assert window.snapshot['meta']['context']['parent_job_id'] == original_id
        assert 'GUI-ORIGIN' in window.context_view.toPlainText()
        calls = [json.loads(line) for line in (root / (role + '-calls.jsonl')).read_text(encoding='utf-8').splitlines()]
        assert 'GUI-ORIGIN' in calls[-1]['prompt']
        assert 'GUI-CONTINUE' in calls[-1]['prompt']
    old_snapshot = a.snapshot
    a.new_discussion()
    assert not a.snapshot['meta'] and a.start_button.text() == '发起讨论'
    assert '不携带其他记录' in a.context_hint.text()
    a.receive('discussion', old_snapshot)
    assert not a.snapshot['meta'], 'Late history UI events must not reattach an old discussion'
    wait(lambda: a.history_list.count() == 2)
    item = next(a.history_list.item(i) for i in range(a.history_list.count())
                if a.history_list.item(i).data(QtCore.Qt.UserRole) == original_id)
    a.select_history(item)
    assert not a.start_button.isEnabled(), 'Wait for the selected history to load'
    wait(lambda: a.snapshot.get('meta', {}).get('id') == original_id)
    assert a.start_button.text() == '继续讨论'
    dialog = SettingsDialog(b.settings)
    assert dialog.result_settings().sandbox == 'read-only'
    b.receive('storage_warning', {'message': 'TEST: temporary file access issue'})
    assert b.notice.isVisible() and not b.start_button.isEnabled()
    b.receive('storage_recovered', {})
    assert not b.notice.isVisible()
    b.receive('error', {'message': 'TEST: unrelated model failure'})
    b.receive('storage_recovered', {})
    assert b.notice.isVisible(), 'Recovery must not hide a model failure'
    b.notice.hide()
    b.grab().save(str(ROOT / 'gui-tested.png'))
    b.tabs.setCurrentIndex(1); app.processEvents()
    b.grab().save(str(ROOT / 'gui-final-tested.png'))
    (root / 'result.txt').write_text('PASS: B initiates 2 rounds; A continues with shared history; context tab; new discussion detaches history; stale selection blocked; UI panes, final answer, summary, tools, copy, permissions.\n', encoding='utf-8')
    print((root / 'result.txt').read_text())
finally:
    for window in windows.values():
        window.close()
    wait(lambda: all(not w.service.thread.is_alive() for w in windows.values()), 20)
    for window in windows.values():
        window.close()
