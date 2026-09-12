"""Build a recovery plan from a COPY of incident evidence; never starts a node/model."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.engine import NodeService
from app.storage import Settings,Mailbox,atomic_json
from app.node_input import FEATURE

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    parser=argparse.ArgumentParser();parser.add_argument('frozen');parser.add_argument('output');args=parser.parse_args()
    original=Path(args.frozen).resolve();out=Path(args.output).resolve()
    assert not out.exists() and not out.is_relative_to(original)
    before={str(p.relative_to(original)):digest(p) for p in original.rglob('*') if p.is_file()}
    meta=json.loads((original/'job/meta.json').read_text('utf-8'))
    node=NodeService(Settings(role='A',shared_root=str(out/'share')),out/'A',lambda *a:None)
    node.box=Mailbox(out/'share',out/'A');node.box.connect()
    job=node.box.job(meta['id'])
    shutil.copytree(original/'job',job)
    atomic_json(node.box.root/'nodes/B.json',{'features':[FEATURE]})
    plan=node.prepare_recovery(meta['id'],'B','继续',meta['project']['id'])
    assert plan['index']==1 and plan['target']=='B' and len(plan['turns'])==1
    assert plan['parent_evidence']['legacy']['kind']=='legacy_peer_failure'
    assert not node.thread.is_alive() and node.client is None
    assert before=={str(p.relative_to(original)):digest(p) for p in original.rglob('*') if p.is_file()}
    result=dict(status='PASS_COPY_PLAN_ONLY',index=plan['index'],target=plan['target'],
                preserved_A_turns=len(plan['turns']),legacy_reason=plan['parent_evidence']['legacy']['kind'],
                original_hashes_unchanged=True,model_requests=0,original_shared_writes=0)
    (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
