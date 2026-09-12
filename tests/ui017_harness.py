"""Qt integration through actual clicks: single input, consent, timeline, B followup."""
import os,json,sys,time,uuid
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen'
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PyQt5 import QtCore,QtGui,QtWidgets as W,QtTest
from app.ui import MainWindow,SettingsDialog
from app.conversation import ID
from app.storage import Settings

def run(code=False):
    app=W.QApplication.instance() or W.QApplication([])
    for name in ('msyh.ttc','msyhbd.ttc'):QtGui.QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+name)
    root=__import__('fixture_paths').output_root()/('ui017-'+uuid.uuid4().hex);root.mkdir(parents=True)
    windows={}
    def wait(predicate,timeout=50):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            app.processEvents()
            if predicate():return
            time.sleep(.03)
        raise AssertionError('GUI timeout; '+str([(r,(w.conversation or {}).get('phase')) for r,w in windows.items()]))
    def send(w,text):
        w.prompt.setPlainText(text);QtTest.QTest.mouseClick(w.start_button,QtCore.Qt.LeftButton)
    try:
        for role in ('A','B'):
            cfg=Settings(role=role,shared_root=str(root/'share'),auto_connect=True)
            w=MainWindow(cfg,root/role,command_override=[sys.executable,str(ROOT/'tests/mock_server.py'),role,str(root/(role+'-calls.jsonl'))])
            windows[role]=w;w.show()
        a,b=windows['A'],windows['B']
        wait(lambda:a.connected and b.connected)
        assert not b.new_button.isEnabled() and not b.start_button.isEnabled()
        assert not hasattr(a,'mode') and not hasattr(a,'project_select') and not hasattr(a,'rounds')
        assert not hasattr(a,'node_message')
        if code:
            project=root/'source-project';project.mkdir();(project/'main.py').write_text('print(1)')
            topic='只读审查这个目录\n'+str(project)
        else:topic='讨论中文 Unicode 问题'
        send(a,topic)
        wait(lambda:a.conversation and a.conversation['phase']=='awaiting_confirmation')
        cid=a.conversation['id'];assert ID.fullmatch(cid)
        assert '回复“开始”' in a.timeline.toPlainText()
        assert a.conversation['completed_rounds']==0
        send(a,'开始')
        wait(lambda:a.conversation['phase']=='completed')
        wait(lambda:any(b.history_list.item(i).data(QtCore.Qt.UserRole)==cid for i in range(b.history_list.count())))
        item=next(b.history_list.item(i) for i in range(b.history_list.count()) if b.history_list.item(i).data(QtCore.Qt.UserRole)==cid)
        b.select_history(item);assert not b.start_button.isEnabled()
        wait(lambda:b.conversation and b.conversation['id']==cid and b.conversation['phase']=='completed' and b.start_button.isEnabled())
        a.service.history();app.processEvents()
        assert a.history_list.count()==1, 'Internal execution job must not duplicate the conversation'
        assert '对话轮数 1 / 3' in a.state_label.text()
        assert 'A 协作成果' in a.timeline.toPlainText() and 'B 协作成果' in a.timeline.toPlainText()
        assert '模拟校验通过' in a.tools_view.toPlainText()
        assert '公开摘要' in a.summary_view.toPlainText()
        a.copy_final();assert W.QApplication.clipboard().text()==a.final_text()
        assert not a.tabs.isVisible();a.toggle_details();assert a.tabs.isVisible()
        assert '澄清/补充请求尝试' in a.project_view.toPlainText()
        if code:assert '源码快照' in a.project_view.toPlainText()
        (root/'export.md').write_text(a.report(),encoding='utf-8');assert topic in (root/'export.md').read_text(encoding='utf-8')
        calls_before=len((root/'A-calls.jsonl').read_text(encoding='utf-8').splitlines())
        send(b,'[RELAY] 记录后续建议')
        wait(lambda:any(m['kind']=='relay' for m in b.conversation['messages']))
        assert b.conversation['completed_rounds']==1
        assert len((root/'A-calls.jsonl').read_text(encoding='utf-8').splitlines())==calls_before
        dialog=SettingsDialog(a.settings);assert dialog.result_settings().sandbox=='read-only';dialog.close()
        b.receive('storage_warning',{'message':'file unavailable'});assert not b.start_button.isEnabled()
        b.receive('storage_recovered',{});assert not b.notice.isVisible()
        b.receive('error',{'message':'model error'});b.receive('storage_recovered',{});assert b.notice.isVisible()
        a.grab().save(str(root/'conversation.png'))
        old=a.conversation;a.new_discussion();a.receive('conversation',old);assert a.conversation is None
        (root/'result.txt').write_text('PASS: '+('code snapshot' if code else 'text')+' Qt single timeline, explicit start, A-only, B followup, counts, details, export, errors, stale selection\n')
        print(root)
    finally:
        for w in windows.values():w.close()
        wait(lambda:all(not w.service.thread.is_alive() for w in windows.values()),25)
        for w in windows.values():w.close()
