"""Clock-independent, instance-bound peer freshness. No filesystem or RPC calls."""
import re
import time
import uuid
import os

# Win32 uptime includes suspend/hibernate, unlike some timeout clocks.
# https://learn.microsoft.com/en-us/windows/win32/sysinfo/windows-time
if os.name == 'nt':
    import ctypes
    _ticks = ctypes.WinDLL('kernel32', use_last_error=True).GetTickCount64
    _ticks.argtypes = []
    _ticks.restype = ctypes.c_ulonglong
    def elapsed_time(): return _ticks() / 1000.0
else:
    elapsed_time = time.monotonic

FEATURE = 'peer-liveness-challenge-v1'
FRESH = 12.0
DEAD = 30.0
TOKEN = re.compile(r'[a-f0-9]{32}')

def token(value):
    return isinstance(value, str) and TOKEN.fullmatch(value) is not None

def valid_challenge(value, origin, target, origin_instance=None, target_instance=None):
    return (isinstance(value, dict) and value.get('schema') == FEATURE
        and value.get('origin') == origin and value.get('target') == target
        and token(value.get('nonce')) and token(value.get('origin_instance'))
        and token(value.get('target_instance'))
        and (origin_instance is None or value['origin_instance'] == origin_instance)
        and (target_instance is None or value['target_instance'] == target_instance))

class PeerLiveness:
    def __init__(self, role, instance, clock=None):
        self.role, self.instance = role, instance
        self.peer_role = 'B' if role == 'A' else 'A'
        self.clock = clock or elapsed_time
        self.reset()

    def reset(self):
        self.peer_instance = None
        self.highest_seq = 0
        self.verified = False
        self.pending = None
        self.pending_at = None
        self.floor = 0
        self.last_progress = None
        self.started = self.clock()
        self.last_sample = self.started
        self.expired = False

    def age(self):
        return max(0., self.clock() - (self.last_progress if self.last_progress is not None else self.started))

    def status(self):
        if self.expired or self.age() >= DEAD:
            return 'unavailable'
        if self.verified and self.age() < FRESH:
            return 'ready'
        return 'delayed' if self.last_progress is not None else 'probing'

    def observe(self, peer):
        stamp = self.clock()
        # A long local sampling gap cannot silently inherit old authority.
        if stamp - self.last_sample >= FRESH:
            self.verified = False
            self.pending = None
        self.last_sample = stamp
        if not isinstance(peer, dict) or peer.get('role') != self.peer_role:
            return 'peer_role_invalid'
        identity, seq = peer.get('instance'), peer.get('seq')
        if not token(identity): return 'peer_instance_invalid'
        if peer.get('status') == 'offline': return 'peer_offline'
        if not isinstance(peer.get('features'), list) or FEATURE not in peer['features']: return 'peer_protocol_incompatible'
        if type(seq) is not int or not 0 < seq <= 2**63-1: return 'peer_sequence_invalid'
        if self.peer_instance != identity:
            self.reset()
            self.peer_instance = identity
        if self.age() >= DEAD:
            self.expired = True
        if self.age() >= FRESH:
            self.verified = False
        if seq < self.highest_seq:
            return 'peer_sequence_regressed'
        progressed = seq > self.highest_seq
        self.highest_seq = max(seq, self.highest_seq)
        ack = peer.get('challenge_ack')
        if (progressed and not self.expired and self.pending is not None and ack == self.pending
                and stamp - self.pending_at < FRESH and seq > self.floor):
            self.verified = True
            self.last_progress = stamp
            self.pending = None
        elif progressed and self.verified:
            self.last_progress = stamp
        return None

    def challenge(self):
        if self.peer_instance is None or self.status() == 'ready' or self.expired:
            return None
        stamp = self.clock()
        if self.pending is None or stamp - self.pending_at >= FRESH:
            self.pending = dict(schema=FEATURE, origin=self.role, target=self.peer_role,
                origin_instance=self.instance, target_instance=self.peer_instance, nonce=uuid.uuid4().hex)
            self.pending_at, self.floor = stamp, self.highest_seq
        return dict(self.pending)

    def details(self):
        return dict(liveness_state=self.status(), local_silence_seconds=round(self.age(), 3),
            peer_sequence=self.highest_seq, challenge_nonce=(self.pending or {}).get('nonce'),
            freshness_basis='local_monotonic_sequence_and_challenge')
