"""Recovery controls and shared issue reads stay off the Qt event thread."""
import os,sys,unittest,uuid
from pathlib import Path
from unittest.mock import patch
os.environ['QT_QPA_PLATFORM']='offscreen'
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from PyQt5.QtWidgets import QApplication
from app.ui_conversation import MainWindow
from app.storage import Settings
from fixture_paths import output_root

class UiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.window=MainWindow(Settings(auto_connect=False),output_root()/('ui022-'+uuid.uuid4().hex[:8]),start_service=False)
        self.addCleanup(self.window.close)
        self.window.connected=True
        self.window.conversation=dict(id='conversation-'+'a'*32,phase='interrupted',jobs=['job'],job='job',
                                      job_meta={'project':{'id':'a'*32}},messages=[],topic='test',completed_rounds=0)
    def test_issue_command_performs_no_shared_read_on_gui_thread(self):
        with patch('app.ui_conversation.read_json',side_effect=PermissionError('injected shared denial')) as read, \
             patch.object(self.window.service,'command') as command:
            self.window.change_issue_status()
            read.assert_not_called();command.assert_called_once_with('issue_catalog',project='a'*32)
        self.assertTrue(self.window.issues_pending)
        self.window.receive('error',{'message':'shared read failed'})
        self.assertFalse(self.window.issues_pending)
    def test_explicit_resume_button_and_stopped_task(self):
        self.window.update_buttons();self.assertFalse(self.window.resume_button.isHidden())
        self.assertTrue(self.window.resume_button.isEnabled())
        with patch.object(self.window.service,'command') as command:
            self.window.resume_button.click()
            command.assert_called_once_with('conversation_control',conversation_id='conversation-'+'a'*32,action='resume')
        self.window.conversation.update(phase='cancelled',user_stopped=True)
        self.window.update_buttons();self.assertTrue(self.window.resume_button.isHidden())
        self.assertFalse(self.window.resume_button.isEnabled())
    def test_cleanup_pending_disables_resume_but_disconnect_stays_available(self):
        self.window.service.cleanup_error='injected cleanup failure';self.window.update_buttons()
        self.assertFalse(self.window.resume_button.isEnabled())
        self.assertTrue(self.window.connect_button.isEnabled())

if __name__=='__main__':unittest.main(verbosity=2)
