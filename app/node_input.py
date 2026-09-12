"""Audited node-specific input. Never retry a steering request after uncertain delivery."""
import re
import time
import math
from contextlib import contextmanager
import hashlib
from .storage import read_json, now, io_path

FEATURE = 'node-intervention-v1'


def ordered_inputs(directory):
    """New messages follow lock-serialized admission, legacy ones their timestamp."""
    def key(item):
        path, value = item
        sequence = value.get('sequence')
        if type(sequence) is int and sequence > 0:
            return (1, sequence, path.name)
        created = value.get('created', 0)
        if type(created) not in (int, float) or not math.isfinite(created):
            created = 0
        return (0, created, path.name)
    # A single durable call receipt commits the complete message set. Message
    # files remain immutable at dispatch; a crash cannot consume a subset.
    committed = {}
    for path in io_path(directory).glob('call-*.json'):
        call = read_json(path) or {}
        if call.get('status') == 'not_sent':
            continue
        for identifier in call.get('input_ids', []):
            committed[identifier] = ('delivered' if call.get('status') == 'result_received' else 'uncertain', call.get('step'))
    values = []
    for path in io_path(directory).glob('input-*.json'):
        value = read_json(path)
        if value.get('id') in committed:
            state, step = committed[value['id']]
            value = dict(value, state=state, step=step)
        values.append((path, value))
    return sorted(values, key=key)


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
            existing = ordered_inputs(self.box.job(job))
            if len(existing) >= 100:
                raise ValueError('本场定向消息已达 100 条上限。')
            sequence = 1 + max((v['sequence'] for _, v in existing
                               if type(v.get('sequence')) is int and v['sequence'] > 0), default=0)
            self.box.put(job, filename, dict(id=message_id, job_id=job, target=target,
                by=self.settings.role, text=text.strip(), state='queued', created=now(), sequence=sequence,
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
        for path, value in ordered_inputs(self.box.job(job)):
            if value.get('target') != self.settings.role or value.get('state') != 'queued':
                continue
            if value.get('job_id') != job or value.get('participant') != self.instance:
                continue
            with self.box.lifecycle(job):
                self.box.ensure_open(job)
                fresh = next((v for p, v in ordered_inputs(self.box.job(job)) if p.name == path.name), None)
                if not fresh or fresh.get('state') != 'queued':
                    continue
                value = fresh
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
        job=self.active['id'];texts=[]; candidates={}
        for path, value in ordered_inputs(self.box.job(job)):
            if value.get('target') != self.settings.role or value.get('participant') != self.instance or value.get('job_id') != job:
                continue
            if value.get('state') == 'queued':
                candidates[value['id']] = hashlib.sha256(value['text'].encode('utf-8')).hexdigest()
                texts.append(value['text'])
        if not hasattr(self, '_input_candidates'):
            self._input_candidates = {}
        self._input_candidates[(job, step)] = candidates
        return '\n用户仅给本节点的补充：\n'+'\n'.join(texts) if texts else ''

    def _commit_node_inputs(self, step, ledger):
        job = self.active['id']
        candidates = getattr(self, '_input_candidates', {}).get((job, step), {})
        with self.box.lifecycle(job):
            self.box.ensure_open(job)
            if self.box.get(job, 'call-' + step + '.json'):
                raise ValueError('请求已有发送凭据，禁止重复提交')
            current = {v['id']: v for _, v in ordered_inputs(self.box.job(job))}
            for key, digest in candidates.items():
                value = current.get(key, {})
                if (value.get('state') != 'queued' or value.get('participant') != self.instance
                        or value.get('target') != self.settings.role or value.get('job_id') != job
                        or hashlib.sha256(value.get('text','').encode('utf-8')).hexdigest() != digest):
                    raise ValueError('补充消息已变化或已交付，拒绝发送旧候选请求')
            ledger.update(input_ids=list(candidates), input_sha256=candidates,
                          input_commit_schema=1, instance=self.instance)
            self.box.put(job, 'call-' + step + '.json', ledger)
        self.client.send_guard = self._request_send_guard

    def _queued_recovery_inputs(self, parent):
        values = []
        for path, value in ordered_inputs(self.box.job(parent['id'])):
            if value.get('state') != 'queued':
                continue
            target = value.get('target')
            if (not re.fullmatch('[a-f0-9]{32}', value.get('id', ''))
                    or path.name != 'input-' + value['id'] + '.json'
                    or target not in ('A','B') or value.get('job_id') != parent['id']
                    or not value.get('participant')
                    or value['participant'] != parent.get('participants', {}).get(target)
                    or not isinstance(value.get('text'), str) or not 1 <= len(value['text'].strip()) <= 12000):
                raise ValueError('恢复定向消息的归属或内容无效')
            values.append(value)
        return values

    @contextmanager
    def _request_send_guard(self):
        # Serialize only the outbound pipe write with control commits; never
        # hold the SMB lifecycle lock while waiting for the model response.
        if not self.active:
            yield
            return
        job = self.active['id']
        while True:
            current = getattr(self.client, 'current', None)
            step = getattr(current, 'step', '')
            self._wait_unpaused(int(step[:3]) if re.fullmatch(r'\d{3}-[AB]', step) else 0)
            with self.box.lifecycle(job):
                self.box.ensure_open(job)
                if self.box.get(job, 'control.json', {}).get('paused'):
                    continue
                self._check_job_instances(self.active)
                yield
                return

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
