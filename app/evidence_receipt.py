"""Verify an explicitly delivered original ZIP; never extracts files or runs evidence."""
import argparse,hashlib,json,re,stat,zipfile
from pathlib import Path,PurePosixPath
from .storage import io_path,atomic_json,now

def verify(archive,expected,out,conversation,job,step,sender,receiver):
    if not re.fullmatch('[a-fA-F0-9]{64}',expected):raise ValueError('必须提供发送方声明的原 ZIP SHA-256')
    for value in (conversation,job,step):
        if not re.fullmatch('[A-Za-z0-9_-]{1,128}',value):raise ValueError('回执归属编号无效')
    if sender not in ('A','B') or receiver not in ('A','B') or sender==receiver:raise ValueError('发送与接收节点必须不同')
    archive=Path(archive);out=Path(out);sha=hashlib.sha256()
    # One open handle binds digest and CRC/index verification to the same original.
    with io_path(archive).open('rb') as raw:
        for chunk in iter(lambda:raw.read(1024*1024),b''):sha.update(chunk)
        if sha.hexdigest()!=expected.lower():raise ValueError('原 ZIP SHA-256 不匹配；拒绝生成通过回执')
        raw.seek(0)
        with zipfile.ZipFile(raw) as z:
            items=z.infolist();names=set()
            if len(items)>100000 or sum(i.file_size for i in items)>512*1024*1024:raise ValueError('证据包超出受控核验容量')
            for info in items:
                path=PurePosixPath(info.filename.replace('\\','/'));name=str(path).casefold()
                if (path.is_absolute() or '..' in path.parts or ':' in info.filename or name in names
                        or stat.S_ISLNK(info.external_attr>>16) or info.flag_bits&1):raise ValueError('证据包包含不安全、重复或加密条目')
                names.add(name)
            io_path(out).mkdir(parents=True,exist_ok=False)
            record=dict(schema=1,archive=str(archive.resolve()),archive_sha256=expected.lower(),conversation=conversation,
                job=job,step=step,sender=sender,receiver=receiver,time=now(),status='verifying',agent_read=False,tests_executed=False)
            atomic_json(out/'receipt.json',record)
            try:
                index_sha=hashlib.sha256();count=0
                with io_path(out/'files-index.jsonl').open('xb') as index:
                    for info in items:
                        if info.is_dir():continue
                        h=hashlib.sha256();size=0
                        with z.open(info) as member:
                            for chunk in iter(lambda:member.read(64*1024),b''):h.update(chunk);size+=len(chunk)
                        line=(json.dumps(dict(path=info.filename,bytes=size,sha256=h.hexdigest()),ensure_ascii=False)+'\n').encode('utf-8')
                        index.write(line);index_sha.update(line);count+=1
                record.update(status='hash_verified',zip_crc='passed',files=count,index_sha256=index_sha.hexdigest(),
                    index='files-index.jsonl',scope='Original ZIP bytes and entries verified locally; independent reading/testing not established')
            except Exception as error:
                record.update(status='failed',error=type(error).__name__);atomic_json(out/'receipt.json',record);raise
            atomic_json(out/'receipt.json',record);return record

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('archive','sha256','out','conversation','job','step','sender','receiver'):p.add_argument('--'+name,required=True)
    a=p.parse_args();print(json.dumps(verify(a.archive,a.sha256,a.out,a.conversation,a.job,a.step,a.sender,a.receiver),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
