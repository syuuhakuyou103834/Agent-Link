"""Replay a supplied private conversation through the real chat builder, zero model calls.

Usage: python tests/replay_context_fixture.py frozen-conversation.json output-directory
The fixture stays read-only. Output includes a local isolated transcript and evidence;
publish metrics.json only, not private contents.
"""
import copy,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.engine import NodeService
from app.storage import Settings,Mailbox,atomic_json
from app.context import check_prompt

def main():
    fixture=Path(sys.argv[1]);out=Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=False)
    raw=fixture.read_bytes();original=json.loads(raw)
    old=json.dumps(dict(messages=original['messages'],confirmed=original['confirmed'],
                       completed_rounds=original['completed_rounds'],phase=original['phase']),ensure_ascii=False)
    node=NodeService(Settings(role='B',shared_root=str(out/'share')),out/'B',lambda *a:None)
    node.box=Mailbox(out/'share',out/'B');node.box.connect();node.connected=True
    c=copy.deepcopy(original);msg=next(m for m in c['messages'] if m['id'] in c['pending'] and m.get('target')=='B')
    c['phase']=c.get('paused_from','working')
    atomic_json(node.conversations.path(c['id']),c)
    calls=[]
    class Capture:
        cleanup_pending=False
        def start(self):pass
        def close(self):pass
        def new_thread(self,settings,cwd,instructions):
            self.settings=copy.deepcopy(settings)
            return 'fixture-only-no-model'
        def run_turn(self,thread,prompt,*args):
            check_prompt(prompt);calls.append(prompt)
            return {'answer':json.dumps(dict(message='本机回放成功；未调用模型',ready=True,brief=c['confirmed'],action='advice'),ensure_ascii=False)}
    node.client=Capture();node._unified_chat(c,msg)
    current=node.conversations.get(c['id'])
    assert len(calls)==1 and msg['id'] not in current['pending'],current.get('error')
    assert current['completed_rounds']==original['completed_rounds']
    assert fixture.read_bytes()==raw
    view,_=json.JSONDecoder().raw_decode(calls[0].split('\n',1)[1])
    assert [m['text'] for m in view['messages']]==[m['text'] for m in original['messages']]
    assert all('turn' not in m for m in view['messages'])
    index=Path(view['evidence']['directory'])/'index.json'
    original_tools=sum(len(m.get('turn',{}).get('tools',[])) for m in original['messages'])
    result=dict(original_sha256=hashlib.sha256(raw).hexdigest(),original_file_bytes=len(raw),
        old_context_chars=len(old),old_context_wire_bytes=len(json.dumps(old,ensure_ascii=False).encode('utf-8')),
        new_context_chars=len(json.dumps(view,ensure_ascii=False)),new_full_chat_chars=len(calls[0]),
        new_full_chat_wire_bytes=len(json.dumps(calls[0],ensure_ascii=False).encode('utf-8')),
        messages=len(view['messages']),original_tools=original_tools,all_message_texts_preserved=True,
        pending_target='B',pending_original_processed=True,completed_rounds=original['completed_rounds'],
        original_unchanged=True,local_evidence_index_created=index.exists(),model_requests=0,
        scope_note='Actual chat builder with capture client; not independent B/SMB/model acceptance')
    (out/'metrics.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
