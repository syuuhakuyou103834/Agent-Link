"""PyQt5 desktop view. Network work is delivered by queued Qt signals."""
from dataclasses import asdict
from datetime import datetime
import html
import json
import os
from pathlib import Path
from PyQt5 import QtCore, QtGui, QtWidgets as W
from .storage import Settings, report_text, turn_title
from .engine import NodeService
from . import __version__
from .context import readable_context
from .projects import Projects, separate
from .storage import read_json

STATUS = {'offline': '离线', 'connecting': '连接中', 'idle': '就绪', 'running': '生成中',
          'waiting_peer': '等待对方', 'paused': '已暂停', 'stopping': '正在停止',
          'completed': '已完成', 'failed': '失败', 'cancelled': '已停止', 'incomplete': '未完成'}
STYLE = """
QWidget { font-family: 'Microsoft YaHei'; font-size: 10pt; color: #203149; }
QMainWindow, QDialog { background: #f4f6fa; }
QFrame#sidebar { background: #e9eef5; border-right: 1px solid #d7dfeb; }
QLabel#brand { font-size: 23pt; font-weight: 700; color: #203f66; }
QLabel#title { font-size: 17pt; font-weight: 650; }
QLabel#muted { color: #64748b; }
QLabel#badge { background: #e8eef7; border-radius: 10px; padding: 7px 12px; }
QLabel#notice { color: #924d14; background: #fff4df; border-radius: 7px; padding: 9px; }
QPushButton { background: white; border: 1px solid #d2dbe7; border-radius: 7px; padding: 8px 13px; }
QPushButton:hover { background: #eaf1fb; border-color: #9aafcf; }
QPushButton:disabled { color: #9aa6b7; background: #edf0f4; }
QPushButton#primary { color: white; background: #2861b5; border: none; font-weight: 600; }
QPushButton#primary:hover { background: #1f529d; }
QPushButton#primary:disabled { color: #9aa6b7; background: #e5ebf3; }
QPushButton#danger { color: #a33136; }
QPushButton#danger:disabled { color: #9aa6b7; }
QLineEdit, QPlainTextEdit, QTextBrowser, QSpinBox, QComboBox { background: white; border: 1px solid #d4deea; border-radius: 7px; padding: 7px; selection-background-color: #bed6f8; }
QTextBrowser { padding: 16px; }
QListWidget { background: transparent; border: none; outline: none; }
QListWidget::item { padding: 12px 8px; margin: 3px 0; border-radius: 7px; }
QListWidget::item:selected { background: #d6e3f7; color: #174b8e; }
QTabWidget::pane { border: none; }
QTabBar::tab { padding: 10px 18px; color: #68768b; }
QTabBar::tab:selected { color: #225cb0; border-bottom: 3px solid #2861b5; }
QGroupBox { border: 1px solid #d6dfeb; border-radius: 8px; margin-top: 13px; padding: 12px; }
QGroupBox::title { subcontrol-origin: margin; left: 14px; color: #315174; }
QProgressBar { border: none; border-radius: 3px; background: #e2e8f1; max-height: 5px; }
QProgressBar::chunk { background: #5186ce; border-radius: 3px; }
QStatusBar { background: #eaf0f7; color: #607087; }
"""


def button(text, callback, primary=False):
    widget = W.QPushButton(text)
    widget.clicked.connect(callback)
    if primary:
        widget.setObjectName('primary')
    return widget


def browser():
    widget = W.QTextBrowser()
    widget.setOpenExternalLinks(False)
    widget.setOpenLinks(False)
    widget.setReadOnly(True)
    return widget


def text_html(text):
    return html.escape(str(text)).replace('\n', '<br>')


def set_html(view, value):
    if view.property('content') == value:
        return
    scroll = view.verticalScrollBar()
    position, following = scroll.value(), scroll.maximum() - scroll.value() < 25
    view.setHtml(value)
    view.setProperty('content', value)
    scroll.setValue(scroll.maximum() if following else position)


class SettingsDialog(W.QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle('AgentLink · 节点设置')
        self.setMinimumWidth(710)
        self.original = settings
        outer = W.QVBoxLayout(self)
        help_text = W.QLabel('两台电脑使用同一共享目录，分别选择 A 和 B。每台电脑保留自己的登录和工具配置。')
        help_text.setWordWrap(True)
        outer.addWidget(help_text)
        form = W.QFormLayout()
        form.setVerticalSpacing(12)
        outer.addLayout(form)
        self.role = W.QComboBox(); self.role.addItems(['A', 'B']); self.role.setCurrentText(settings.role)
        form.addRow('本机节点', self.role)
        self.share = self.path_field(form, '共享目录', settings.shared_root, True)
        self.codex = self.path_field(form, 'Codex 程序', settings.codex, False)
        self.model = W.QLineEdit(settings.model); form.addRow('模型', self.model)
        self.effort = W.QComboBox(); self.effort.addItems(['low', 'medium', 'high', 'xhigh'])
        self.effort.setCurrentText(settings.effort); form.addRow('推理强度', self.effort)
        form.addRow('任务权限', W.QLabel('目录在对话中提供；澄清只读，执行遵循已确认任务。\nB 源码只读。外部应用与权限升级关闭。'))
        wait_note = W.QLabel('不限制总时长；执行中持续等待并同步活动状态。\n长时间无新事件会提示，可随时手动停止。')
        wait_note.setWordWrap(True); form.addRow('任务等待', wait_note)
        self.auto = W.QCheckBox('打开程序时自动连接节点'); self.auto.setChecked(settings.auto_connect)
        form.addRow('', self.auto)
        note = W.QLabel('更改设置会断开节点，保存后重新连接生效。旧版目录设置保留用于历史兼容。')
        note.setObjectName('muted'); note.setWordWrap(True); outer.addWidget(note)
        actions = W.QDialogButtonBox(W.QDialogButtonBox.Save | W.QDialogButtonBox.Cancel)
        actions.button(W.QDialogButtonBox.Save).setText('保存设置')
        actions.button(W.QDialogButtonBox.Cancel).setText('取消')
        actions.accepted.connect(self.accept); actions.rejected.connect(self.reject); outer.addWidget(actions)

    def path_field(self, form, label, text, folder):
        layout = W.QHBoxLayout(); field = W.QLineEdit(text)
        def choose():
            value = W.QFileDialog.getExistingDirectory(self, label, field.text()) if folder else W.QFileDialog.getOpenFileName(self, label, field.text(), 'Codex (codex.exe);;程序 (*.exe)')[0]
            if value:
                field.setText(value)
        layout.addWidget(field); layout.addWidget(button('选择', choose))
        form.addRow(label, layout)
        return field

    def result_settings(self):
        value = Settings(role=self.role.currentText(), shared_root=self.share.text().strip(),
            codex=self.codex.text().strip(), model=self.model.text().strip(), effort=self.effort.currentText(),
            workspace=self.original.workspace, sandbox=self.original.sandbox, tools=self.original.tools,
            timeout_seconds=0, auto_connect=self.auto.isChecked())
        value.validate()
        if not value.model:
            raise ValueError('请填写模型名称。')
        return value

    def accept(self):
        try:
            self.result_settings()
        except ValueError as error:
            W.QMessageBox.warning(self, '请检查设置', str(error)); return
        super().accept()


class Bridge(QtCore.QObject):
    event = QtCore.pyqtSignal(str, object)


