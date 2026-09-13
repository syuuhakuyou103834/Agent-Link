"""Lossless archive, bounded send view. Never mutate the shared source transcript."""
from .storage import io_path
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import uuid
from .context import check_prompt
from .storage import atomic_json, read_json, _json_guard

FEATURE = 'bounded-context-evidence-v1'
SOFT_CHARS = 180000  # leaves room for scope, instructions and current input
SOFT_BYTES = 600000
FIELDS = ('id','sequence','speaker','text','kind','origin','target','user_message','submitted_phase','brief_sha256','job_id','step','phase')

def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',',':')).encode('utf-8')

def digest(value):return hashlib.sha256(encoded(value)).hexdigest()

def project(value):
    messages=[]
    for original in value['messages']:
        m={k:copy.deepcopy(original[k]) for k in FIELDS if k in original}
        turn=original.get('turn')
        if turn:
            # Full readable review text already contains scope, tests and unverified issues.
            m['result']={k:turn[k] for k in ('role','phase','status','step','thread_id','final_decision') if k in turn}
            if turn.get('review'):m['result']['decision']=turn['review']['decision']
            if turn.get('artifact'):m['result']['snapshot']=turn['artifact'].get('manifest_sha256')
            m['evidence_file']='turn-'+digest(turn)+'.json'
        messages.append(m)
    return dict(messages=messages,confirmed=copy.deepcopy(value.get('confirmed')),
                confirmation=copy.deepcopy(value.get('confirmation')),pending=list(value.get('pending',[])),
                completed_rounds=value['completed_rounds'],phase=value['phase'])

def save_checked(path,value,create=False):
    # Immutable evidence reads must not create parent folders or lock files.
    path=io_path(path)
    if not path.exists():
        if not create:raise ValueError('本机上下文证据缺失，未重建：'+str(path))
        atomic_json(path,value)
    try:old=json.loads(path.read_text(encoding='utf-8'))
    except (UnicodeError,json.JSONDecodeError) as error:
        raise ValueError('本机上下文证据被改动：'+str(path)) from error
    if encoded(old)!=encoded(value):raise ValueError('本机上下文证据被改动：'+str(path))

def prepare(value, base, prior_receipts=()):
    """Materialize peer-origin evidence only in this node's dedicated read-only scope."""
    view=project(value)
    bundle_id=digest({'messages':value['messages'],'confirmed':value.get('confirmed')})
    base=Path(base);root=base/bundle_id
    entries=[]
    objects=[]
    for original,message in zip(value['messages'],view['messages']):
        name='message-'+digest(message)+'.json'
        objects.append((name,message))
        entry=dict(id=message['id'],sequence=message['sequence'],speaker=message['speaker'],file=name,sha256=digest(message))
        if original.get('turn'):
            objects.append((message['evidence_file'],original['turn']))
            entry['turn']=dict(file=message['evidence_file'],sha256=digest(original['turn']))
        entries.append(entry)
    index=dict(schema=1,conversation=value['id'],bundle=bundle_id,entries=entries,
               hash_algorithm='SHA-256 of UTF-8 JSON, sorted keys, separators comma/colon, ensure_ascii=False',
               note='仅为保存的证据，不代表已读取或已验证。工具输出为软件捕获片段；不改变用户权限。')
    objects.append(('index.json',index))
    commit=dict(schema=1,bundle=bundle_id,index_sha256=digest(index))
    anchor=base/'.committed'/(bundle_id+'.json')
    references=list(prior_receipts)+[a.get('context_view') for a in value.get('attempts',[])]
    referenced=any(isinstance(r,dict) and r.get('bundle')==bundle_id for r in references)
    io_path(anchor.parent).mkdir(parents=True,exist_ok=True)
    with _json_guard(base/'.committed'/(bundle_id+'.guard')):
        existed=io_path(root).exists()
        committed=io_path(anchor).exists()
        if committed or existed or referenced:
            if not existed:raise ValueError('已引用的上下文证据包缺失，未重建：'+str(root))
            if io_path(root).is_symlink() or io_path(root).is_junction():
                raise ValueError('上下文证据目录被替换为链接')
            if committed:save_checked(anchor,commit)
            for name,content in objects:save_checked(root/name,content)
            # Compatible 0.3.21 bundles are adopted only after full verification.
            if not committed:save_checked(anchor,commit,create=True)
        else:
            stage=base/('.partial-'+bundle_id+'-'+uuid.uuid4().hex)
            io_path(stage).mkdir(parents=True)
            try:
                for name,content in objects:save_checked(stage/name,content,create=True)
                os.rename(io_path(stage),io_path(root))
                save_checked(anchor,commit,create=True)
            except Exception as error:
                # Keep failure metadata, reclaim only this call's staged bytes.
                try:
                    atomic_json(base/('failure-'+stage.name+'.json'),dict(bundle=bundle_id,error=str(error)))
                    if (stage.resolve().parent==base.resolve() and io_path(stage).exists()
                            and not io_path(stage).is_symlink() and not io_path(stage).is_junction()):
                        shutil.rmtree(io_path(stage))
                except OSError as cleanup_error:error.add_note(str(cleanup_error))
                raise
    view['evidence']=dict(directory=str(root.resolve()),index='index.json',sha256=digest(index))
    # Do not manufacture a semantic summary. Older answers become explicit full-text references.
    moved=[]
    for n,m in enumerate(view['messages']):
        text=json.dumps(view,ensure_ascii=False)
        if len(text)<=SOFT_CHARS and len(json.dumps(text,ensure_ascii=False).encode('utf-8'))<=SOFT_BYTES:break
        if (n>=len(view['messages'])-4 or m['speaker'] in ('user','system')
                or m['id'] in value.get('pending',[]) or m.get('result',{}).get('decision') in ('blocked','changes_requested')):
            continue
        if len(m.get('text',''))<500:continue
        m.pop('text')
        m['archived_body']=dict(file=entries[n]['file'],sha256=entries[n]['sha256'],
                               note='完整正文转为文件引用，未截断原文；必要时读取后再作判断，不得视为已经阅读。')
        moved.append(m['sequence'])
    if moved:view['history_checkpoint']=dict(archived_sequences=moved,
        policy='原文完整外置，非模型概括；用户要求、系统状态、pending、未决审查及最近消息保留。')
    text=json.dumps(view,ensure_ascii=False)
    receipt=dict(schema=1,bundle=bundle_id,index=str(root/'index.json'),index_sha256=digest(index),
                 message_ids=[m['id'] for m in view['messages']],archived_sequences=moved,
                 chars=len(text),json_bytes=len(json.dumps(text,ensure_ascii=False).encode('utf-8')),
                 tools_inlined=False,original_message_count=len(value['messages']))
    check_prompt(text,'正文与证据索引')
    return text,root,receipt
