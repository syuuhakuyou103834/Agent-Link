"""Clock/nonce boundary tests and two actual local services with mock model RPC."""
from pathlib import Path
import sys, unittest, time
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from app.liveness import PeerLiveness, FEATURE
from app.storage import read_json, atomic_json
from test_system import SystemTests, until
from test_repairs import RepairComponentTests
from app.protocol import RpcClient
from types import SimpleNamespace

class Clock:
    def __init__(self): self.t=100.
    def __call__(self): return self.t

class LivenessTests(unittest.TestCase):
    def setUp(self):
        self.clock=Clock();self.live=PeerLiveness('A','a'*32,self.clock)
        self.peer=dict(role='B',instance='b'*32,seq=1,status='idle',features=[FEATURE],updated=0)
    def ready(self):
        self.live.observe(self.peer)
        challenge=self.live.challenge();self.assertIsNotNone(challenge)
        self.peer.update(seq=self.peer['seq']+1,challenge_ack=challenge)
        self.assertIsNone(self.live.observe(self.peer));self.assertEqual(self.live.status(),'ready')
    def test_original_skew_and_wall_jumps_do_not_change_liveness(self):
        self.ready()
        for offset in (-1.098,-300,-2,0,2,300,86400,-86400):
            self.clock.t+=1;self.peer.update(seq=self.peer['seq']+1,updated=self.clock.t+offset)
            self.assertIsNone(self.live.observe(self.peer));self.assertEqual(self.live.status(),'ready')
    def test_12_30_boundaries_and_repeated_sequence_not_renewed(self):
        self.ready()
        for elapsed,expected in [(11.999,'ready'),(12,'delayed'),(29.999,'delayed'),(30,'unavailable')]:
            self.clock.t=100+elapsed;self.live.observe(self.peer)
            self.assertEqual(self.live.status(),expected)
    def test_first_record_and_wrong_or_stale_ack_cannot_authorize(self):
        self.live.observe(self.peer);c=self.live.challenge()
        self.assertEqual(self.live.status(),'probing')
        for change in ({'nonce':'c'*32},{'target_instance':'c'*32},{'origin_instance':'d'*32}):
            self.peer.update(seq=self.peer['seq']+1,challenge_ack=dict(c,**change))
            self.live.observe(self.peer);self.assertNotEqual(self.live.status(),'ready')
        self.clock.t+=12;self.peer.update(seq=9,challenge_ack=c)
        self.live.observe(self.peer);self.assertNotEqual(self.live.status(),'ready')
    def test_delayed_requires_new_challenge_and_timeout_is_latched(self):
        self.ready();old=self.peer['challenge_ack'];self.clock.t+=12
        self.peer.update(seq=3);self.live.observe(self.peer)
        self.assertEqual(self.live.status(),'delayed')
        c=self.live.challenge();self.assertNotEqual(c,old)
        self.peer.update(seq=4,challenge_ack=c);self.live.observe(self.peer)
        self.assertEqual(self.live.status(),'ready')
        self.clock.t+=30;self.peer.update(seq=5);self.live.observe(self.peer)
        self.assertEqual(self.live.status(),'unavailable');self.assertIsNone(self.live.challenge())
    def test_invalid_sequence_and_regression_do_not_refresh(self):
        self.ready()
        for seq in (True,0,-1,1.5,'4',2**63):
            self.assertEqual(self.live.observe(dict(self.peer,seq=seq)),'peer_sequence_invalid')
        self.assertEqual(self.live.observe(dict(self.peer,seq=1)),'peer_sequence_regressed')
        self.assertEqual(self.live.last_progress,100)
    def test_restart_invalidates_proof(self):
        self.ready();self.peer.update(instance='c'*32,seq=1)
        self.live.observe(self.peer);self.assertEqual(self.live.status(),'probing')
    def test_sampling_gap_reauthenticates(self):
        self.ready();self.clock.t+=13;self.peer.update(seq=15)
        self.live.observe(self.peer);self.assertEqual(self.live.status(),'delayed')
        self.assertIsNotNone(self.live.challenge())
    def test_reset_does_not_reuse_ack(self):
        self.ready();self.live.reset();self.live.observe(self.peer)
        self.assertEqual(self.live.status(),'probing');self.assertNotEqual(self.live.challenge(),self.peer['challenge_ack'])

class LocalPairTests(unittest.TestCase):
    setUp=SystemTests.setUp
    tearDown=SystemTests.tearDown
    calls=SystemTests.calls
    def test_simultaneous_start_handshake_and_original_wall_skew(self):
        until(lambda:all(n.liveness.status()=='ready' for n in self.nodes.values()),15)
        a,b=self.nodes['A'],self.nodes['B']
        peer=read_json(a.box.root/'nodes/B.json')
        for delta in (-300,300,-1.098):
            self.assertIsNone(a._peer_problem(dict(peer,updated=time.time()+delta)))
        self.assertEqual([len(self.calls(r)) for r in ('A','B')],[0,0])
        self.assertTrue(read_json(a.box.root/'nodes/A.json')['challenge_ack'])
    def test_dead_peer_with_held_lock_cannot_pass_gate(self):
        until(lambda:all(n.liveness.status()=='ready' for n in self.nodes.values()),15)
        a=self.nodes['A'];a.liveness.last_progress-=31
        with self.assertRaises(ValueError):a._check_peer_compatibility()
        self.assertEqual(len(self.calls('A')),0)

class SendGateTests(RepairComponentTests):
    def rpc(self):
        self.node.active=self.ready()
        rpc=object.__new__(RpcClient);rpc.counter=0;rpc.responses={};rpc.sensitive_requests=set()
        rpc.current=SimpleNamespace(turn_id='turn',thread_id='thread',status='running',step='001-B')
        rpc.steer_guard=self.node._steer_send_guard
        self.sent=[];rpc.send=lambda m:self.sent.append(m)
        self.node.client=rpc
        return rpc
    def test_stop_between_pending_and_pipe_write_sends_zero_and_preserves_input(self):
        rpc=self.rpc();job=self.node.active['id'];identifier='f'*32
        self.node.send_node_input(job,'B','补充',identifier)
        original=rpc.begin_steer
        def after_stop(text):
            self.node._edit_control(job,'cancel','')
            return original(text)
        rpc.begin_steer=after_stop
        self.node._pump_node_inputs()
        self.assertEqual(self.sent,[])
        self.assertEqual(self.box.get(job,'input-'+identifier+'.json')['state'],'queued')
    def test_delayed_or_paused_steer_blocked_and_send_first_recorded(self):
        rpc=self.rpc();self.node.liveness.last_progress-=13
        with self.assertRaises(ValueError):rpc.begin_steer('delayed')
        self.assertFalse(rpc.steer_send_started);self.assertFalse(self.sent)
        self.node.liveness.reset();__import__('liveness_fixture').respond(self.node)
        self.node._edit_control(self.node.active['id'],'pause','')
        with self.assertRaises(ValueError):rpc.begin_steer('paused')
        self.assertFalse(self.sent)
        self.node._edit_control(self.node.active['id'],'resume','')
        rpc.begin_steer('allowed');self.assertTrue(rpc.steer_send_started)
        self.assertEqual(len(self.sent),1)

if __name__=='__main__':
    suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(c) for c in (LivenessTests,LocalPairTests))
    suite.addTests(SendGateTests(n) for n in SendGateTests.__dict__ if n.startswith('test_'))
    sys.exit(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())
