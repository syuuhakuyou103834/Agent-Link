"""Verify the actual Windows Qt platform plugin without showing a window to the user."""
import os
os.environ['QT_QPA_PLATFORM'] = 'windows'
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PyQt5 import QtCore, QtWidgets as W
from app.ui import MainWindow, SettingsDialog
from app.storage import Settings
app = W.QApplication([])
app.setStyle('Fusion')
root = __import__('fixture_paths').output_root() / 'windows-plugin'
root.mkdir(parents=True, exist_ok=True)
window = MainWindow(Settings(auto_connect=False), root, start_service=False)
window.move(-32000, -32000)
window.show()
app.processEvents()
assert app.platformName() == 'windows'
assert window.grab().save(str(root / 'windows-main.png'))
dialog = SettingsDialog(window.settings)
dialog.move(-32000, -32000)
dialog.show()
app.processEvents()
assert dialog.grab().save(str(root / 'windows-settings.png'))
dialog.close(); window.close()
print('PASS: native Windows platform plugin, main window and settings render with bundled runtime.')
