import argparse
import os
from pathlib import Path
import sys
import traceback


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir')
    parser.add_argument('--role', choices=['A', 'B'])
    parser.add_argument('--preview', help='Save an offline preview screenshot and exit')
    parser.add_argument('--import-file')
    args = parser.parse_args()
    if args.preview:
        os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    from PyQt5 import QtCore, QtGui, QtWidgets
    from app.storage import default_data_dir, Settings, import_legacy, FileLock
    from app.ui import MainWindow
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling)
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps)
    application = QtWidgets.QApplication(sys.argv[:1])
    if args.preview:
        # Qt's Windows offscreen plugin has no system font database.
        for name in ('msyh.ttc', 'msyhbd.ttc', 'segoeui.ttf'):
            font_path = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / name
            if font_path.exists():
                QtGui.QFontDatabase.addApplicationFont(str(font_path))
    application.setStyle('Fusion')
    application.setApplicationName('AgentLink GUI')
    application.setFont(QtGui.QFont('Microsoft YaHei', 10))
    data = Path(args.data_dir) if args.data_dir else default_data_dir()
    data.mkdir(parents=True, exist_ok=True)
    try:
        gui_lock = FileLock(data / 'gui.lease').acquire()
    except RuntimeError:
        QtWidgets.QMessageBox.information(None, 'AgentLink 已打开', '本机已有 AgentLink GUI 窗口，请使用已打开的窗口。')
        return 0
    def exception_hook(kind, value, tb):
        detail = ''.join(traceback.format_exception(kind, value, tb))
        with (data / 'gui-errors.log').open('a', encoding='utf-8') as handle:
            handle.write(detail + '\n')
        QtWidgets.QMessageBox.critical(None, 'AgentLink 遇到问题', str(value) + '\n\n详细日志：' + str(data / 'gui-errors.log'))
    sys.excepthook = exception_hook
    settings = Settings.load(data)
    first = not (data / 'settings.json').exists()
    if args.role and first:
        settings.role = args.role
    if first:
        settings.auto_connect = False
    window = MainWindow(settings, data, start_service=not args.preview)
    window.show()
    if args.import_file:
        imported = import_legacy(args.import_file)
        window.view_job_id = imported['meta']['id']
        window.receive('discussion', imported)
    if args.preview:
        QtCore.QTimer.singleShot(350, lambda: (window.grab().save(args.preview), application.quit()))
    elif first:
        QtCore.QTimer.singleShot(200, window.open_settings)
    try:
        return application.exec_()
    finally:
        gui_lock.close()


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, traceback.format_exc(), 'AgentLink 启动失败', 0x10)
        raise
