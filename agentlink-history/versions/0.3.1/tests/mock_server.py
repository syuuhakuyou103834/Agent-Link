"""Offline App Server fixture. Never calls a model or external service."""
import json
import sys
import threading
import time
from pathlib import Path
import uuid

role, audit_path = sys.argv[1:3]
lock = threading.Lock()
turns = {}


def send(value):
    with lock:
        sys.stdout.buffer.write((json.dumps(value, ensure_ascii=False) + '\n').encode('utf-8'))
        sys.stdout.buffer.flush()


def notify(method, tid, turn_id, **kwargs):
    send({'method': method, 'params': dict(threadId=tid, turnId=turn_id, **kwargs)})


def work(tid, turn_id, prompt, cancel):
    with lock:
        with open(audit_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps({'role': role, 'thread': tid, 'turn': turn_id, 'prompt': prompt}, ensure_ascii=False) + '\n')
    notify('turn/started', tid, turn_id, turn={'id': turn_id, 'status': 'inProgress'})
    notify('item/reasoning/summaryTextDelta', tid, turn_id, itemId='reason', delta='公开摘要：核对中文与上下文。', summaryIndex=0)
    notify('item/started', tid, turn_id, item={'type': 'commandExecution', 'id': 'tool', 'command': 'mock read-only check', 'status': 'inProgress'})
    notify('item/commandExecution/outputDelta', tid, turn_id, itemId='tool', delta='模拟校验通过')
    notify('item/completed', tid, turn_id, item={'type': 'commandExecution', 'id': 'tool', 'command': 'mock read-only check', 'status': 'completed', 'aggregatedOutput': '模拟校验通过', 'exitCode': 0})
    text = role + ' 节点模拟回答：中文传递正确，温度 23℃，已阅读对方材料。' + ('已采纳评审。' if '评审材料' in prompt else '提出具体实施建议。')
    for chunk in [text[i:i+5] for i in range(0, len(text), 5)]:
        if cancel.wait(.35 if '[LONG]' in prompt else .07):
            notify('turn/completed', tid, turn_id, turn={'id': turn_id, 'status': 'interrupted', 'items': [], 'error': None})
            return
        notify('item/agentMessage/delta', tid, turn_id, itemId='answer', delta=chunk)
    if '[FAIL]' in prompt:
        notify('turn/completed', tid, turn_id, turn={'id': turn_id, 'status': 'failed', 'items': [], 'error': {'message': '模拟接口失败'}})
        return
    notify('item/completed', tid, turn_id, item={'type': 'agentMessage', 'id': 'answer', 'text': text, 'phase': 'final_answer'})
    notify('thread/tokenUsage/updated', tid, turn_id, tokenUsage={'last': {'inputTokens': 10, 'outputTokens': 20}})
    notify('turn/completed', tid, turn_id, turn={'id': turn_id, 'status': 'completed', 'items': [], 'error': None})


for raw in sys.stdin.buffer:
    request = json.loads(raw.decode('utf-8'))
    if 'id' not in request:
        continue
    method, p = request.get('method'), request.get('params', {})
    result = {}
    start = None
    if method == 'initialize':
        result = {'userAgent': 'AgentLink offline fixture'}
    elif method == 'skills/list':
        result = {'data': [{'cwd': p['cwds'][0], 'skills': [{'name': 'mock-skill', 'enabled': True, 'description': '离线测试技能'}], 'errors': []}]}
    elif method == 'mcpServerStatus/list':
        result = {'data': [{'name': 'mock-tools', 'authStatus': 'notLoggedIn', 'tools': {'test': {}}}], 'nextCursor': None}
    elif method == 'thread/start':
        result = {'thread': {'id': 'mock-' + role + '-' + uuid.uuid4().hex}, 'sandbox': {'type': 'readOnly'}}
    elif method == 'turn/start':
        turn_id = uuid.uuid4().hex
        cancel = turns[turn_id] = threading.Event()
        result = {'turn': {'id': turn_id, 'status': 'inProgress'}}
        start = threading.Thread(target=work, args=(p['threadId'], turn_id, p['input'][0]['text'], cancel), daemon=True)
    elif method == 'turn/interrupt':
        turns[p['turnId']].set()
    send({'id': request['id'], 'result': result})
    if start:
        start.start()
