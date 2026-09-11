import os,sys
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='windows'
root=Path(r'C:\AgentLink-GUI\dist\AgentLink-GUI-0.3.13')
sys.path.insert(0,str(root))
from PyQt5 import QtWidgets as W
from app import __version__
from app.ui import MainWindow
from app.storage import Settings
assert __version__=='0.3.13'
app=W.QApplication([])
w=MainWindow(Settings(auto_connect=False),Path(r'C:\AgentLink-hotfix-0.3.13\evidence\packaged-smoke-data'),start_service=False)
w.move(-32000,-32000); w.show(); app.processEvents()
assert app.platformName()=='windows'
assert w.grab().save(r'C:\AgentLink-hotfix-0.3.13\evidence\packaged-main.png')
w.close()
print('PASS packaged 0.3.13 native Windows Qt main window, service disabled')
