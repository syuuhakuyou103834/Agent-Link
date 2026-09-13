"""I/O grace and isolated test guard boundaries; no real shares or model calls."""
from pathlib import Path
import os,sys,time,unittest
from unittest.mock import patch
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from test_repairs import RepairComponentTests
from app.interruption import TechnicalInterruption
from offline_test_guard import guard

class GraceTests(RepairComponentTests):
    def test_single_io_failure_keeps_current_request_and_30_seconds_interrupts(self):
        self.node.active=self.ready();self.node.last_tick=0
        with patch.object(self.node,'_heartbeat',side_effect=OSError('injected shared read failure')):
            self.node._pump()
            self.assertIsNotNone(self.node.share_lost)
            self.assertEqual(self.client.calls,[])
            self.assertNotEqual(self.box.get(self.node.active['id'],'state.json')['status'],'failed')
            self.node.io_failures['heartbeat']=self.node.liveness.clock()-31;self.node.last_tick=0
            with self.assertRaises(TechnicalInterruption) as error:self.node._pump()
            self.assertEqual(error.exception.details['code'],'shared_io_unavailable')
    def test_identity_loss_does_not_receive_grace(self):
        self.node.active=self.ready();self.peer_locks[0].close()
        with self.assertRaises(TechnicalInterruption):self.node._control()
        self.assertEqual(self.client.calls,[])

class GuardTests(unittest.TestCase):
    def test_only_explicit_project_test_source_and_output_are_allowed(self):
        base=r'C:\synthetic-local\AgentLinkGUI'
        source=base+r'\project-tests\case\source';output=base+r'\project-tests\case\out'
        with patch.dict(os.environ,LOCALAPPDATA=r'C:\synthetic-local',AGENTLINK_TEST_SOURCE_ROOT=source,AGENTLINK_TEST_WRITE_ROOT=output):
            guard('open',(source+r'\tests\test_storage.py','r',0))
            guard('open',(output+r'\result.json','w',os.O_WRONLY))
            for path,mode,flags in [(base+r'\settings.json','r',0),(base+r'\runs\state.json','w',os.O_WRONLY),
                (base+r'\project-tests\another\result.json','r',0),(source+r'\app\engine.py','w',os.O_WRONLY),
                (r'\\server\share\file','r',0)]:
                with self.subTest(path=path),self.assertRaises(PermissionError):guard('open',(path,mode,flags))

if __name__=='__main__':
    suite=unittest.TestSuite(GraceTests(n) for n in GraceTests.__dict__ if n.startswith('test_'))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(GuardTests))
    sys.exit(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())
