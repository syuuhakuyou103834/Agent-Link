"""Actual Qt widgets: create/bind a project, start code review, inspect/export its result."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
import sys
import time
import uuid
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PyQt5 import QtCore, QtGui, QtWidgets as W, QtTest
from app.ui import MainWindow, ProjectDialog
from app.storage import Settings, read_json
from app.projects import Projects

app = W.QApplication([])
for name in ('msyh.ttc','msyhbd.ttc'):
    QtGui.QFontDatabase.addApplicationFont('C:/Windows/Fonts/' + name)
root = ROOT/'test-output'/('code-gui-'+uuid.uuid4().hex); root.mkdir(parents=True)
source = root/'project'; source.mkdir(); (source/'app.py').write_text('print("GUI 中文")',encoding='utf-8')
windows=[]
def wait(predicate):
    end=time.monotonic()+50
    while time.monotonic()<end:
        app.processEvents()
        if predicate(): return
        time.sleep(.02)
    raise AssertionError('Code GUI timeout')
try:
    for role in ('A','B'):
        cfg=Settings(role=role,shared_root=str(root/'share'),auto_connect=True)
        w=MainWindow(cfg,root/role,command_override=[sys.executable,str(ROOT/'tests'/'mock_server.py'),role,str(root/(role+'-calls.jsonl'))])
        w.show();windows.append(w)
    a,b=windows
    wait(lambda:all(w.connected and w.peer.get('online') for w in windows))
    dialog=ProjectDialog(a.data,a.settings)
    dialog.name.setText('代码审查 GUI 测试');dialog.directory.setText(str(source));dialog.accept()
    assert dialog.result()==W.QDialog.Accepted
    a.mode.setCurrentIndex(a.mode.findData('code'));a.refresh_projects();a.project_select.setCurrentIndex(1)
    assert a.rounds.value()==3 and '7' in a.call_count.text()
    a.prompt.setPlainText('审查项目 [SIDE_ISSUE]')
    QtTest.QTest.mouseClick(a.start_button,QtCore.Qt.LeftButton)
    wait(lambda:all(w.snapshot.get('status')=='completed' and not w.active_id for w in windows))
    assert a.snapshot['state']['outcome']=='passed'
    assert '审查通过' in a.state_label.text()
    assert 'A 只读总结' in a.panes['A'].toPlainText()
    assert 'B 独立审查' in b.panes['B'].toPlainText()
    assert '另一个范围外问题' in a.project_view.toPlainText()
    assert a.snapshot['local_scope']['phase']=='summary'
    assert b.snapshot['local_scope']['phase']=='review'
    assert not a.mode.isEnabled()
    a.grab().save(str(root/'project-review.png'))
    a.copy_final();assert '审查通过' in W.QApplication.clipboard().text()
    assert Path(a.snapshot['report_path']).exists()
    for w in windows:
        delivery = w.snapshot['turns'][0]['delivery']
        assert (w.data/'runs'/w.snapshot['meta']['id']/delivery['complete_manifest']).is_file()
    print('PASS code GUI project binding, 3-call early pass, source scope, issues, copy/export; screenshot:',root/'project-review.png')
finally:
    for w in windows:w.service.stop()
    for w in windows:w.service.thread.join(15);w.close()
