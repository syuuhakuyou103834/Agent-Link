"""Synthetic challenge responder for component tests, never a product bypass."""
from app.liveness import FEATURE
from app.engine import SAFETY_FEATURE
from app.storage import atomic_json, read_json, FileLock

def respond(node, peer=None):
    path=node.box.root/'nodes'/(node.peer_role+'.json')
    peer=peer or read_json(path,{})
    peer=dict(peer, role=node.peer_role, instance=peer.get('instance',node.peer_role.lower()*32),
              seq=max(peer.get('seq',0),node.liveness.highest_seq)+1,
              status=peer.get('status','idle'),features=[SAFETY_FEATURE,FEATURE])
    node.liveness.observe(peer)
    challenge=node.liveness.challenge()
    if challenge:peer.update(seq=peer['seq']+1,challenge_ack=challenge)
    atomic_json(path,peer);node.liveness.observe(peer)
    return peer

def owned_peer(node, peer):
    lease=FileLock(node.box.root/'nodes'/(node.peer_role+'.lease')).acquire()
    atomic_json(node.box.root/'nodes'/(node.peer_role+'-owner.json'),dict(role=node.peer_role,instance=peer.get('instance',node.peer_role.lower()*32)))
    respond(node,peer)
    return lease
