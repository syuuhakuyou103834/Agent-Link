"""Bounded result receipts and independently verifiable bodies; legacy bytes stay intact."""
import hashlib,json,os,re,socket,uuid
from pathlib import Path
from .storage import FileLock,io_path,read_json,atomic_json,now
from .context_view import digest

MAX_BODY=64*1024*1024
MAX_RECEIPT=64*1024

def _exists(path):
    try:io_path(path).stat();return True
    except FileNotFoundError:return False

def directory(data,job,step):
    if any(not isinstance(v,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',v) for v in (job,step)):
        raise ValueError('结果缓存编号无效')
    return Path(data)/'received-results'/job/step

def _validate(record,job,step,role):
    if not isinstance(record,dict):raise ValueError('已有本机返回缓存损坏：对象无效')
    if (record.get('job_id')!=job or record.get('step')!=step or record.get('host')!=socket.gethostname()
            or record.get('role',role)!=role):raise ValueError('原请求本机返回缓存的归属无效')
    if not isinstance(record.get('result'),dict) or record.get('sha256')!=digest(record['result']):
        raise ValueError('原请求本机返回缓存的摘要或正文无效')
    return record

def _load(root,job,step,role):
    modern=root/'result-v2';legacy=root/'result.json'
    if _exists(modern):
        receipt=read_json(modern/'receipt.json',limit=MAX_RECEIPT)
        if (not isinstance(receipt,dict) or receipt.get('schema')!=2 or receipt.get('body')!='body.json'
                or type(receipt.get('bytes')) is not int or not 0<=receipt['bytes']<=MAX_BODY):
            raise ValueError('结果缓存回执损坏或容量不支持')
        path=modern/'body.json';hasher=hashlib.sha256();parts=[];size=0
        with io_path(path).open('rb') as f:
            for part in iter(lambda:f.read(64*1024),b''):
                size+=len(part)
                if size>MAX_BODY:raise ValueError('结果缓存正文超出支持容量；原件保留')
                hasher.update(part);parts.append(part)
        if size!=receipt['bytes'] or hasher.hexdigest()!=receipt.get('body_sha256'):
            raise ValueError('结果缓存正文长度或摘要不符')
        record=dict(receipt,result=json.loads(b''.join(parts).decode('utf-8')))
        record=_validate(record,job,step,role);record['cache_path']=str(modern/'receipt.json')
        return record
    if _exists(legacy):
        record=_validate(read_json(legacy,limit=MAX_BODY),job,step,role)
        return dict(record,cache_path=str(legacy))
    if _exists(root) and list(io_path(root).glob('result-v2.partial-*')):
        raise ValueError('结果缓存存在未提交原件，需核查；禁止当作从未返回')
    return None

def load(data,job,step,role,required=False):
    root=directory(data,job,step)
    with FileLock(root/'cache.lease'):
        value=_load(root,job,step,role)
    if value is None and required:raise ValueError('账本记录已返回，但本机结果缓存缺失')
    if value is not None:
        proof=read_json(Path(value['cache_path']).parent/'context.json',limit=MAX_RECEIPT)
        if proof is not None:
            if not isinstance(proof,dict) or proof.get('result_sha256')!=value['sha256'] or not isinstance(proof.get('context'),dict):
                raise ValueError('结果源码关联回执无效')
            value['context']=proof['context']
    return value

def attest(data,job,step,role,context):
    root=directory(data,job,step)
    with FileLock(root/'cache.lease'):
        value=_load(root,job,step,role)
        if value is None:raise ValueError('缺少原结果，不能生成关联回执')
        path=Path(value['cache_path']).parent/'context.json'
        proof=dict(result_sha256=value['sha256'],context=context)
        if _exists(path):
            if read_json(path,limit=MAX_RECEIPT)!=proof:raise ValueError('已有结果关联回执不同，拒绝覆盖')
        else:atomic_json(path,proof)

def save(data,job,step,role,instance,result):
    if not isinstance(result,dict):raise ValueError('返回结果必须是对象')
    root=directory(data,job,step)
    with FileLock(root/'cache.lease'):
        old=_load(root,job,step,role)
        if old is not None:
            if old['result']!=result:raise ValueError('同一步骤已有不同的本机返回结果，拒绝覆盖')
            return Path(old['cache_path'])
        stage=root/('result-v2.partial-'+uuid.uuid4().hex);io_path(stage).mkdir()
        hasher=hashlib.sha256();size=0
        # Even an unsupported large body remains as an uncommitted original.
        with io_path(stage/'body.json').open('xb') as f:
            for text in json.JSONEncoder(ensure_ascii=False,sort_keys=True).iterencode(result):
                chunk=text.encode('utf-8');f.write(chunk);hasher.update(chunk);size+=len(chunk)
            f.flush();os.fsync(f.fileno())
        if size>MAX_BODY:
            atomic_json(stage/'failure.json',dict(reason='body_too_large',bytes=size,sha256=hasher.hexdigest()))
            raise ValueError('返回结果超过 64 MiB 自动处理容量；原始正文已保留，需核查')
        record=dict(schema=2,job_id=job,step=step,role=role,instance=instance,host=socket.gethostname(),
                    received_at=now(),body='body.json',bytes=size,body_sha256=hasher.hexdigest(),
                    sha256=digest(result),verification='raw received; not validated/published')
        atomic_json(stage/'receipt.json',record)
        os.replace(io_path(stage),io_path(root/'result-v2'))
        return root/'result-v2'/'receipt.json'
