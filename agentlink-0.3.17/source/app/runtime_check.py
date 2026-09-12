"""Validate Codex companion files without changing sandbox policy or user PATH."""
import os
from pathlib import Path
import shutil

COMPANIONS = ('codex-windows-sandbox-setup.exe', 'codex-command-runner.exe', 'codex-code-mode-host.exe')


def runtime_status(command):
    if os.name != 'nt' or not command or Path(command[0]).name.lower() != 'codex.exe':
        return {'ready': True, 'missing': [], 'checked': False}
    exe = Path(shutil.which(command[0]) or command[0]).resolve()
    missing = [name for name in COMPANIONS if not (exe.parent / name).is_file()]
    return {'ready': exe.is_file() and not missing, 'missing': missing,
            'checked': True, 'directory': str(exe.parent)}


def require_project_runtime(command):
    status = runtime_status(command)
    if not status['ready']:
        raise RuntimeError('本机 Codex 运行组件不完整，未发送模型请求。目录：' + status['directory']
            + '；缺少：' + ', '.join(status['missing'])
            + '。请运行随包 Repair-CodexRuntime.ps1，或修复本机 Codex 安装；不要删除源码清单或关闭沙盒。')
    return status


def runtime_environment(command):
    env = os.environ.copy()
    if os.name == 'nt' and command and Path(command[0]).name.lower() == 'codex.exe':
        exe = Path(shutil.which(command[0]) or command[0]).resolve()
        key = next((key for key in env if key.upper() == 'PATH'), 'PATH')
        env[key] = str(exe.parent) + os.pathsep + env.get(key, '')
    return env
