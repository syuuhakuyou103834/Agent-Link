"""Build an offline, inspectable Python/PyQt runtime and one-file C# installer."""
from pathlib import Path
import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import __version__ as VERSION
DIST = ROOT / 'dist'
PORTABLE = DIST / ('AgentLink-GUI-' + VERSION)
RUNTIME = PORTABLE / 'runtime'
PYTHON = Path(sys.base_prefix)
QT = PYTHON / 'Lib' / 'site-packages' / 'PyQt5'
CSC = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Microsoft.NET' / 'Framework64' / 'v4.0.30319' / 'csc.exe'
TEMP = ROOT / 'build-temp'


def copy(source, target):
    target = Path(target); target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def compile_cs(source, output, resource=None):
    env = os.environ.copy(); env.update(TEMP=str(TEMP), TMP=str(TEMP))
    manifest = TEMP / 'AgentLink.manifest'
    manifest.write_text((ROOT / 'packaging' / 'app.manifest').read_text(encoding='utf-8').replace('AGENTLINK_VERSION', VERSION), encoding='utf-8')
    command = [str(CSC), '/nologo', '/target:winexe', '/platform:anycpu', '/optimize+', '/codepage:65001',
        '/reference:System.Windows.Forms.dll', '/reference:System.Drawing.dll',
        '/reference:System.IO.Compression.dll', '/reference:System.IO.Compression.FileSystem.dll',
        '/win32manifest:' + str(manifest), '/out:' + str(output)]
    if resource:
        command.append('/resource:' + str(resource) + ',payload.zip')
    generated = TEMP / ('generated-' + Path(source).name)
    text = Path(source).read_text(encoding='utf-8-sig').replace('AGENTLINK_VERSION', VERSION)
    generated.write_text(text, encoding='utf-8-sig')
    command.append(str(generated))
    subprocess.run(command, check=True, env=env, cwd=ROOT, creationflags=subprocess.CREATE_NO_WINDOW)


