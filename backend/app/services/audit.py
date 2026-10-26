"""关键操作审计：只记录动作和结果，不读取请求正文、查询参数或响应内容。"""
import logging
import re
from datetime import datetime, timezone

from starlette.concurrency import run_in_threadpool

from ..database import SessionLocal
from ..models.models import OperationLog

logger = logging.getLogger(__name__)

# 使用路由模板匹配，避免把用户输入、查询参数和任意 URL 写进日志。
ACTIONS = {
    ('POST', '/api/auth/register'): ('auth.register', '注册账号'),
    ('POST', '/api/auth/login'): ('auth.login', '登录'),
    ('POST', '/api/auth/logout'): ('auth.logout', '退出登录'),
    ('POST', '/api/auth/change-password'): ('auth.password', '修改密码'),
    ('POST', '/api/auth/reset-password/verify'): ('auth.reset.verify', '验证密码找回'),
    ('POST', '/api/auth/reset-password/confirm'): ('auth.reset.confirm', '重置密码'),
    ('PUT', '/api/auth/me'): ('auth.profile', '修改个人资料'),
    ('DELETE', '/api/auth/me'): ('auth.delete', '注销账号'),
    ('POST', '/api/materials'): ('material.upload', '上传资料'),
    ('PUT', '/api/materials/{material_id}'): ('material.update', '修改资料'),
    ('DELETE', '/api/materials/{material_id}'): ('material.delete', '删除资料'),
    ('POST', '/api/ai/profile'): ('ai.profile', '生成学习画像'),
    ('POST', '/api/ai/profile/complete'): ('ai.profile.complete', '补全学习画像'),
    ('POST', '/api/ai/analyze'): ('ai.analyze', '生成复习分析'),
    ('POST', '/api/ai/analyses/{exam_id}/replan'): ('ai.replan', '请求学习反馈调整'),
    ('POST', '/api/exams'): ('exam.create', '录入考试'),
    ('PUT', '/api/exams/{exam_id}'): ('exam.update', '修改考试'),
    ('DELETE', '/api/exams/{exam_id}'): ('exam.delete', '删除考试'),
    ('POST', '/api/exams/import-ics/confirm'): ('exam.ics', '确认导入日历'),
    ('POST', '/api/tasks'): ('task.create', '新增任务'),
    ('PUT', '/api/tasks/{task_id}'): ('task.update', '修改任务'),
    ('DELETE', '/api/tasks/{task_id}'): ('task.delete', '删除任务'),
    ('POST', '/api/tasks/{task_id}/checkin'): ('task.checkin', '任务打卡'),
    ('DELETE', '/api/tasks/{task_id}/checkin'): ('task.uncheckin', '撤销打卡'),
    ('POST', '/api/admin/courses'): ('admin.course.create', '新增课程'),
    ('PUT', '/api/admin/courses/{course_id}'): ('admin.course.update', '修改课程'),
    ('DELETE', '/api/admin/courses/{course_id}'): ('admin.course.delete', '删除课程'),
    ('POST', '/api/admin/users/{user_id}/ban'): ('admin.ban', '封禁账号'),
    ('POST', '/api/admin/users/{user_id}/unban'): ('admin.unban', '解除封禁'),
    ('DELETE', '/api/admin/materials/{material_id}'): ('admin.material.delete', '删除违规资料'),
    ('POST', '/api/admin/file-cleanups/retry'): ('admin.files.retry', '重试文件清理'),
}
ACTION_LABELS = {action: label for action, label in ACTIONS.values()}


class AuditMiddleware:
    def __init__(self, app, session_factory=SessionLocal):
        self.app = app
        self.session_factory = session_factory

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        status_code = 500
        async def capture(message):
            nonlocal status_code
            if message['type'] == 'http.response.start':
                status_code = message['status']
            await send(message)
        try:
            await self.app(scope, receive, capture)
        finally:
            matched_route = getattr(scope.get('route'), 'path', '')
            # FastAPI 的延迟 include_router 在部分版本中只保留局部 route.path。
            # 用已匹配路由 + 白名单模板补全前缀，始终只持久化固定模板。
            route = next((template for method, template in ACTIONS
                          if method == scope['method'] and scope.get('route') is not None
                          and template.endswith(matched_route)
                          and re.fullmatch(re.sub(r'\{[^}]+\}', '[^/]+', template), scope['path'])), '')
            action = ACTIONS.get((scope['method'], route))
            if action:
                state = scope.get('state', {})
                actor = state.get('audit_actor', {})
                target = next((str(value) for key, value in scope.get('path_params', {}).items() if key.endswith('_id')), '')
                if not re.fullmatch(r'[A-Za-z0-9-]{1,64}', target):
                    target = ''
                record = dict(actor_id=actor.get('id'), actor_name=actor.get('name', '')[:64],
                              action=action[0], target_id=target, method=scope['method'], path=route,
                              status_code=status_code, created_at=datetime.now(timezone.utc).replace(tzinfo=None))
                await run_in_threadpool(self.record, record)

    def record(self, values):
        try:
            with self.session_factory() as db:
                db.add(OperationLog(**values))
                db.commit()
        except Exception:
            # 审计故障不将已经成功的业务操作伪装成失败；异常写入服务端日志。
            logger.exception('Operation log persistence failed')
