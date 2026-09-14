"""Single timeline GUI for the confirmed 0.3.18 interaction contract."""
from dataclasses import asdict
from datetime import datetime
import json
from .interruption import recovery_hint
from pathlib import Path
from PyQt5 import QtCore, QtGui, QtWidgets as W
from . import __version__
from .engine import NodeService
from .storage import Settings, report_text, read_json
from .conversation import ID, FINISHED, brief_text, round_count
from .ui_support import STYLE, SettingsDialog, Bridge, button, browser, text_html, set_html

LABELS = {'clarifying':'A 正在澄清', 'awaiting_confirmation':'等待确认', 'waiting_peer':'等待 B',
          'working':'协作中', 'paused':'已暂停', 'interrupted':'中断，等待恢复', 'chat_interrupted':'对话中断，等待恢复',
          'context_blocked':'上下文待处理，未发送',
          'conflict':'要求冲突，等待裁决', 'needs_user_decision':'待用户裁决', 'completed':'已完成',
          'cancelled':'已停止', 'idle':'就绪', 'offline':'离线', 'connecting':'连接中', 'running':'执行中',
          'failed':'失败', 'incomplete':'未完成','cleanup_pending':'清理待处理'}


class MainWindow(W.QMainWindow):
    def __init__(self, settings, data_dir, start_service=True, command_override=None):
        super().__init__()
        self.settings, self.data = settings, Path(data_dir)
        self.connected=False; self.active_id=None; self.view_job_id=None; self.selection_pending=None
        self.peer={}; self.capabilities={}; self.execution={}; self.storage_warning=False; self.closing=False
        self.conversation=None; self.snapshot={'meta':{},'turns':[],'live':[]}
        self.input_pending=False
        self.issues_pending=False
        self.export_writer=None
        self.setWindowTitle('AgentLink '+__version__+' · 双机协作')
        self.resize(1380,940); self.setMinimumSize(1000,720); self.setStyleSheet(STYLE)
        self.bridge=Bridge();self.bridge.event.connect(self.receive)
        self.service=NodeService(settings,self.data,self.bridge.event.emit,command_override)
        self.build();self.update_buttons()
        if start_service:self.service.start()
        self.close_timer=QtCore.QTimer(self);self.close_timer.timeout.connect(self.finish_close)

    def build(self):
        central=W.QWidget();self.setCentralWidget(central)
        outer=W.QHBoxLayout(central);outer.setContentsMargins(0,0,0,0);outer.setSpacing(0)
        sidebar=W.QFrame();sidebar.setObjectName('sidebar');sidebar.setFixedWidth(242)
        side=W.QVBoxLayout(sidebar);side.setContentsMargins(19,24,19,20);side.setSpacing(13)
        brand=W.QLabel('AgentLink');brand.setObjectName('brand');side.addWidget(brand)
        subtitle=W.QLabel('A 负责执行 · B 独立审查');subtitle.setObjectName('muted');side.addWidget(subtitle)
        side.addSpacing(12)
        self.new_button=button('＋  新建对话',self.new_discussion,True);side.addWidget(self.new_button)
        side.addWidget(W.QLabel('任务历史'))
        self.history_list=W.QListWidget();self.history_list.itemClicked.connect(self.select_history)
        self.history_list.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff);side.addWidget(self.history_list,1)
        self.import_button=button('导入旧版记录',self.import_discussion);side.addWidget(self.import_button)
        side.addWidget(button('打开本地记录',lambda:QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(self.data)))))
        foot=W.QLabel('v'+__version__+'\n账号保留在各自电脑');foot.setObjectName('muted');side.addWidget(foot)
        outer.addWidget(sidebar)
        main=W.QVBoxLayout();main.setContentsMargins(24,22,24,18);main.setSpacing(12);outer.addLayout(main,1)
        top=W.QHBoxLayout();title=W.QLabel('双机协作');title.setObjectName('title');top.addWidget(title);top.addStretch()
        self.self_badge=W.QLabel('节点 '+self.settings.role+' · 离线');self.self_badge.setObjectName('badge');top.addWidget(self.self_badge)
        self.peer_badge=W.QLabel('另一台 · 未连接');self.peer_badge.setObjectName('badge');top.addWidget(self.peer_badge)
        self.connect_button=button('连接节点',self.toggle_connect);top.addWidget(self.connect_button)
        self.settings_button=button('设置',self.open_settings);top.addWidget(self.settings_button);main.addLayout(top)
        self.topic_label=W.QLabel('直接描述任务。涉及文件时，在消息里写明工作目录。');self.topic_label.setWordWrap(True)
        self.topic_label.setMaximumHeight(60);main.addWidget(self.topic_label)
        self.notice=W.QLabel();self.notice.setObjectName('notice');self.notice.setWordWrap(True);self.notice.hide();main.addWidget(self.notice)
        self.timeline=browser();main.addWidget(self.timeline,3)
        actions=W.QHBoxLayout()
        self.state_label=W.QLabel('新对话');self.state_label.setObjectName('muted');actions.addWidget(self.state_label);actions.addStretch()
        self.details_button=button('展开详情',self.toggle_details);actions.addWidget(self.details_button)
        actions.addWidget(button('复制答复',self.copy_final));actions.addWidget(button('导出记录',self.export_report))
        actions.addWidget(button('实施交接',self.export_handoff));actions.addWidget(button('Codex 任务 ID',self.copy_session));main.addLayout(actions)
        self.tabs=W.QTabWidget();self.tabs.setMaximumHeight(270);self.tabs.hide();main.addWidget(self.tabs,1)
        self.project_view=browser();self.tabs.addTab(self.project_view,'任务与快照')
        self.tools_view=browser();self.tabs.addTab(self.tools_view,'测试与工具')
        self.summary_view=browser();self.tabs.addTab(self.summary_view,'公开摘要')
        self.cap_view=browser();self.tabs.addTab(self.cap_view,'节点能力')
        self.activity=W.QPlainTextEdit();self.activity.setReadOnly(True);self.activity.setMaximumBlockCount(1000);self.tabs.addTab(self.activity,'运行日志')
        self.issues_button=button('更新后续问题状态',self.change_issue_status);self.tabs.setCornerWidget(self.issues_button)
        self.execution_label=W.QLabel();self.execution_label.setObjectName('muted');self.execution_label.setWordWrap(True);main.addWidget(self.execution_label)
        self.prompt=W.QPlainTextEdit();self.prompt.setFixedHeight(108)
        self.prompt.setPlaceholderText('输入任务、工作目录或给本节点的补充…\nEnter 换行，Ctrl + Enter 发送。');main.addWidget(self.prompt)
        row=W.QHBoxLayout();self.context_hint=W.QLabel();self.context_hint.setObjectName('muted');self.context_hint.setWordWrap(True);row.addWidget(self.context_hint,1)
        self.pause_button=button('暂停',self.toggle_pause);row.addWidget(self.pause_button)
        self.resume_button=button('恢复任务',lambda:self.control('resume'));row.addWidget(self.resume_button)
        self.stop_button=button('停止',lambda:self.control('cancel'));row.addWidget(self.stop_button)
        self.start_button=button('发送给 '+self.settings.role,self.start_discussion,True);row.addWidget(self.start_button);main.addLayout(row)
        shortcut=W.QShortcut(QtGui.QKeySequence('Ctrl+Return'),self);shortcut.activated.connect(self.start_discussion)
        self.statusBar().showMessage('本机输入交给本节点；只有 A 可以创建任务。')
        self.render()

    def toggle_details(self):
        self.tabs.setVisible(self.tabs.isHidden());self.details_button.setText('收起详情' if self.tabs.isVisible() else '展开详情')

    def toggle_connect(self):
        self.service.command('disconnect' if self.connected else 'connect')

    def open_settings(self):
        dialog=SettingsDialog(self.settings,self)
        if dialog.exec_()==W.QDialog.Accepted:self.service.command('configure',settings=asdict(dialog.result_settings()))

    def new_discussion(self):
        if self.settings.role!='A':return
        self.conversation=None;self.snapshot={'meta':{},'turns':[],'live':[]};self.view_job_id=None;self.selection_pending=None
        self.service.command('select',job_id=None);self.history_list.clearSelection();self.prompt.clear();self.notice.hide();self.render()

    def start_discussion(self):
        if not self.start_button.isEnabled():return
        text=self.prompt.toPlainText().strip()
        if not text:return
        self.service.command('chat',text=text,conversation_id=self.conversation['id'] if self.conversation else None)
        self.input_pending=True;self.update_buttons()

    def control(self,action):
        if self.conversation:
            self.service.command('conversation_control',conversation_id=self.conversation['id'],action=action)
            if action=='resume':self.input_pending=True;self.update_buttons()

    def toggle_pause(self):
        if self.conversation and self.conversation['phase']=='paused':
            self.service.command('chat',text='继续',conversation_id=self.conversation['id'])
        else:self.control('pause')

    def select_history(self,item):
        self.view_job_id=item.data(QtCore.Qt.UserRole);self.selection_pending=self.view_job_id
        self.service.command('select',job_id=self.view_job_id);self.update_buttons()

    def import_discussion(self):
        path=W.QFileDialog.getOpenFileName(self,'选择旧版讨论记录',str(self.data),'记录 (*.txt)')[0]
        if path:
            self.view_job_id='legacy:'+str(Path(path));self.service.command('import',path=path)

    def receive(self,kind,value):
        if kind=='status':
            self.connected=value['connected'];self.active_id=value.get('active')
            self.self_badge.setText('节点 '+value['role']+' · '+LABELS.get(value['status'],value['status']))
            self.connect_button.setText('断开' if self.connected else '连接节点');self.statusBar().showMessage(value.get('text',''))
        elif kind=='conversation_selected':
            self.view_job_id=value['id'];self.selection_pending=None
        elif kind=='input_accepted':
            self.input_pending=False
            if self.prompt.toPlainText().strip()==value['text']:self.prompt.clear()
        elif kind=='conversation':
            if value['id']==self.view_job_id:
                self.conversation=value;self.selection_pending=None;self.render()
        elif kind=='conversation_live':
            if self.conversation and value['id']==self.conversation['id']:
                self.conversation['live']=value['view'];self.render()
        elif kind=='discussion':
            if value['meta'].get('id')==self.view_job_id:
                self.conversation=None;self.snapshot=value;self.selection_pending=None;self.render()
        elif kind=='live':
            if self.conversation and value.get('job_id')==self.conversation.get('job'):
                self.conversation['formal_live']=[v for v in self.conversation.get('formal_live',[]) if v.get('role')!=value['role']]+[value];self.render()
        elif kind=='history':
            self.history_list.clear()
            for entry in value:
                text=entry['topic'].replace('\n',' ')
                short=self.history_list.fontMetrics().elidedText(text,QtCore.Qt.ElideRight,176)
                item=W.QListWidgetItem(short+'\n'+datetime.fromtimestamp(entry['created']).strftime('%m/%d %H:%M')+' · '+LABELS.get(entry['status'],entry['status']))
                item.setData(QtCore.Qt.UserRole,entry['id']);item.setToolTip(text);self.history_list.addItem(item);item.setSelected(entry['id']==self.view_job_id)
        elif kind=='peer':
            self.peer=value
            code=(value.get('online_problem') or {}).get('code')
            label='就绪' if value.get('online') else {'peer_probing':'确认中','peer_delayed':'响应延迟'}.get(code,'不可执行')
            self.peer_badge.setText('节点 '+self.service.peer_role+' · '+label)
            self.peer_badge.setToolTip((value.get('online_problem') or {}).get('reason',
                '最近心跳有效；开始步骤时还会核对本场实例与角色锁。'))
            self.render_capabilities()
        elif kind=='capabilities':self.capabilities=value;self.render_capabilities()
        elif kind=='issue_catalog':
            self.issues_pending=False
            project=(self.conversation or {}).get('job_meta',{}).get('project')
            if project and project['id']==value['project']:self.choose_issue_status(value['project'],value['issues'])
        elif kind=='export_result':
            if value['error']:W.QMessageBox.warning(self,'保存失败',value['error'])
            else:self.statusBar().showMessage('已保存：'+value['path'])
        elif kind=='detail_log_health':
            if value.get('write_failures') or value.get('dropped_events'):
                self.statusBar().showMessage('详细错误日志未完整保存；写入失败 '+str(value.get('write_failures',0))+' 次，丢弃 '+str(value.get('dropped_events',0))+' 条。原业务错误仍显示在界面。')
        elif kind=='diagnostic_health':
            if value.get('last_error_type') or value.get('dropped_events'):
                self.statusBar().showMessage('运行诊断有写入失败或丢失事件；任务状态请结合界面与原始记录核查。')
        elif kind=='activity':self.activity.appendPlainText(datetime.fromtimestamp(value['time']).strftime('%H:%M:%S')+' '+value['text'])
        elif kind in ('error','storage_warning'):
            self.input_pending=False
            self.issues_pending=False
            if kind=='storage_warning':self.storage_warning=True
            self.notice.setProperty('error_kind',kind);self.notice.setText(value['message']);self.notice.show()
        elif kind=='storage_recovered':
            self.storage_warning=False
            if self.notice.property('error_kind')=='storage_warning':self.notice.hide()
        elif kind=='configured':self.settings=Settings(**value)
        elif kind=='execution':
            self.execution[value['role']]=value
            self.render_execution()
        self.update_buttons()

    def update_buttons(self):
        c=self.conversation;legacy=bool(self.view_job_id and not ID.fullmatch(self.view_job_id))
        self.new_button.setEnabled(self.settings.role=='A' and not self.active_id and (not c or c['phase'] in FINISHED))
        self.start_button.setText('发送给 '+self.settings.role)
        self.start_button.setEnabled(self.connected and not self.storage_warning and not self.selection_pending and not self.input_pending and not legacy
                                    and (self.settings.role=='A' or bool(c and c.get('jobs'))))
        self.pause_button.setEnabled(bool(c and c['phase'] in ('working','paused','waiting_peer')))
        self.pause_button.setText('继续' if c and c['phase']=='paused' else '暂停')
        self.resume_button.setVisible(bool(c and c['phase'] in ('paused','interrupted','chat_interrupted','context_blocked')))
        self.resume_button.setEnabled(bool(c and not c.get('user_stopped') and self.connected
            and not self.storage_warning and not self.active_id and not self.input_pending
            and not getattr(self.service,'chat_active',None) and not getattr(self.service,'cleanup_error','')))
        self.stop_button.setEnabled(bool(c and c['phase'] not in FINISHED))
        self.settings_button.setEnabled(not self.active_id and not getattr(self.service,'chat_active',None))
        self.connect_button.setEnabled(not self.active_id and not getattr(self.service,'chat_active',None))
        self.issues_button.setEnabled(bool(c and c.get('job_meta',{}).get('project') and self.connected and not self.active_id and not self.issues_pending))
        hint='A 会先澄清任务，确认后再开始协作。' if self.settings.role=='A' else '请选择 A 发起的任务，消息会交给本机 B。'
        if legacy:hint='旧版记录可查看和导出；在 A 端新建对话并粘贴需要承接的材料。'
        elif c:
            hint={'awaiting_confirmation':'确认上方任务说明后，输入“开始”。',
                  'interrupted':'节点就绪不代表任务已恢复；核查已有结果后点击“恢复任务”，接回未完成步骤。',
                  'chat_interrupted':'对话请求未正常结束；输入“继续”明确恢复，不会自动重发。',
                  'context_blocked':'完整记录和未处理消息已保留；展开详情查看上下文，处理后输入“继续”。',
                  'waiting_peer':'任务说明已保存，等待 B 就绪。',
                  'conflict':'请在 A 端明确裁决冲突；后续步骤已暂停。'}.get(c['phase'],'给本节点的消息不计入对话轮数。')
        if c and c['phase']=='interrupted' and c.get('interruption'):
            hint = recovery_hint(c['interruption'])
        self.context_hint.setText(hint)

    def all_turns(self):
        if self.conversation:
            return [m['turn'] for m in self.conversation['messages'] if m.get('turn')]+self.conversation.get('formal_live',[])
        return self.snapshot.get('turns',[])+self.snapshot.get('live',[])

    def render(self):
        cards=[];c=self.conversation
        if c:
            self.topic_label.setText(c['topic'].splitlines()[0][:180])
            for m in c['messages']:
                who=('你 · 节点 '+m.get('origin','A')) if m['speaker']=='user' else m['speaker']
                label={'formal':'协作成果','brief':'任务说明','clarification':'澄清','supplement':'补充审查','relay':'转交建议','state':'状态'}.get(m['kind'],'')
                cards.append('<p style="color:#3263a1;font-weight:600">'+text_html(who+'  '+label)+'</p>'+text_html(m['text'])+'<hr>')
            lives=c.get('formal_live',[])+([c['live']] if c.get('live') else [])
            for v in lives:
                # Structured chat output is rendered after validation; avoid raw JSON flashing.
                text=v.get('answer','') if v.get('step','').startswith(('0','1')) else '正在整理问题和任务说明…'
                cards.append('<p>'+text_html(v.get('role','A')+' · 生成中')+'</p>'+text_html(text))
            count=c.get('completed_rounds',0);limit=(c.get('confirmed') or c.get('brief') or {}).get('round_limit',3)
            self.state_label.setText(LABELS.get(c['phase'],c['phase'])+' · 对话轮数 '+str(count)+' / '+str(limit))
            details=[]
            if c.get('confirmed'):details.append('已确认任务\n'+brief_text(c['confirmed']))
            if c.get('brief') and c['brief']!=c.get('confirmed'):details.append('待确认任务\n'+brief_text(c['brief']))
            details += ['澄清/补充请求尝试：'+str(c.get('chat_attempts',0)), '本任务执行请求尝试（含恢复）：'+str(c.get('formal_attempts',0)),
                        '执行记录：\n'+'\n'.join(c['jobs'])]
            if c.get('context_view'):
                details.append('本机发送上下文：工具记录已外置；文件索引可核对完整保存内容。字符和 JSON 字节是传输计数，不是 token。\n'+json.dumps(c['context_view'],ensure_ascii=False,indent=2))
            if c.get('context_error'):
                details.append('上下文阻塞详情（本步骤尚未发送）\n'+json.dumps(c['context_error'],ensure_ascii=False,indent=2))
            if c.get('context_recoveries'):
                details.append('上下文恢复记录\n'+json.dumps(c['context_recoveries'],ensure_ascii=False,indent=2))
            if c.get('interruption'):
                details.append('中断位置与恢复依据\n'+json.dumps(c['interruption'],ensure_ascii=False,indent=2))
            for t in self.all_turns():
                if t.get('delivery'):details.append('源码快照\n'+json.dumps(t['delivery'],ensure_ascii=False,indent=2)+'\nSHA-256：'+t['artifact']['manifest_sha256'])
            if c.get('error'):
                self.notice.setProperty('error_kind','conversation');self.notice.setText(c['error']);self.notice.show()
            elif self.notice.property('error_kind')=='conversation':self.notice.hide()
            set_html(self.project_view,text_html('\n\n'.join(details)))
        elif self.snapshot.get('meta'):
            self.topic_label.setText(self.snapshot['meta'].get('topic','历史记录'))
            for t in self.all_turns():cards.append('<h4>'+text_html(t.get('role',''))+'</h4>'+text_html(t.get('answer',''))+'<hr>')
            self.state_label.setText('旧版记录 · '+LABELS.get(self.snapshot.get('status','incomplete'),'历史'))
            details=json.dumps(self.snapshot.get('context') or self.snapshot.get('meta'),ensure_ascii=False,indent=2)
            if self.snapshot['meta'].get('mode')=='code':
                source=self.snapshot.get('project_issues_source')
                details += '\n'+('离线缓存，可能不是最新状态。' if source=='cache' else '本机尚未缓存问题清单。' if source=='unavailable' else '后续问题：')
                details += '\n'+json.dumps(self.snapshot.get('project_issues',[]),ensure_ascii=False,indent=2)
            set_html(self.project_view,text_html(details))
        else:
            self.topic_label.setText('直接描述任务。涉及文件时，在消息里写明工作目录。')
            self.state_label.setText('新对话 · 对话轮数 0')
        set_html(self.timeline,''.join(cards) or '<h3>从一个问题开始</h3><p>A 先与你明确目标，B 随后独立审查。</p><p>例如：工作目录是 C:\\Work\\Demo。请分析恢复后丢失消息的原因，先不要改代码。</p>')
        tools=[];summaries=[]
        for t in self.all_turns():
            if t.get('summary'):summaries.append(t['role']+'：'+t['summary'])
            for tool in t.get('tools',[]):tools.append(t['role']+'：'+json.dumps(tool,ensure_ascii=False,indent=2))
        set_html(self.tools_view,text_html('\n\n'.join(tools) or '暂无工具事件。'))
        set_html(self.summary_view,text_html('\n\n'.join(summaries) or '仅显示接口返回的公开摘要；当前暂无摘要。'))
        self.update_buttons()

    def render_capabilities(self):
        value={'本机':self.capabilities,'对端':self.peer.get('capabilities',{})}
        set_html(self.cap_view,text_html(json.dumps(value,ensure_ascii=False,indent=2)))

    def render_execution(self):
        job=(self.conversation or {}).get('job') or self.snapshot.get('meta',{}).get('id')
        lines=[]
        for role,node in self.execution.items():
            info=node.get('execution') or {}
            if not info or (node.get('job_id') and job and node['job_id']!=job):continue
            state={'tool_running':'工具执行中','quiet':'进程仍在，暂时无新事件','process_exited':'进程已退出'}.get(info.get('phase'),'执行中')
            lines.append('节点 '+role+' · '+state+' · 已运行 '+str(int(info.get('elapsed_seconds',0)))+' 秒')
        self.execution_label.setText('\n'.join(lines))

    def final_text(self):
        if self.conversation:
            return next((m['text'] for m in reversed(self.conversation['messages']) if m['speaker'] in ('A','B')),'')
        return self.snapshot.get('turns',[{}])[-1].get('answer','') if self.snapshot.get('turns') else ''

    def copy_final(self):
        if self.final_text():W.QApplication.clipboard().setText(self.final_text());self.statusBar().showMessage('已复制最近答复')

    def report(self):
        if not self.conversation:
            turns=list(self.snapshot.get('turns',[]))
            for t in self.snapshot.get('live',[]):
                if not any(saved['step']==t['step'] for saved in turns):
                    turns.append(dict(t,answer='【未完成输出，仅作恢复线索】\n'+t.get('answer','')))
            return report_text(self.snapshot['meta'],turns,self.snapshot.get('context'))
        c=self.conversation
        lines=['# AgentLink 对话记录',c['topic'],'状态：'+LABELS.get(c['phase'],c['phase']),'对话轮数：'+str(c['completed_rounds'])]
        for m in c['messages']:lines += ['', '## '+m['speaker']+('（用户位于 '+m['origin']+'）' if m.get('origin') else ''),m['text']]
        if c.get('live'):lines+=['','未完成输出（仅作恢复线索）',c['live'].get('answer','')]
        for t in c.get('formal_live',[]):lines+=['','未完成输出（仅作恢复线索）',t.get('answer','')]
        lines+=['','执行记录：',*c['jobs']]
        return '\n'.join(lines)

    def export_report(self):
        if not self.view_job_id and not self.snapshot.get('meta'):return
        path=W.QFileDialog.getSaveFileName(self,'导出完整记录','AgentLink-discussion.md','Markdown (*.md);;文本 (*.txt)')[0]
        if path:self.save_text(path,self.report())

    def export_handoff(self):
        if not self.view_job_id:return
        path=W.QFileDialog.getSaveFileName(self,'导出实施交接','AgentLink-handoff.md','Markdown (*.md)')[0]
        if path:self.save_text(path,self.report())

    def save_text(self,path,text):
        from .file_output import ExportWriter
        if self.export_writer is None:self.export_writer=ExportWriter(self.bridge.event.emit)
        if self.export_writer.submit(path,text):self.statusBar().showMessage('正在保存：'+path)
        else:W.QMessageBox.warning(self,'保存未排队','已有导出正在保存，请稍后重试。')

    def copy_session(self):
        records=self.all_turns()
        if self.conversation:records+=self.conversation['attempts']
        sessions=sorted({t['thread_id'] for t in records if t.get('role')==self.settings.role and t.get('thread_id')})
        if sessions:W.QApplication.clipboard().setText('\n'.join(sessions));self.statusBar().showMessage('已复制本机 Codex 任务 ID')
        else:self.statusBar().showMessage('当前暂无本机 Codex 任务 ID')

    def change_issue_status(self):
        project=(self.conversation or {}).get('job_meta',{}).get('project')
        if not project:return
        self.issues_pending=True;self.update_buttons()
        self.service.command('issue_catalog',project=project['id'])
        self.statusBar().showMessage('正在读取后续问题…')

    def choose_issue_status(self,project,issues):
        if not issues:W.QMessageBox.information(self,'后续问题','暂无已记录问题');return
        choice,ok=W.QInputDialog.getItem(self,'后续问题','选择问题',[v['description'] for v in issues],0,False)
        if not ok:return
        status,ok=W.QInputDialog.getItem(self,'问题状态','状态',['open','resolved','deferred'],0,False)
        if ok:self.service.command('issue_status',project=project,issue_id=next(i['id'] for i in issues if i['description']==choice),status=status)

    def closeEvent(self,event):
        if self.export_writer is not None:
            self.export_writer.close()
            if self.export_writer.thread.is_alive():
                event.ignore();self.statusBar().showMessage('正在完成已确认的导出，请稍候。')
                QtCore.QTimer.singleShot(200,self.close);return
        if not self.service.thread.is_alive():event.accept();return
        event.ignore()
        if not self.closing:
            self.closing=True;self.service.stop();self.centralWidget().setEnabled(False);self.close_timer.start(200)

    def finish_close(self):
        if not self.service.thread.is_alive():self.close_timer.stop();self.close()
