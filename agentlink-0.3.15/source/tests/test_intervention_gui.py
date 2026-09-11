import os,sys
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen'
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
from PyQt5 import QtWidgets as W, QtGui
from app.ui import MainWindow
from app.storage import Settings
app=W.QApplication([])
for font in ('msyh.ttc','msyhbd.ttc'):QtGui.QFontDatabase.addApplicationFont(str(Path('C:/Windows/Fonts')/font))
app.setStyle('Fusion')
w=MainWindow(Settings(auto_connect=False),root/'test-output'/'intervention-gui',start_service=False)
w.resize(1300,900);w.show();w.connected=True
job='20260911-000000-'+'a'*32
w.snapshot={'meta':{'id':job,'mode':'code','topic':'测试','rounds':1,'project':{'id':'b'*32}},'status':'failed','turns':[]}
w.active_id=None;w.update_buttons()
assert w.node_recover.isEnabled() and not w.node_send.isEnabled()
calls=[];w.service.command=lambda kind,**kw:calls.append((kind,kw))
w.node_target.setCurrentText('B');w.node_message.setPlainText('额度已恢复，继续核查')
w.recover_node();assert calls[-1][1]['recovery']=={'parent_id':job,'target':'B','text':'额度已恢复，继续核查'}
w.active_id=job;w.snapshot['status']='running';w.update_buttons()
assert w.node_send.isEnabled() and not w.node_recover.isEnabled()
w.send_node_message();assert calls[-1][0]=='node_input' and calls[-1][1]['target']=='B'
w.tabs.setCurrentIndex(w.tabs.count()-1);app.processEvents()
assert w.grab().save(str(root.parent/'evidence'/'node-chat.png'))
w.close();print('PASS node input and recovery UI controls, command binding and rendering')
