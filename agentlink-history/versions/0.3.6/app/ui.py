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
        self.workspace = self.path_field(form, '本机项目目录', settings.workspace, True)
        self.workspace.setPlaceholderText('留空使用独立的 AgentLink 工作目录')
        self.model = W.QLineEdit(settings.model); form.addRow('模型', self.model)
        self.effort = W.QComboBox(); self.effort.addItems(['low', 'medium', 'high', 'xhigh'])
        self.effort.setCurrentText(settings.effort); form.addRow('推理强度', self.effort)
        self.sandbox = W.QComboBox()
        self.sandbox.addItem('只读沙盒（默认）', 'read-only')
        self.sandbox.addItem('允许读写本机项目', 'workspace-write')
        self.sandbox.setCurrentIndex(max(0, self.sandbox.findData(settings.sandbox)))
        form.addRow('本机权限', self.sandbox)
        self.tools = W.QComboBox()
        self.tools.addItem('沿用本机 Codex 技能和插件配置', 'configured')
        self.tools.addItem('文字讨论，不主动使用工具', 'discussion')
        self.tools.setCurrentIndex(max(0, self.tools.findData(settings.tools)))
        form.addRow('技能和插件', self.tools)
        self.timeout = W.QSpinBox(); self.timeout.setRange(1, 60); self.timeout.setSuffix(' 分钟')
        self.timeout.setValue(max(1, settings.timeout_seconds // 60)); form.addRow('单次调用超时', self.timeout)
        self.auto = W.QCheckBox('打开程序时自动连接节点'); self.auto.setChecked(settings.auto_connect)
        form.addRow('', self.auto)
        note = W.QLabel('只读沙盒限制本地写入；它不等于禁用所有外部工具。额外权限请求不会自动批准。\n更改设置会断开节点，保存后重新连接生效。')
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
            workspace=self.workspace.text().strip(), sandbox=self.sandbox.currentData(), tools=self.tools.currentData(),
            timeout_seconds=self.timeout.value() * 60, auto_connect=self.auto.isChecked())
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


class MainWindow(W.QMainWindow):
    def __init__(self, settings, data_dir, start_service=True, command_override=None):
        super().__init__()
        self.settings, self.data = settings, Path(data_dir)
        self.connected, self.active_id, self.peer = False, None, {}
        self.storage_warning = False
        self.selection_pending = None
        self.view_job_id = None
        self.snapshot = {'meta': {}, 'turns': [], 'live': []}
        self.capabilities = {}
        self.closing = False
        self.setWindowTitle('AgentLink · 双机协作')
        self.resize(1380, 940); self.setMinimumSize(1040, 740)
        self.setStyleSheet(STYLE)
        self.bridge = Bridge()
        self.bridge.event.connect(self.receive)
        self.service = NodeService(settings, self.data, self.bridge.event.emit, command_override)
        self.build()
        self.update_buttons()
        if start_service:
            self.service.start()
        self.close_timer = QtCore.QTimer(self); self.close_timer.timeout.connect(self.finish_close)

    def build(self):
        central = W.QWidget(); self.setCentralWidget(central)
        outer = W.QHBoxLayout(central); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)
        sidebar = W.QFrame(); sidebar.setObjectName('sidebar'); sidebar.setFixedWidth(242)
        side = W.QVBoxLayout(sidebar); side.setContentsMargins(19, 24, 19, 20); side.setSpacing(13)
        brand = W.QLabel('AgentLink'); brand.setObjectName('brand'); side.addWidget(brand)
        label = W.QLabel('两台电脑 · 一个讨论空间'); label.setObjectName('muted'); side.addWidget(label)
        side.addSpacing(14)
        self.new_button = button('＋  新建讨论', self.new_discussion, True); side.addWidget(self.new_button)
        side.addWidget(W.QLabel('讨论记录'))
        self.history_list = W.QListWidget(); self.history_list.itemClicked.connect(self.select_history)
        self.history_list.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        side.addWidget(self.history_list, 1)
        self.import_button = button('导入旧版讨论', self.import_discussion)
        side.addWidget(self.import_button)
        side.addWidget(button('打开本地记录', lambda: QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(self.data)))))
        foot = W.QLabel('PyQt5 · v' + __version__ + '\n账号与工具配置保留在各自电脑'); foot.setObjectName('muted'); side.addWidget(foot)
        outer.addWidget(sidebar)
        main = W.QVBoxLayout(); main.setContentsMargins(24, 22, 24, 18); main.setSpacing(12); outer.addLayout(main, 1)
        top = W.QHBoxLayout()
        title = W.QLabel('双机讨论'); title.setObjectName('title'); top.addWidget(title); top.addStretch()
        self.self_badge = W.QLabel('节点 ' + self.settings.role + ' · 离线'); self.self_badge.setObjectName('badge'); top.addWidget(self.self_badge)
        self.peer_badge = W.QLabel('另一台 · 未连接'); self.peer_badge.setObjectName('badge'); top.addWidget(self.peer_badge)
        self.connect_button = button('连接节点', self.toggle_connect); top.addWidget(self.connect_button)
        self.settings_button = button('设置', self.open_settings); top.addWidget(self.settings_button)
        main.addLayout(top)
        self.topic_label = W.QLabel('从一个议题开始，让另一台电脑参与评审。'); self.topic_label.setWordWrap(True)
        self.topic_label.setMaximumHeight(70); main.addWidget(self.topic_label)
        self.notice = W.QLabel(''); self.notice.setObjectName('notice'); self.notice.setWordWrap(True); self.notice.hide(); main.addWidget(self.notice)
        self.progress = W.QProgressBar(); self.progress.setTextVisible(False); self.progress.setRange(0, 3); self.progress.setValue(0); main.addWidget(self.progress)
        self.tabs = W.QTabWidget(); main.addWidget(self.tabs, 1)
        conversation = W.QWidget(); split_layout = W.QHBoxLayout(conversation); split_layout.setContentsMargins(0, 8, 0, 0)
        self.panes = {}
        for role in ('A', 'B'):
            column = W.QVBoxLayout(); heading = W.QLabel('节点 ' + role); heading.setStyleSheet('font-weight: 650; color: #315174;')
            column.addWidget(heading); self.panes[role] = browser(); column.addWidget(self.panes[role]); split_layout.addLayout(column, 1)
        self.tabs.addTab(conversation, '讨论现场')
        self.final_view = browser(); self.tabs.addTab(self.final_view, '最终答复')
        self.summary_view = browser(); self.tabs.addTab(self.summary_view, '公开思考摘要')
        self.tools_view = browser(); self.tabs.addTab(self.tools_view, '工具事件')
        self.context_view = browser(); self.tabs.addTab(self.context_view, '承接上下文')
        self.cap_view = browser(); self.tabs.addTab(self.cap_view, '节点能力')
        self.activity = W.QPlainTextEdit(); self.activity.setReadOnly(True); self.activity.setMaximumBlockCount(1000)
        self.tabs.addTab(self.activity, '运行日志')
        row = W.QHBoxLayout()
        self.state_label = W.QLabel('新讨论'); self.state_label.setObjectName('muted'); row.addWidget(self.state_label); row.addStretch()
        row.addWidget(button('复制答复', self.copy_final)); row.addWidget(button('导出记录', self.export_report))
        row.addWidget(button('实施交接', self.export_handoff)); row.addWidget(button('Codex 任务 ID', self.copy_session))
        main.addLayout(row)
        self.context_hint = W.QLabel('新建独立讨论，不携带其他记录。'); self.context_hint.setObjectName('muted')
        self.context_hint.setWordWrap(True); main.addWidget(self.context_hint)
        self.prompt = W.QPlainTextEdit(); self.prompt.setPlaceholderText('输入议题或补充要求…\nEnter 换行，Ctrl + Enter 发起讨论。'); self.prompt.setFixedHeight(96)
        main.addWidget(self.prompt)
        controls = W.QHBoxLayout()
        controls.addWidget(W.QLabel('评审轮数'))
        self.rounds = W.QSpinBox(); self.rounds.setRange(1, 8); self.rounds.setValue(1); self.rounds.setFixedWidth(72); controls.addWidget(self.rounds)
        self.call_count = W.QLabel('3 次模型调用'); self.call_count.setObjectName('muted'); controls.addWidget(self.call_count)
        self.rounds.valueChanged.connect(lambda n: self.call_count.setText(str(1 + 2*n) + ' 次模型调用'))
        controls.addStretch()
        self.note_button = button('补充到下一轮', self.add_note); controls.addWidget(self.note_button)
        self.pause_button = button('暂停', self.toggle_pause); controls.addWidget(self.pause_button)
        self.stop_button = button('停止', lambda: self.service.command('cancel')); self.stop_button.setObjectName('danger'); controls.addWidget(self.stop_button)
        self.start_button = button('发起讨论', self.start_discussion, True); controls.addWidget(self.start_button)
        main.addLayout(controls)
        self.statusBar().showMessage('账号使用本机 Codex 登录 · 默认只读 · 双方均可发起和控制')
        shortcut = W.QShortcut(QtGui.QKeySequence('Ctrl+Return'), self); shortcut.activated.connect(self.start_discussion)
        self.render()

    def toggle_connect(self):
        self.notice.hide()
        if not self.settings.codex and not self.connected:
            self.open_settings(); return
        self.connect_button.setEnabled(False)
        self.service.command('disconnect' if self.connected else 'connect')

    def open_settings(self):
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec_() == W.QDialog.Accepted:
            self.settings = dialog.result_settings()
            self.service.command('configure', settings=asdict(self.settings))

    def new_discussion(self):
        if self.active_id:
            return
        self.snapshot = {'meta': {}, 'turns': [], 'live': []}
        self.selection_pending = None
        self.view_job_id = None
        self.service.command('select', job_id=None)
        self.history_list.clearSelection(); self.prompt.clear(); self.notice.hide()
        self.render(); self.prompt.setFocus(); self.tabs.setCurrentIndex(0)

    def start_discussion(self):
        if not self.start_button.isEnabled():
            return
        topic = self.prompt.toPlainText().strip()
        if not topic:
            self.prompt.setFocus(); return
        self.notice.hide()
        self.start_button.setEnabled(False)
        parent = self.snapshot.get('meta', {}).get('id')
        self.service.command('start', topic=topic, rounds=self.rounds.value(), parent_job_id=parent)

    def add_note(self):
        text = self.prompt.toPlainText().strip()
        if text:
            self.service.command('note', text=text); self.prompt.clear()

    def toggle_pause(self):
        self.service.command('resume' if self.snapshot.get('control', {}).get('paused') else 'pause')

    def select_history(self, item):
        self.selection_pending = item.data(QtCore.Qt.UserRole)
        self.view_job_id = self.selection_pending
        self.update_buttons()
        self.service.command('select', job_id=self.selection_pending)

    def import_discussion(self):
        base = Path(os.environ.get('LOCALAPPDATA', '')) / 'AgentLinkApp' / 'runs'
        path = W.QFileDialog.getOpenFileName(self, '选择旧版 discussion.txt', str(base), '讨论记录 (discussion.txt *.txt)')[0]
        if path:
            self.view_job_id = 'legacy:' + str(Path(path))
            self.service.command('import', path=path)

    def receive(self, kind, value):
        if kind == 'status':
            self.connected, self.active_id = value['connected'], value.get('active')
            self.self_badge.setText('节点 ' + value['role'] + ' · ' + STATUS.get(value['status'], value['status']))
            self.connect_button.setText('断开' if self.connected else '连接节点')
            self.statusBar().showMessage(value.get('text') or STATUS.get(value['status'], ''))
        elif kind == 'peer':
            self.peer = value
            self.peer_badge.setText('节点 ' + ('B' if self.settings.role == 'A' else 'A') + (' · 在线' if value.get('online') else ' · 离线'))
            self.render_capabilities()
        elif kind == 'new_job':
            self.selection_pending = None
            self.view_job_id = value['id']
            self.active_id = value['id']
            if self.snapshot.get('meta', {}).get('id') != value['id']:
                self.snapshot = {'meta': value, 'turns': [], 'live': [], 'status': 'running'}
                self.prompt.clear(); self.notice.hide(); self.tabs.setCurrentIndex(0); self.render()
        elif kind == 'discussion':
            if value.get('meta', {}).get('id') != self.view_job_id:
                return
            if self.selection_pending and value.get('meta', {}).get('id') != self.selection_pending:
                return
            self.selection_pending = None
            self.snapshot = value; self.render()
        elif kind == 'live':
            if value.get('job_id') == self.snapshot.get('meta', {}).get('id'):
                turns = self.snapshot.get('turns', [])
                if not any(t['step'] == value['step'] for t in turns):
                    live = [t for t in self.snapshot.get('live', []) if t['role'] != value['role']]
                    self.snapshot['live'] = live + [value]
                    self.render()
        elif kind == 'history':
            selected = self.snapshot.get('meta', {}).get('id')
            self.history_list.clear()
            for entry in value:
                date = datetime.fromtimestamp(entry['created']).strftime('%m/%d %H:%M')
                topic = entry['topic'].replace('\n', ' ')
                short = self.history_list.fontMetrics().elidedText(topic, QtCore.Qt.ElideRight, 174)
                item = W.QListWidgetItem(short + '\n' + date + '  ·  ' + STATUS.get(entry['status'], entry['status']))
                item.setData(QtCore.Qt.UserRole, entry['id']); item.setToolTip(entry['topic']); self.history_list.addItem(item)
                item.setSelected(entry['id'] == selected)
        elif kind == 'activity':
            stamp = datetime.fromtimestamp(value['time']).strftime('%H:%M:%S')
            self.activity.appendPlainText(stamp + '  ' + value['text'])
        elif kind == 'error':
            self.notice.setProperty('error_kind', 'error')
            self.notice.setText(value['message']); self.notice.show()
        elif kind == 'storage_warning':
            self.storage_warning = True
            self.notice.setProperty('error_kind', 'storage')
            self.notice.setText(value['message']); self.notice.show()
        elif kind == 'storage_recovered':
            self.storage_warning = False
            if self.notice.property('error_kind') == 'storage':
                self.notice.hide()
            self.statusBar().showMessage('共享文件读写已恢复。')
        elif kind == 'capabilities':
            self.capabilities = value; self.render_capabilities()
        elif kind == 'configured':
            self.settings = Settings(**value)
            self.self_badge.setText('节点 ' + self.settings.role + ' · 离线')
            self.statusBar().showMessage('设置已保存，点击“连接节点”生效。')
        self.update_buttons()

    def update_buttons(self):
        busy = bool(self.active_id)
        meta = self.snapshot.get('meta', {})
        selected = bool(meta.get('id'))
        can_continue = (self.snapshot.get('status') == 'completed'
                        and not meta.get('id', '').startswith('legacy:'))
        self.start_button.setEnabled(self.connected and not self.storage_warning and not busy
                                    and not self.selection_pending and (not selected or can_continue)
                                    and not (self.peer.get('online') and self.peer.get('job_id')))
        self.start_button.setText('继续讨论' if selected else '发起讨论')
        if busy:
            ref = meta.get('context')
            self.context_hint.setText('本场已携带 %s 场历史，详情见“承接上下文”。' % ref['discussion_count']
                                     if ref else '本场为独立讨论。运行中的新要求请点“补充到下一轮”。')
        elif self.selection_pending:
            self.context_hint.setText('正在读取所选历史，读取完成后才能继续。')
        elif selected and can_continue:
            self.context_hint.setText('将继续所选讨论：' + meta.get('topic', '').replace('\n', ' ')[:90]
                                     + '。双方会收到历史议题、补充要求和完整答复；无关任务请点“新建讨论”。')
        elif selected:
            self.context_hint.setText('仅已完成的本版记录可自动续接。请选择已完成记录，或点“新建讨论”并粘贴需要的材料。')
        else:
            self.context_hint.setText('新建独立讨论，不携带其他记录。需承接历史，请先在左侧选择一场已完成讨论。')
        self.prompt.setPlaceholderText('输入下一步要求，例如：按上轮测试集开始测试，5 次调用后报告结果。\nCtrl + Enter 继续讨论。'
                                       if selected and can_continue else '输入议题或补充要求…\nEnter 换行，Ctrl + Enter 发起讨论。')
        self.new_button.setEnabled(not busy)
        self.history_list.setEnabled(not busy)
        self.import_button.setEnabled(not busy)
        self.settings_button.setEnabled(not busy)
        self.connect_button.setEnabled(not busy)
        self.rounds.setEnabled(not busy)
        for widget in (self.note_button, self.pause_button, self.stop_button):
            widget.setEnabled(self.connected and busy)
        self.pause_button.setText('继续' if self.snapshot.get('control', {}).get('paused') else '暂停')

    def render(self):
        meta = self.snapshot.get('meta', {})
        self.topic_label.setText(meta.get('topic', '从一个议题开始，让另一台电脑参与评审。'))
        turns = sorted(self.snapshot.get('turns', []) + self.snapshot.get('live', []), key=lambda t: t.get('index', 0))
        for role, pane in self.panes.items():
            cards = []
            for turn in turns:
                if turn['role'] != role:
                    continue
                body = turn.get('blocks') or [{'text': turn.get('answer', '')}]
                title = turn_title(turn.get('index', 0)) + ' · ' + STATUS.get(turn.get('status'), '生成中')
                cards.append('<p style="color:#3263a1;font-weight:600">' + title + '</p>' +
                             '<br><br>'.join(text_html(b.get('text', '')) for b in body) + '<hr style="color:#e2e8f1">')
            set_html(pane, ''.join(cards) or '<p style="color:#8a97aa">等待节点 ' + role + ' 的内容…</p>')
        status = self.snapshot.get('status', 'incomplete')
        complete = self.snapshot.get('turns', [])
        final = complete[-1].get('answer', '') if complete and status == 'completed' else ''
        set_html(self.final_view, text_html(final) if final else '<p style="color:#8a97aa">讨论完成后，发起方的最终答复会显示在这里。</p>')
        summaries = ['<p style="color:#64748b">这里只显示接口提供的公开思考摘要；有些模型或调用不会返回摘要。</p>']
        tool_cards = []
        for turn in turns:
            heading = turn['role'] + ' · ' + turn_title(turn.get('index', 0))
            if turn.get('summary'):
                summaries.append('<h4>' + heading + '</h4>' + text_html(turn['summary']))
            for tool in turn.get('tools', []):
                tool_cards.append('<h4>' + heading + ' · ' + text_html(tool.get('kind', '')) + '</h4><p>' +
                    text_html(tool.get('name', '')) + ' · ' + text_html(tool.get('status', '')) + '</p><p>' + text_html(tool.get('output', '')) + '</p>')
        set_html(self.summary_view, ''.join(summaries))
        set_html(self.tools_view, ''.join(tool_cards) or '<p style="color:#8a97aa">工具调用和执行结果将按轮次出现在这里。</p>')
        context = self.snapshot.get('context')
        ref = meta.get('context')
        if context and ref:
            self.context_view.setToolTip('来源：' + ref['parent_job_id'] + '\nSHA-256：' + ref['sha256'])
            set_html(self.context_view, '<p>双方收到的历史内容（共 ' + str(ref['discussion_count'])
                     + ' 场已完成讨论）</p>' + text_html(readable_context(context)))
        else:
            self.context_view.setToolTip('')
            set_html(self.context_view, '<p style="color:#8a97aa">本场没有承接历史。选中已完成讨论并点“继续讨论”，新场次会保存双方共同收到的历史。</p>')
        count, total = len(complete), 1 + 2 * meta.get('rounds', 1)
        self.progress.setRange(0, total); self.progress.setValue(count)
        self.state_label.setText((STATUS.get(status, status) + ' · ' + str(count) + ' / ' + str(total) + ' 次调用') if meta else '新讨论')
        self.update_buttons()

    def render_capabilities(self):
        parts = ['<p>能力清单来自各台 Codex 的实际配置。能否执行还取决于授权、登录状态和项目环境。</p>']
        for role, cap in ((self.settings.role, self.capabilities), ('B' if self.settings.role == 'A' else 'A', self.peer.get('capabilities', {}))):
            parts.append('<h3>节点 ' + role + '</h3>')
            parts.append('<p>技能：' + text_html('、'.join(s['name'] for s in cap.get('skills', []) if s.get('enabled', True)) or '尚未读取或为空') + '</p>')
            parts.append('<p>MCP / 插件服务：' + text_html('；'.join(s['name'] + '（' + str(s.get('tool_count', 0)) + ' 个工具）' for s in cap.get('mcp', [])) or '尚未读取或为空') + '</p>')
            if cap.get('errors'):
                parts.append('<p>读取提示：' + text_html('\n'.join(cap['errors'])) + '</p>')
        set_html(self.cap_view, ''.join(parts))

    def final_text(self):
        turns = self.snapshot.get('turns', [])
        return turns[-1].get('answer', '') if turns else ''

    def copy_final(self):
        if self.final_text():
            W.QApplication.clipboard().setText(self.final_text()); self.statusBar().showMessage('已复制最近一份答复。')

    def export_report(self):
        if not self.snapshot.get('meta'):
            return
        path = W.QFileDialog.getSaveFileName(self, '导出完整讨论', 'AgentLink-discussion.txt', '文本 (*.txt);;Markdown (*.md)')[0]
        if path:
            self.save_text(path, self.snapshot.get('report') or report_text(self.snapshot['meta'], self.snapshot.get('turns', []), self.snapshot.get('context')))

    def export_handoff(self):
        if not self.final_text():
            return
        path = W.QFileDialog.getSaveFileName(self, '保存实施交接文档', 'AgentLink-handoff.md', 'Markdown (*.md)')[0]
        if path:
            content = '# 实施交接\n\n## 用户议题\n\n' + self.snapshot['meta'].get('topic', '') + '\n\n## 最近方案\n\n' + self.final_text() + '\n\n## 执行前确认\n\n请先核对当前项目、验收条件和允许修改的范围，再开始实施。\n'
            self.save_text(path, content)

    def save_text(self, path, text):
        try:
            Path(path).write_text(text, encoding='utf-8-sig')
            self.statusBar().showMessage('已保存：' + path)
        except OSError as error:
            W.QMessageBox.warning(self, '保存失败', str(error))

    def copy_session(self):
        sessions = sorted({t.get('thread_id') for t in self.snapshot.get('turns', []) if t['role'] == self.settings.role and t.get('thread_id')})
        if not sessions:
            self.statusBar().showMessage('当前记录暂无本机 Codex 任务 ID。'); return
        W.QApplication.clipboard().setText('\n'.join(sessions))
        W.QMessageBox.information(self, '本机 Codex 任务', '已复制任务 ID：\n\n' + '\n'.join(sessions) + '\n\n可在本机 Codex 桌面端请助手打开这个任务。另一台电脑的任务仍保留在另一台；完整双机记录在 AgentLink 中查看。')

    def closeEvent(self, event):
        if not self.service.thread.is_alive():
            event.accept(); return
        event.ignore()
        if not self.closing:
            self.closing = True; self.service.stop()
            self.statusBar().showMessage('正在停止本机任务并退出…')
            self.centralWidget().setEnabled(False); self.close_timer.start(200)

    def finish_close(self):
        if not self.service.thread.is_alive():
            self.close_timer.stop(); self.close()
