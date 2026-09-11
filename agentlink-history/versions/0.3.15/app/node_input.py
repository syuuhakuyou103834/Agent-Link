"""Audited node-specific input. Never retry a steering request after uncertain delivery."""
import re
import time
from .storage import read_json, now

FEATURE = 'node-intervention-v1'


class NodeInput:
    def send_node_input(self, job, target, text, message_id):
        if target not in ('A', 'B') or not isinstance(text, str) or not 1 <= len(text.strip()) <= 12000:
            raise ValueError('请选择 A/B，输入 1 到 12000 字符。')
        if not re.fullmatch('[a-f0-9]{32}', message_id):
            raise ValueError('定向消息编号无效')
        meta = self.box.get(job, 'meta.json', {})
        if target != self.settings.role:
            peer = read_json(self.box.root / 'nodes' / (self.peer_role + '.json'), {})
            if FEATURE not in peer.get('features', []):
                raise ValueError('定向输入要求双方更新到 0.3.15。')
        with self.box.lifecycle(job):
            self.box.ensure_open(job)
            filename = 'input-' + message_id + '.json'
            if self.box.get(job, filename):
                return
            if len(list(self.box.job(job).glob('input-*.json'))) >= 100:
                raise ValueError('本场定向消息已达 100 条上限。')
            self.box.put(job, filename, dict(id=message_id, job_id=job, target=target,
                by=self.settings.role, text=text.strip(), state='queued', created=now(),
                participant=meta.get('participants', {}).get(target)))
        self.note('定向消息已保存，等待节点 ' + target + ' 接收。')

    def _pump_node_inputs(self):
        if not self.active or not self.client:
            return
        current = getattr(self.client,'current',None)
        job = self.active['id']
        pending = getattr(self, '_steering', {})
        self._steering = pending
        for key, (request_id, expected, started) in list(pending.items()):
            response = self.client.responses.pop(request_id, None)
            if response is None and time.monotonic() - started < 30:
                continue
            value = self.box.get(job, 'input-' + key + '.json')
            if value:
                value['state'] = ('delivered' if response and not response.get('error')
                    and response.get('result', {}).get('turnId') == expected else 'rejected' if response else 'uncertain')
                value['detail'] = str((response or {}).get('error', '未确认送达；不会自动重发' if not response else ''))[:1500]
                value['updated'] = now()
                self.box.put(job, 'input-' + key + '.json', value)
                self.note('定向消息回执：' + value['state'])
            del pending[key]
        if not current or not current.turn_id or current.status != 'running':
            return
        for path in sorted(self.box.job(job).glob('input-*.json')):
            value = read_json(path)
            if value.get('target') != self.settings.role or value.get('state') != 'queued':
                continue
            if value.get('job_id') != job or value.get('participant') != self.instance:
                continue
            with self.box.lifecycle(job):
                self.box.ensure_open(job)
                value.update(state='send_pending', step=current.step, thread_id=current.thread_id,
                             turn_id=current.turn_id, updated=now())
                self.box.put(job, path.name, value)
            try:
                request_id, expected = self.client.begin_steer(value['text'])
                pending[value['id']] = (request_id, expected, time.monotonic())
            except Exception as error:
                value.update(state='uncertain', detail=str(error), updated=now())
                self.box.put(job, path.name, value)
                self.note('定向消息未确认送达，未自动重发。')

    def node_input_prompt(self, step):
        if not self.active:
            return ''
        job=self.active['id'];texts=[]
        for path in sorted(self.box.job(job).glob('input-*.json')):
            value=read_json(path)
            if value.get('target') != self.settings.role or value.get('participant') != self.instance or value.get('job_id') != job:
                continue
            if value.get('state') == 'queued':
                value.update(state='included_next_request', step=step, updated=now())
                self.box.put(job,path.name,value)
                texts.append(value['text'])
        return '\n用户仅给本节点的补充：\n'+'\n'.join(texts) if texts else ''

    def _finish_node_inputs(self):
        pending=getattr(self,'_steering',{})
        if not pending or not self.active:return
        job=self.active['id']
        for key,(request_id,expected,started) in list(pending.items()):
            response=self.client.responses.pop(request_id,None) if self.client else None
            value=self.box.get(job,'input-'+key+'.json')
            if value:
                value.update(state='delivered' if response and not response.get('error') and response.get('result',{}).get('turnId')==expected else 'uncertain',updated=now())
                self.box.put(job,'input-'+key+'.json',value)
            del pending[key]
