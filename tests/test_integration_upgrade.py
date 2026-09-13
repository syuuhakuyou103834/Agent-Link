"""Cross-version migration and restored UI behavior with preserved safety gates."""
import json
from pathlib import Path
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tests')]
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PyQt5 import QtWidgets as W
from app.storage import Settings, Mailbox, atomic_json, read_json
from app.context import prepare_context
from app.ui import MainWindow, SettingsDialog
from app.protocol import RpcClient, TurnView
from app.engine import NodeService
from app.protocol import Cancelled
import test_system
from test_system import until

class UpgradeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = W.QApplication.instance() or W.QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='agentlink-upgrade-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_actual_034_settings_and_039_legacy_values_migrate(self):
        legacy = json.loads((ROOT/'tests/fixtures/034-settings.json').read_text(encoding='utf-8'))
        self.assertEqual(legacy['timeout_seconds'], 0)
        for timeout in (legacy['timeout_seconds'], 900, 3600):
            with self.subTest(timeout=timeout):
                old = dict(legacy, timeout_seconds=timeout, role='B', workspace='preserve-workspace',
                           sandbox='workspace-write', tools='discussion', model='preserve-model')
                atomic_json(self.root/'settings.json', old)
                loaded = Settings.load(self.root)
                self.assertEqual(loaded.timeout_seconds, 0)
                loaded.save(self.root)
                actual = read_json(self.root/'settings.json')
                self.assertEqual(actual, dict(old, timeout_seconds=0))
                dialog = SettingsDialog(loaded)
                self.assertFalse(hasattr(dialog, 'timeout'))
                dialog.close()

    def test_protocol2_and_protocol1_history_continue_without_mutation(self):
        fixture = json.loads((ROOT/'tests/fixtures/034-history.json').read_text(encoding='utf-8'))
        for protocol in (1,2):
            with self.subTest(protocol=protocol):
                box = Mailbox(self.root/str(protocol)/'share', self.root/str(protocol)/'local')
                box.connect()
                meta = dict(fixture['meta'], protocol=protocol)
                if protocol == 1:
                    meta['expires'] = 1  # completed historical jobs remain usable after expiry
                    meta.pop('wait_policy')
                job_id = meta['id']
                box.job(job_id).mkdir()
                for name, data in [('meta',meta), ('control',fixture['control']), ('state',fixture['state'])]:
                    box.put(job_id, name+'.json', data)
                for turn in fixture['turns']:
                    box.put(job_id, 'turn-'+turn['step']+'.json', turn)
                before = (box.job(job_id)/'meta.json').read_bytes()
                context = prepare_context(box,job_id)
                self.assertEqual(context['discussions'][0]['turns'][-1]['answer'], 'LEGACY-034-ANSWER-2')
                self.assertEqual(context['discussions'][0]['notes'], ['LEGACY-NOTE'])
                self.assertEqual((box.job(job_id)/'meta.json').read_bytes(), before)

    def test_unfinished_export_and_status_label_restored(self):
        window = MainWindow(Settings(auto_connect=False),self.root/'gui',start_service=False)
        self.addCleanup(window.close)
        job_id = '20260911-000000-'+'a'*32
        window.snapshot = {'meta':{'id':job_id,'topic':'部分输出','rounds':1},'turns':[],
            'live':[{'step':'000-A','index':0,'role':'A','status':'running','thread_id':'TASK-PARTIAL',
                     'answer':'PARTIAL-ANSWER','blocks':[{'text':'PARTIAL-ANSWER'}]}]}
        target=self.root/'export.txt'
        with patch.object(W.QFileDialog,'getSaveFileName',return_value=(str(target),'')):
            window.export_report()
        text=target.read_text(encoding='utf-8-sig')
        self.assertIn('未完成输出',text)
        self.assertIn('PARTIAL-ANSWER',text)
        self.assertIn('TASK-PARTIAL',text)
        window.execution={'A':{'job_id':job_id,'execution':{'phase':'tool_running',
                           'elapsed_seconds':172800,'event_age_seconds':70}}}
        window.render_execution()
        self.assertIn('工具执行中',window.execution_label.text())

    def test_stale_turn_cannot_reset_activity_silence(self):
        client=RpcClient([],self.root)
        client.current=TurnView('A','002-A','same-thread')
        client.current.turn_id='new'
        client.turn_started_at=client.last_turn_event_at=100
        with patch('app.protocol.time.monotonic',return_value=200):
            client._feed_current('item/agentMessage/delta',{'threadId':'same-thread','turnId':'old',
                                                         'itemId':'old','delta':'STALE'})
            self.assertEqual(client.last_turn_event_at,100)
            self.assertEqual(client.turn_event_count,0)
            self.assertEqual(client.activity_snapshot()['event_age_seconds'],100)

    def test_terminal_previous_heartbeat_allowed_but_other_running_job_rejected(self):
        box=Mailbox(self.root/'share',self.root/'local'); box.connect()
        old=box.create('old completed',1)
        new=box.create('new active',1)
        box.put(old['id'],'state.json',{'status':'completed'})
        node=NodeService(Settings(role='A'),self.root/'node',lambda *args:None)
        node.box=box
        atomic_json(box.root/'nodes/B.json',{'job_id':old['id'],'updated':__import__('time').time(),
                                            'instance':'b'*32,'status':'waiting_peer'})
        lease=__import__('liveness_fixture').owned_peer(node,read_json(box.root/'nodes/B.json'))
        self.addCleanup(lease.close)
        node._check_peer_wait(new['id'],'B')
        box.put(old['id'],'state.json',{'status':'running'})
        with self.assertRaises(Cancelled):
            node._check_peer_wait(new['id'],'B')

class UpgradeServiceTests(unittest.TestCase):
    setUp=test_system.SystemTests.setUp
    tearDown=test_system.SystemTests.tearDown
    calls=test_system.SystemTests.calls
    job=test_system.SystemTests.job
    state=test_system.SystemTests.state

    def test_039_capability_is_rejected_before_job_creation(self):
        peer=self.nodes['B']
        original=peer._heartbeat
        peer._heartbeat=lambda *a,**k: None
        peer.stop(); peer.thread.join(15)
        atomic_json(self.shared/'nodes/B.json',{'role':'B','features':['agentlink-execution-lease-v3'],
                                             'updated':__import__('time').time(),'status':'idle'})
        self.nodes['A'].command('start',topic='reject old peer',rounds=1)
        until(lambda: any(k=='error' and '0.3.22' in v['message'] for k,v in self.events['A']))
        self.assertEqual(len(list((self.shared/'jobs').iterdir())),0)
        self.assertEqual(self.calls('A')+self.calls('B'),[])

if __name__=='__main__':
    unittest.main(verbosity=2)
