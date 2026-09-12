"""Offline history rendering on real Qt widgets; no model or network."""
import os,sys,uuid
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen'
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PyQt5 import QtWidgets as W
from app.ui import MainWindow
from app.storage import Settings, atomic_json
app=W.QApplication([])
root=__import__('fixture_paths').output_root()/('offline-gui-'+uuid.uuid4().hex)
w=MainWindow(Settings(auto_connect=False),root,start_service=False)
try:
    job='20260911-000000-'+'a'*32
    cache=root/'runs'/job
    atomic_json(cache/'meta.json',{'id':job,'mode':'code','topic':'离线项目','rounds':1,'project':{'id':'b'*32,'name':'离线项目'}})
    atomic_json(cache/'state.json',{'status':'failed'})
    w.service.selected=job
    events=[];w.service.emit=lambda k,v:events.append((k,v))
    w.service._sync_selected()
    w.snapshot=events[-1][1];w.render()
    assert '尚未缓存问题清单' in w.project_view.toPlainText()
    atomic_json(cache/'project-issues.json',{'issues':[{'id':'c','status':'open','description':'缓存问题'}]})
    w.service._sync_selected();w.snapshot=events[-1][1];w.render()
    assert '缓存问题' in w.project_view.toPlainText()
    assert '离线缓存' in w.project_view.toPlainText()
    w.resize(1300,900);w.show();app.processEvents()
    assert w.grab().save(str(root/'offline-history.png'))
    print('PASS: offline project history, missing-cache notice and cached issues rendered')
finally:w.close()
