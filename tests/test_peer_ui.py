from fixture_paths import fs, entries
"""Offline Qt rendering of recoverable peer failures; explicit local share only."""
import os,sys,unittest,uuid
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen'
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PyQt5 import QtWidgets as W, QtGui
from app.ui_conversation import MainWindow
from app.storage import Settings
from app.conversation import append_message

class PeerUi(unittest.TestCase):
    def test_unsent_B_recovery_and_clock_diagnostic(self):
        app=W.QApplication.instance() or W.QApplication([])
        for name in ('msyh.ttc','msyhbd.ttc'):
            QtGui.QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+name)
        root=__import__('fixture_paths').output_root()/('ui019-'+uuid.uuid4().hex);fs(root).mkdir(parents=True)
        w=MainWindow(Settings(shared_root=str(root/'share'),auto_connect=False),root,start_service=False)
        try:
            c=w.service.conversations.create('A 初审已保存；从 B 的源码接收继续')
            append_message(c,'A','初审完成，源码快照及测试记录已保存。','formal')
            c.update(phase='interrupted',job='test-job',jobs=['test-job'],error='节点 B 暂停执行：节点 A 心跳时间差 13 秒',
                interruption=dict(origin='B',peer='A',stage='receiving_snapshot',request_state='not_sent',
                                  code='peer_heartbeat_stale',heartbeat_age_seconds=13,resume_policy='explicit_only'))
            w.conversation=c;w.connected=True;w.render();w.show();app.processEvents();w.toggle_details();app.processEvents()
            self.assertIn('尚未发送模型请求',w.context_hint.text())
            self.assertNotIn('额度',w.context_hint.text())
            self.assertIn('receiving_snapshot',w.project_view.toPlainText())
            self.assertIn('中断',w.state_label.text());self.assertTrue(w.start_button.isEnabled())
            w.receive('peer',{'online':False,'online_problem':{'reason':'节点 B 时钟领先 2 秒'},'capabilities':{}})
            self.assertIn('领先 2 秒',w.peer_badge.toolTip())
            self.assertTrue(w.grab().save(str(root/'peer-recovery.png')))
            print(root)
        finally:w.hide();w.deleteLater();app.processEvents()

if __name__=='__main__':unittest.main(verbosity=2)
