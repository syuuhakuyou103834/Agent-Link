"""Render budget diagnostics and full transcript without a service or model."""
import os,sys,unittest,uuid
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen'
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PyQt5 import QtWidgets as W, QtGui
from app.ui_conversation import MainWindow
from app.storage import Settings
from app.conversation import append_message
from app.context import PromptBudgetError

class ContextUiTests(unittest.TestCase):
    def test_context_details_and_original_export(self):
        app=W.QApplication.instance() or W.QApplication([])
        for name in ('msyh.ttc','msyhbd.ttc'):
            QtGui.QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+name)
        root=ROOT/'test-output'/('ui018-'+uuid.uuid4().hex);root.mkdir(parents=True)
        window=MainWindow(Settings(shared_root=str(root/'share'),auto_connect=False),root,start_service=False)
        try:
            value=window.service.conversations.create('长对话保持原文')
            append_message(value,'B','完整审查意见 END','formal')
            error=PromptBudgetError('X'*280001,'节点 A 正式总结')
            value.update(phase='context_blocked',error=str(error),context_error=error.details,
                context_view=dict(prompt_chars=280001,archived_sequences=[2],index='本机证据目录/index.json'))
            window.conversation=value;window.connected=True;window.render();window.show();app.processEvents()
            window.toggle_details();app.processEvents()
            self.assertIn('上下文待处理，未发送',window.state_label.text())
            self.assertIn('280,001',window.notice.text());self.assertIn('JSON 字节',window.notice.text())
            self.assertIn('prompt_chars',window.project_view.toPlainText());self.assertIn('index.json',window.project_view.toPlainText())
            self.assertIn('完整审查意见 END',window.report());self.assertTrue(window.stop_button.isEnabled())
            self.assertTrue(window.start_button.isEnabled());self.assertIn('继续',window.context_hint.text())
            self.assertTrue(window.grab().save(str(root/'context-blocked.png')))
            print(root)
        finally:window.hide();window.deleteLater();app.processEvents()

if __name__=='__main__':unittest.main(verbosity=2)
