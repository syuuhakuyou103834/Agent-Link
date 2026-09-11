import os,sys
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='windows'
sys.path.insert(0,r'C:\AgentLink-GUI\dist\AgentLink-GUI-0.3.15')
from PyQt5 import QtWidgets as W,QtGui
from app.ui import MainWindow
from app.storage import Settings
from app import __version__
assert __version__=='0.3.15'
app=W.QApplication([])
for name in ('msyh.ttc','msyhbd.ttc'):QtGui.QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+name)
w=MainWindow(Settings(auto_connect=False),Path(r'C:\AgentLink-intervention-0.3.15\evidence\package-ui'),start_service=False)
w.resize(1300,900);w.move(-32000,-32000);w.show();w.tabs.setCurrentIndex(w.tabs.count()-1);app.processEvents()
assert w.tabs.tabText(w.tabs.count()-1)=='节点对话与恢复'
assert w.grab().save(r'C:\AgentLink-intervention-0.3.15\evidence\packaged-ui.png')
w.close();print('PASS packaged native Qt node intervention UI 0.3.15')
