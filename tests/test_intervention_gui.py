import os,sys,uuid
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen'
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PyQt5 import QtWidgets as W
from app.ui import MainWindow
from app.storage import Settings
app=W.QApplication([])
w=MainWindow(Settings(role='B',auto_connect=False),ROOT/'test-output'/('routing-'+uuid.uuid4().hex),start_service=False)
calls=[];w.service.command=lambda kind,**kw:calls.append((kind,kw))
w.connected=True;w.conversation=dict(id='conversation-'+'a'*32,phase='interrupted',jobs=['job'],job='job')
w.update_buttons();assert w.start_button.isEnabled() and not w.new_button.isEnabled()
w.prompt.setPlainText('继续');w.start_discussion()
assert calls[-1][0]=='chat' and calls[-1][1]['text']=='继续' and 'target' not in calls[-1][1]
assert not hasattr(w,'node_message') and not hasattr(w,'node_target')
w.close();print('PASS: one local input, B recovery routed through existing conversation')
