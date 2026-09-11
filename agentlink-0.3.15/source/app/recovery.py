"""Explicit project recovery creates a linked job; terminal evidence remains immutable."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import socket
from . import artifacts
from .storage import JOB_PATTERN, read_json, now
from .node_input import FEATURE


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode('utf-8')).hexdigest()


class ProjectRecovery:
    def prepare_recovery(self, parent_id, target, text, project):
        if not isinstance(parent_id,str) or not JOB_PATTERN.fullmatch(parent_id):
            raise ValueError('恢复场次编号无效')
        parent=self.box.get(parent_id,'meta.json',{})
        self.box.validate_meta(parent,parent_id)
        state=self.box.get(parent_id,'state.json',{})
        if state.get('status') != 'failed' or parent.get('mode') != 'code' or parent.get('project',{}).get('id') != project:
            raise ValueError('仅支持恢复同一项目的失败场次；停止和完成场次不会复活。')
        if self.box.get(parent_id,'recovery-child.json'):
            raise ValueError('此失败场次已有恢复记录；请在历史中选择最新的恢复场次。')
        peer=read_json(self.box.root/'nodes'/(self.peer_role+'.json'),{})
        if FEATURE not in peer.get('features',[]):
            raise ValueError('恢复要求双方均使用 0.3.15。')
        turns=[]
        for index in range(parent['budget']):
            role='B' if index%2 else 'A'
            turn=self.box.get(parent_id,f'turn-{index:03d}-{role}.json')
            if not turn:break
            self.box.validate_turn(turn,parent_id,index,role);turns.append(turn)
        index=len(turns);role='B' if index%2 else 'A'
        if index>=parent['budget'] or role!=target:
            raise ValueError('未完成步骤属于节点 '+role+'；请选择该节点恢复。')
        request=self.box.get(parent_id,f'request-{index:03d}-{role}.json')
        if not request or request.get('job_id')!=parent_id or request.get('index')!=index:
            raise ValueError('缺少未完成步骤的请求记录，不能推测恢复位置。')
        if not isinstance(text,str) or not 1<=len(text.strip())<=12000:
            raise ValueError('请输入明确的恢复指令（1 到 12000 字符）。')
        inherited=parent.get('recovery',{}).get('prior_attempts',0)+len(list(self.box.job(parent_id).glob('call-*.json')))
        return {'parent_id':parent_id,'parent_digest':digest(parent),'index':index,'target':target,
                'text':text.strip(),'phase':request['phase'],'prior_attempts':inherited,'turns':turns,'rounds':parent['rounds']}

    def import_recovery(self, plan):
        parent=plan['parent_id'];job=self.active['id']
        for turn in plan['turns']:
            receipt=turn.get('artifact')
            if receipt:
                sha=receipt.get('manifest_sha256','')
                if not re.fullmatch('[a-f0-9]{64}',sha):raise ValueError('恢复快照标识无效')
                source=self.box.job(parent)/'artifacts'/sha
                manifest=read_json(source/'manifest.json',limit=artifacts.MAX_MANIFEST)
                artifacts.validate_manifest(manifest,receipt)
                dest=self.box.job(job)/'artifacts'/sha;dest.mkdir(parents=True,exist_ok=True)
                for filename in ('manifest.json','source.zip','ready.json'):
                    shutil.copyfile(source/filename,dest/filename)
            imported=dict(turn,job_id=job,inherited_from={'job_id':parent,'step':turn['step'],'sha256':digest(turn)})
            self.box.put(job,'turn-'+turn['step']+'.json',imported)
        old_control=self.box.get(parent,'control.json',{})
        self.box.put(job,'control.json',{'paused':False,'cancelled':False,'notes':old_control.get('notes',[])})
        self.box.put(parent,'recovery-child.json',{'job_id':job,'created':now(),'target':plan['target'],'index':plan['index']})

    def recovery_scope(self, request, binding):
        recovery=self.active.get('recovery')
        if not recovery or recovery['index']!=request['index']:
            return None
        parent=recovery['parent_id'];step=f"{request['index']:03d}-{self.settings.role}"
        # Only this machine's saved scope can supply local paths, never a peer message.
        scope=read_json(self.data/'runs'/parent/(step+'-scope.json'))
        if not scope or scope.get('phase')!=request['phase']:
            raise ValueError('本机缺少原步骤范围记录；不能安全恢复原会话。')
        source=Path(scope['source']).resolve();scratch=Path(scope['scratch']).resolve()
        scratch_root=(self.data/'project-tests'/binding['id']).resolve()
        bound=Path(binding['directory']).resolve()
        if not scratch.is_relative_to(scratch_root) or scratch==scratch_root:
            raise ValueError('恢复测试目录不在当前项目范围内')
        if (self.settings.role=='A' and source!=bound) or (self.settings.role=='B' and not source.is_relative_to(bound)):
            raise ValueError('恢复源目录与当前项目绑定不一致')
        if scope.get('snapshot')!=request.get('artifact'):
            raise ValueError('恢复快照与原步骤不一致')
        ledger=self.box.get(parent,'call-'+step+'.json',{})
        session=self.box.get(parent,'session-'+self.settings.role+'.json',{})
        thread=ledger.get('thread_id')
        if thread and (session.get('thread_id')!=thread or session.get('host')!=socket.gethostname()):
            raise ValueError('原 Codex 会话不属于当前电脑，不能冒充恢复。')
        return dict(source=source,scratch=scratch,thread=thread,text=recovery['text'])
