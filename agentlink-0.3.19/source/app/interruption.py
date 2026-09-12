"""Technical interruption evidence and narrowly scoped legacy recovery eligibility."""
import hashlib
import json

FEATURE = 'recoverable-peer-interruption-v1'
LEGACY_PREFIX = '对端实例失效，停止继续执行；已发送请求的结果须核查：'
LEGACY_REASONS = (
    '对端能力记录已失效、离线或实例信息无效，拒绝使用遗留心跳。',
    '对端已更换实例，原场次不能转交给重启后的执行者。',
    '对端能力与当前角色锁归属不一致。',
    '对端角色锁缺失，不能确认当前实例在线。',
    '对端角色锁已经释放，遗留能力记录不能用于执行。',
)


class PeerStateError(ValueError):
    def __init__(self, message, details):
        super().__init__(message)
        self.details = details


class TechnicalInterruption(RuntimeError):
    def __init__(self, message, details):
        super().__init__(message)
        self.details = details


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()


def legacy_peer_failure(box, meta):
    """Recognize old technical cancellations, never generic/manual cancellations.

    Read-only; original terminal state remains immutable. The caller must also
    honor the conversation's user stop and require an explicit resume input.
    """
    if meta.get('workflow') != 'unified-conversation-v1':
        return None
    job = meta['id']
    state = box.get(job, 'state.json', {}) or {}
    control = box.get(job, 'control.json', {}) or {}
    if state.get('status') != 'cancelled' or control.get('cancelled') is not False:
        return None
    message = state.get('error')
    if message not in [LEGACY_PREFIX + reason for reason in LEGACY_REASONS]:
        return None
    for role in ('A', 'B'):
        error = box.get(job, role + '-error.json', {}) or {}
        if error.get('status') == 'cancelled' and error.get('message') == message:
            return dict(kind='legacy_peer_failure', origin=role, message=message,
                        state_sha256=fingerprint(state), control_sha256=fingerprint(control),
                        error_sha256=fingerprint(error))
    return None


def recovery_parent(box, meta):
    job = meta['id']
    state = box.get(job, 'state.json', {}) or {}
    control = box.get(job, 'control.json', {}) or {}
    if control.get('cancelled'):
        raise ValueError('用户已停止原任务，不能恢复。')
    legacy = legacy_peer_failure(box, meta)
    if state.get('status') != 'failed' and not legacy:
        raise ValueError('仅支持恢复失败或已核实的技术中断场次；停止和完成场次不会复活。')
    return dict(state_sha256=fingerprint(state), control_sha256=fingerprint(control), legacy=legacy)


def recovery_hint(info):
    if info.get('request_state') == 'not_sent':
        return '本步骤尚未发送模型请求，已完成成果保留。两端就绪后输入“继续”，接续本步骤。'
    if info.get('request_state') == 'result_received':
        return '模型结果已收到，交付尚需核查。不会自动重发；核查后输入“继续”。'
    return '本步骤请求结果需要核查，不会自动重发。两端就绪并核查后输入“继续”。'