def archive(folder, target):
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zip:
        for path in sorted(folder.rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
                zip.write(path, path.relative_to(folder).as_posix())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--zip-only', action='store_true')
    args = parser.parse_args()
    for path in (DIST, PORTABLE, RUNTIME, TEMP):
        path.mkdir(parents=True, exist_ok=True)
    for name in ('python.exe', 'pythonw.exe', 'python313.dll', 'python3.dll', 'vcruntime140.dll', 'vcruntime140_1.dll'):
        copy(PYTHON / name, RUNTIME / name)
    for path in (PYTHON / 'DLLs').iterdir():
        if path.suffix.lower() in ('.pyd', '.dll') and '_d.' not in path.name and not any(s in path.name.lower() for s in ('tkinter', 'tcl', 'tk86')):
            copy(path, RUNTIME / 'DLLs' / path.name)
    with zipfile.ZipFile(RUNTIME / 'python313.zip', 'w', zipfile.ZIP_DEFLATED) as zip:
        for path in (PYTHON / 'Lib').rglob('*.py'):
            relative = path.relative_to(PYTHON / 'Lib')
            if any(p in ('site-packages', '__pycache__', 'test', 'tests', 'tkinter', 'idlelib', 'ensurepip') for p in relative.parts):
                continue
            zip.write(path, relative.as_posix())
    # A minimal set of Qt modules; keep the platform and image plugins dynamically replaceable.
    qt_target = RUNTIME / 'site-packages' / 'PyQt5'
    for name in ('__init__.py', 'QtCore.pyd', 'QtGui.pyd', 'QtWidgets.pyd', 'QtTest.pyd', 'sip.cp313-win_amd64.pyd'):
        copy(QT / name, qt_target / name)
    bins = ('Qt5Core.dll', 'Qt5Gui.dll', 'Qt5Widgets.dll', 'Qt5Test.dll', 'Qt5Svg.dll',
            'msvcp140.dll', 'msvcp140_1.dll', 'msvcp140_2.dll', 'concrt140.dll',
            'vcruntime140.dll', 'vcruntime140_1.dll')
    # This app renders ordinary raster widgets, no OpenGL/Direct3D views.
    # Remove only known optional files from earlier builds, within this package.
    for name in ('d3dcompiler_47.dll', 'libEGL.dll', 'libGLESv2.dll', 'opengl32sw.dll'):
        old = qt_target / 'Qt5' / 'bin' / name
        if old.resolve().is_relative_to(PORTABLE.resolve()) and old.exists():
            old.unlink()
    for name in bins:
        copy(QT / 'Qt5' / 'bin' / name, qt_target / 'Qt5' / 'bin' / name)
    for group in ('platforms', 'imageformats', 'styles', 'iconengines'):
        source = QT / 'Qt5' / 'plugins' / group
        if source.exists():
            shutil.copytree(source, qt_target / 'Qt5' / 'plugins' / group, dirs_exist_ok=True)
    (RUNTIME / 'python313._pth').write_text('python313.zip\nDLLs\nsite-packages\n..\n', encoding='ascii')
    copy(ROOT / 'main.py', PORTABLE / 'main.py')
    copy(ROOT / 'packaging' / 'Repair-CodexRuntime.cmd', PORTABLE / 'Repair-CodexRuntime.cmd')
    shutil.copytree(ROOT / 'app', PORTABLE / 'app', dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__'))
    copy(ROOT / 'README.md', PORTABLE / 'README.md')
    copy(ROOT / ('DEBUG-' + VERSION + '.md'), PORTABLE / ('DEBUG-' + VERSION + '.md'))
    for folder in ('app', 'packaging', 'tests', 'docs'):
        shutil.copytree(ROOT / folder, PORTABLE / 'source' / folder, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__'))
    copy(ROOT / 'main.py', PORTABLE / 'source' / 'main.py')
    copy(ROOT / 'README.md', PORTABLE / 'source' / 'README.md')
    copy(ROOT / 'BUILDING.txt', PORTABLE / 'source' / 'BUILDING.txt')
    copy(ROOT / ('DEBUG-' + VERSION + '.md'), PORTABLE / 'source' / ('DEBUG-' + VERSION + '.md'))
    copy(ROOT / 'AGENTS.md', PORTABLE / 'source' / 'AGENTS.md')
    for prefix in ('RELEASE-', 'DEVELOPMENT-LOG-'):
        name = prefix + VERSION + '.md'
        copy(ROOT / name, PORTABLE / name)
        copy(ROOT / name, PORTABLE / 'source' / name)
        copy(ROOT / name, DIST / name)
    # Include the complete documented source baseline, including historical
    # reports retained for provenance. Never copy build outputs or credentials.
    for path in ROOT.iterdir():
        if path.is_file() and (path.suffix in ('.md', '.py', '.txt') or path.name == '.gitignore'):
            copy(path, PORTABLE / 'source' / path.name)
    license_dir = PORTABLE / 'licenses'; license_dir.mkdir(exist_ok=True)
    copy(PYTHON / 'LICENSE.txt', license_dir / 'Python-3.13-LICENSE.txt')
    copy(QT.parent / 'PyQt5_Qt5-5.15.2.dist-info' / 'LICENSE', license_dir / 'Qt-LICENSE.txt')
    for dist in ('PyQt5-5.15.11.dist-info', 'PyQt5_Qt5-5.15.2.dist-info', 'pyqt5_sip-12.18.0.dist-info'):
        copy(QT.parent / dist / 'METADATA', license_dir / (dist + '-METADATA.txt'))
        for path in (QT.parent / dist).rglob('*'):
            if path.is_file() and ('license' in path.name.lower() or 'copying' in path.name.lower()):
                copy(path, license_dir / (dist + '-' + path.name))
    qt_license = (license_dir / 'Qt-LICENSE.txt').read_text(encoding='utf-8')
    start = qt_license.find('                    GNU GENERAL PUBLIC LICENSE')
    end = qt_license.find('                    GNU LESSER GENERAL PUBLIC LICENSE', start + 1)
    (license_dir / 'GPL-3.0.txt').write_text(qt_license[start:end] if end > start else qt_license[start:], encoding='utf-8')
    (license_dir / 'NOTICE.txt').write_text(
        'AgentLink GUI source is provided under GPL-3.0.\n'
        'PyQt5 5.15.11: GPL-3.0, Copyright Riverbank Computing Limited.\n'
        'Source: https://pypi.org/project/PyQt5/5.15.11/#files\n'
        'PyQt5-sip 12.18.0 source: https://pypi.org/project/PyQt5-sip/12.18.0/#files\n'
        'Qt 5.15.2 (unmodified dynamically linked libraries): LGPL/GPL.\n'
        'Source: https://download.qt.io/archive/qt/5.15/5.15.2/single/\n'
        'Python 3.13.13: PSF license. Source: https://www.python.org/downloads/release/python-31313/\n'
        'Dependencies are unmodified and replaceable in runtime/. App source and build scripts are in source/.\n', encoding='utf-8')
    compile_cs(ROOT / 'packaging' / 'Launcher.cs', PORTABLE / 'AgentLink.exe')
    payload = DIST / ('AgentLink-GUI-' + VERSION + '-Windows-x64.zip')
    archive(PORTABLE, payload)
    files = [payload]
    if not args.zip_only:
        digest = hashlib.sha256(payload.read_bytes()).hexdigest().upper()
        setup_source = (ROOT / 'packaging' / 'Setup.cs').read_text(encoding='utf-8').replace('PAYLOAD_HASH', digest)
        (TEMP / 'Setup.cs').write_text(setup_source, encoding='utf-8-sig')
        installer = DIST / ('AgentLink-GUI-' + VERSION + '-Setup.exe')
        compile_cs(TEMP / 'Setup.cs', installer, payload)
        files.append(installer)
    (DIST / ('SHA256SUMS-' + VERSION + '.txt')).write_text('\n'.join(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.name for p in files) + '\n', encoding='ascii')
    for file in files:
        print(str(file) + '  %.1f MB' % (file.stat().st_size / 1024**2))


if __name__ == '__main__':
    main()
