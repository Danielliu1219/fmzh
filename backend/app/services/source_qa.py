"""按来源版本读取已保存的题目问答，兼容旧客户端生成的后台任务。"""
import json

from ..models.models import AIJob, QaConversation, QaMessage
from .ai_jobs import payload_hash


def legacy_help_kind(content):
    if content.startswith('请针对本次指定来源只给分步提示'):
        return 'hint'
    if content.startswith('请针对本次指定来源给出参考解答'):
        return 'answer'
    return None


def help_history(db, user_id, unit):
    owned = db.query(QaMessage).join(QaConversation).filter(
        QaConversation.user_id == user_id, QaConversation.exam_id == unit['exam_id'])
    messages = owned.filter(QaMessage.role == 'assistant', QaMessage.source_unit_id == unit['id'],
                            QaMessage.source_help_kind.in_(['hint', 'answer'])).all()
    kinds = {m.id: m.source_help_kind for m in messages}

    # 旧消息没有来源字段。仅在原任务哈希完整匹配资料、来源版本及问题时恢复，避免同名题串答。
    candidates = owned.filter(QaMessage.role == 'user', QaMessage.source_unit_id.is_(None),
                              QaMessage.content.startswith('请针对本次指定来源', autoescape=True)).all()
    hashes = {}
    for question in candidates:
        kind = legacy_help_kind(question.content)
        if kind:
            digest = payload_hash('qa', dict(conversation_id=question.conversation_id, content=question.content,
                source_material_id=unit['material_id'], source_unit_id=unit['id']))
            hashes[digest] = (question.conversation_id, kind)
    if hashes:
        jobs = db.query(AIJob).filter(AIJob.user_id == user_id, AIJob.kind == 'qa',
            AIJob.status == 'succeeded', AIJob.payload_hash.in_(hashes)).all()
        for job in jobs:
            try:
                result = json.loads(job.result_json)
                saved = result['messages'][-1]
                conversation_id, kind = hashes[job.payload_hash]
                message = owned.filter(QaMessage.id == saved['id'], QaMessage.conversation_id == conversation_id,
                                       QaMessage.role == 'assistant').first()
            except (ValueError, TypeError, KeyError, IndexError):
                continue
            if message and message.id not in kinds:
                messages.append(message)
                kinds[message.id] = kind
    return [dict(id=m.id, conversation_id=m.conversation_id, kind=kinds[m.id], content=m.content,
                 created_at=m.created_at) for m in sorted(messages, key=lambda m: m.id)]


def pending_help(db, user_id, unit_id):
    jobs = db.query(AIJob).filter(AIJob.user_id == user_id, AIJob.kind == 'qa',
                                 AIJob.status.in_(['queued', 'running'])).order_by(AIJob.created_at).all()
    result = []
    for job in jobs:
        payload = json.loads(job.payload_json)
        kind = payload.get('source_help_kind') or legacy_help_kind(payload.get('content', ''))
        if payload.get('source_unit_id') == unit_id and kind:
            result.append(dict(id=job.id, status=job.status, kind=kind,
                               conversation_id=payload['conversation_id']))
    return result
