"""Whole-tree, Git-independent snapshots with explicit omissions and verified publication."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import uuid
import zipfile
from contextlib import contextmanager
from .storage import atomic_json, read_json, io_path
from .projects import local_directory, separate, project_id

MAX_FILES = 100000
MAX_BYTES = 4 * 1024**3
MAX_MANIFEST = 32 * 1024**2
OMIT_DIRS = {'.git', '.svn', '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache',
             '.venv', 'venv', 'node_modules', '.idea'}
PRIVATE = {'.env', '.npmrc', '.pypirc', 'id_rsa', 'id_ed25519', 'credentials.json', 'auth.json'}


@contextmanager
def project_file(path, root):
    """Check the opened handle before reading bytes, including Windows link races."""
    with io_path(path).open('rb') as f:
        info = os.fstat(f.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError('项目文件已被替换为链接或特殊文件')
        final = Path(path).resolve()
        if os.name == 'nt':
            import ctypes
            import msvcrt
            fn = ctypes.WinDLL('kernel32', use_last_error=True).GetFinalPathNameByHandleW
            fn.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32]
            fn.restype = ctypes.c_uint32
            buffer = ctypes.create_unicode_buffer(32768)
            length = fn(msvcrt.get_osfhandle(f.fileno()), buffer, len(buffer), 0)
            if not 0 < length < len(buffer):
                raise OSError('无法确认已打开项目文件的真实路径')
            text = buffer.value
            if text.startswith('\\\\?\\'): text = text[4:]
            final = Path(text)
        if Path(root).resolve() not in final.parents or final != Path(path).absolute():
            raise ValueError('已打开的文件不属于绑定项目，未读取内容')
        yield f


def digest(path, root=None, pump=lambda: None):
    h = hashlib.sha256()
    with (project_file(path, root) if root else io_path(path).open('rb')) as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            pump()
            h.update(block)
    return h.hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def safe_name(name):
    if not isinstance(name, str) or not name or '\\' in name or ':' in name:
        raise ValueError('交付文件路径无效')
    p = PurePosixPath(name)
    if p.is_absolute() or any(v in ('', '.', '..') for v in name.split('/')):
        raise ValueError('交付路径越界：' + name)
    for part in p.parts:
        if part.endswith((' ', '.')) or any(ord(c) < 32 for c in part) or re.match(r'(?i)^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)', part):
            raise ValueError('交付路径在 Windows 上不安全：' + name)
    return name


def inventory(root, pump=lambda: None):
    root = local_directory(root)
    entries, omitted, size = [], [], 0
    def walk(folder):
        nonlocal size
        with os.scandir(io_path(folder)) as scan:
            children = sorted(scan, key=lambda e: e.name.casefold())
        for node in children:
            item = folder / node.name
            pump()
            relative = safe_name(item.relative_to(root).as_posix())
            info = os.lstat(io_path(item))
            if getattr(info, 'st_file_attributes', 0) & 0x400:
                raise ValueError('项目含链接或重解析点，未发布：' + relative)
            name = item.name.casefold()
            reason = ('凭据/私密配置' if name in PRIVATE or name.startswith('.env.') or item.suffix.lower() in ('.pem', '.key', '.pfx', '.p12') else
                      '版本库/依赖缓存' if stat.S_ISDIR(info.st_mode) and name in OMIT_DIRS else
                      'Python 字节码' if item.suffix.lower() in ('.pyc', '.pyo') else None)
            if reason:
                omitted.append({'path': relative, 'reason': reason}); continue
            if stat.S_ISDIR(info.st_mode):
                entries.append({'path': relative, 'kind': 'directory'})
                walk(item)
            elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                size += info.st_size
                if size > MAX_BYTES:
                    raise ValueError('项目超过 4 GiB 交付上限；未截断发布。')
                entries.append({'path': relative, 'kind': 'file', 'size': info.st_size, 'sha256': digest(item, root, pump)})
            else:
                raise ValueError('不支持的文件或硬链接：' + relative)
            if len(entries) > MAX_FILES:
                raise ValueError('项目条目超过交付上限；未截断发布。')
    walk(root)
    return {'entries': entries, 'omitted': omitted}


def changed(before, after):
    a = {e['path']: e for e in (before or {}).get('entries', [])}
    b = {e['path']: e for e in after['entries']}
    return sorted(k for k in a.keys() | b.keys() if a.get(k) != b.get(k))


def publish(root, destination, identifier, job_id, revision, before=None, pump=lambda: None):
    root, destination = local_directory(root), Path(destination)
    separate(root, destination)
    snapshot = inventory(root, pump)
    manifest = dict(schema=1, project_id=project_id(identifier), job_id=job_id, revision=revision,
                    **snapshot, changed=changed(before, snapshot))
    token = hashlib.sha256(encoded(manifest)).hexdigest()
    io_path(destination).mkdir(parents=True, exist_ok=True)
    stage = destination / ('.partial-' + uuid.uuid4().hex)
    io_path(stage).mkdir()
    archive = stage / 'source.zip'
    with zipfile.ZipFile(io_path(archive), 'w', zipfile.ZIP_DEFLATED, compresslevel=3) as z:
        for entry in snapshot['entries']:
            pump()
            path = root / entry['path']
            if entry['kind'] == 'directory':
                z.writestr(entry['path'] + '/', b'')
            else:
                # A second complete inventory detects concurrent user/tool edits.
                with project_file(path, root) as src, z.open(entry['path'], 'w', force_zip64=True) as dst:
                    for block in iter(lambda: src.read(1024 * 1024), b''):
                        pump(); dst.write(block)
    if inventory(root, pump) != snapshot:
        raise ValueError('源码在打包期间发生变化，未发布不一致快照。')
    atomic_json(stage / 'manifest.json', manifest)
    receipt = dict(schema=1, project_id=identifier, job_id=job_id, revision=revision,
                   manifest_sha256=token, zip_sha256=digest(archive, pump=pump))
    atomic_json(stage / 'ready.json', receipt)
    target = destination / token
    if io_path(target).exists():
        if read_json(target / 'ready.json') != receipt:
            raise ValueError('交付编号冲突')
    else:
        os.rename(io_path(stage), io_path(target))
    return receipt, manifest


def validate_manifest(m, receipt):
    if not isinstance(m, dict) or hashlib.sha256(encoded(m)).hexdigest() != receipt['manifest_sha256']:
        raise ValueError('交付清单哈希不一致')
    if m.get('schema') != 1 or any(m.get(k) != receipt.get(k) for k in ('project_id', 'job_id', 'revision')):
        raise ValueError('交付归属不一致')
    if not isinstance(m.get('entries'), list) or len(m['entries']) > MAX_FILES:
        raise ValueError('交付清单条目无效')
    seen, total = set(), 0
    for entry in m['entries']:
        name = safe_name(entry['path'])
        if name.casefold() in seen:
            raise ValueError('交付存在重名文件')
        seen.add(name.casefold())
        if entry['kind'] == 'file':
            if type(entry.get('size')) is not int or entry['size'] < 0 or not re.fullmatch('[a-f0-9]{64}', entry.get('sha256', '')):
                raise ValueError('交付文件摘要无效')
            total += entry['size']
        elif entry['kind'] != 'directory':
            raise ValueError('交付条目类型无效')
    if total > MAX_BYTES:
        raise ValueError('交付超出大小上限')


def receive(destination, local, receipt, pump=lambda: None):
    token = receipt.get('manifest_sha256', '')
    if not isinstance(token, str) or not re.fullmatch('[a-f0-9]{64}', token):
        raise ValueError('快照编号无效')
    package = Path(destination) / token
    if read_json(package / 'ready.json') != receipt:
        raise ValueError('源码尚未完整发布或发布记录不一致')
    m = read_json(package / 'manifest.json', limit=MAX_MANIFEST)
    validate_manifest(m, receipt)
    local = local_directory(local)
    io_path(local).mkdir(parents=True, exist_ok=True)
    source = local / token
    if io_path(source).exists():
        verify(source, m, pump)
        return source, m
    stage = local / ('.partial-' + uuid.uuid4().hex)
    io_path(stage).mkdir()
    # Read the verified LOCAL archive to eliminate shared-file replacement between hash and extract.
    archive = stage / 'payload.zip'
    with io_path(package / 'source.zip').open('rb') as src, io_path(archive).open('xb') as dst:
        for block in iter(lambda: src.read(1024 * 1024), b''):
            pump(); dst.write(block)
    if digest(archive, pump=pump) != receipt['zip_sha256']:
        raise ValueError('源码包损坏，未启动审查')
    tree = stage / 'tree'; io_path(tree).mkdir()
    expected = {e['path'] + ('/' if e['kind'] == 'directory' else ''): e for e in m['entries']}
    with zipfile.ZipFile(io_path(archive)) as z:
        infos = z.infolist()
        if len(infos) != len(expected) or {i.filename for i in infos} != set(expected):
            raise ValueError('压缩包与清单文件集合不一致')
        for info in infos:
            pump()
            entry = expected[info.filename]
            if stat.S_ISLNK(info.external_attr >> 16) or info.file_size != entry.get('size', 0):
                raise ValueError('压缩包文件属性不一致')
            path = tree / entry['path']
            if entry['kind'] == 'directory':
                io_path(path).mkdir(parents=True, exist_ok=True)
            else:
                io_path(path.parent).mkdir(parents=True, exist_ok=True)
                with z.open(info) as src, io_path(path).open('xb') as dst:
                    for block in iter(lambda: src.read(1024 * 1024), b''):
                        pump(); dst.write(block)
    verify(tree, m, pump)
    os.rename(io_path(tree), io_path(source))
    return source, m


def verify(source, manifest, pump=lambda: None):
    actual = inventory(source, pump)
    if actual['entries'] != manifest['entries'] or actual['omitted']:
        raise ValueError('只读源码快照已被更改或存在额外文件，审查无效。')
