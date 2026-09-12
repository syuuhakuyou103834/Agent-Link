"""Local project bindings. Shared metadata never authorizes an A-side path."""
from pathlib import Path
import re
import uuid
from .storage import atomic_json, read_json, now, plain_path, canonical_path, io_path

FEATURE = 'project-review-v1'


def project_id(value):
    if not isinstance(value, str) or not re.fullmatch('[a-f0-9]{32}', value):
        raise ValueError('项目编号无效')
    return value


def local_directory(value):
    path = plain_path(value).absolute()
    if not value or str(path).startswith(('\\\\', '//')) or path == Path(path.anchor):
        raise ValueError('请选择本机的具体项目目录，不能选择整盘或网络路径。')
    for parent in (path, *path.parents):
        if io_path(parent).exists() and (io_path(parent).is_symlink() or io_path(parent).is_junction()):
            raise ValueError('项目路径不能经过链接或目录联接：' + str(parent))
    return canonical_path(path)


def separate(left, right):
    a, b = canonical_path(left), canonical_path(right)
    if a == b or a in b.parents or b in a.parents:
        raise ValueError('项目、共享通信目录及接收/测试目录必须互不包含。')


class Projects:
    def __init__(self, data):
        self.data = Path(data)
        self.path = self.data / 'projects.json'

    def all(self):
        return read_json(self.path, {'schema': 1, 'projects': []})['projects']

    def get(self, identifier):
        project_id(identifier)
        for value in self.all():
            if value['id'] == identifier:
                return value
        raise ValueError('本机尚未绑定此项目，请先在项目管理中绑定。')

    def save(self, name, directory, role, identifier=None, dependencies=None):
        identifier = project_id(identifier) if identifier else uuid.uuid4().hex
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120:
            raise ValueError('项目名称应为 1 至 120 个字符')
        root = local_directory(directory)
        separate(root, self.data)
        if role == 'A' and not io_path(root).is_dir():
            raise ValueError('A 的项目目录必须已存在。')
        if role not in ('A', 'B'):
            raise ValueError('节点角色无效')
        deps = []
        for value in dependencies or []:
            dep = local_directory(value)
            if not io_path(dep).exists():
                raise ValueError('声明的只读依赖不存在：' + str(dep))
            separate(dep, root)
            deps.append(str(dep))
        records = [v for v in self.all() if v['id'] != identifier]
        for v in records:
            separate(v['directory'], root)
        item = dict(id=identifier, name=name.strip(), directory=str(root), role=role,
                    dependencies=deps, updated=now())
        records.append(item)
        atomic_json(self.path, {'schema': 1, 'projects': records})
        return item

    def bound(self, identifier, role, shared):
        value = self.get(identifier)
        if value['role'] != role:
            raise ValueError('项目绑定角色与当前节点不一致，请重新绑定。')
        root = local_directory(value['directory'])
        separate(root, shared)
        separate(root, self.data)
        if role == 'A' and not io_path(root).is_dir():
            raise ValueError('A 的项目目录已不可用。')
        return value

    def publish(self, shared, role):
        # Each side owns its own catalog. A paths are deliberately absent.
        atomic_json(Path(shared) / 'projects' / (role + '.json'), {
            'schema': 1, 'projects': [{'id': p['id'], 'name': p['name']}
                                    for p in self.all() if p['role'] == role]})


def add_issues(shared, identifier, job_id, revision, findings):
    from .storage import _json_guard
    path = Path(shared) / 'projects' / project_id(identifier) / 'issues.json'
    io_path(path.parent).mkdir(parents=True, exist_ok=True)
    with _json_guard(path.with_suffix('.guard')):
        data = read_json(path, {'schema': 1, 'issues': []})
        for finding in findings:
            if not any(v['job_id'] == job_id and v['revision'] == revision and
                       v['description'] == finding for v in data['issues']):
                data['issues'].append(dict(id=uuid.uuid4().hex, job_id=job_id, revision=revision,
                    description=finding, status='open', updated=now()))
        atomic_json(path, data)
    return data


def update_issue(shared, identifier, issue_id, status):
    from .storage import _json_guard
    if status not in ('open', 'resolved', 'deferred'):
        raise ValueError('问题状态无效')
    path = Path(shared) / 'projects' / project_id(identifier) / 'issues.json'
    with _json_guard(path.with_suffix('.guard')):
        data = read_json(path)
        issue = next((i for i in data['issues'] if i['id'] == issue_id), None)
        if issue is None:
            raise ValueError('问题编号不存在')
        issue.update(status=status, updated=now())
        atomic_json(path, data)
