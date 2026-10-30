"""每日北京时间00:05后记录压力；启动补当天，唯一键及账号锁保证幂等。"""
import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import time
from threading import Event

from ..models.models import DailyPressure, User
from .pressure import BEIJING, FORMULA_VERSION, compute_pressure, utc, utcnow

logger = logging.getLogger(__name__)


def capture_user(session_factory, user_id, now, source):
    day = utc(now).astimezone(BEIJING).date()
    with session_factory() as db:
        # 与任务写入/注销共用账号锁；删除或重建账号不会留下旧快照。
        if not db.query(User).filter(User.id == user_id).update({User.id:user_id}, synchronize_session=False):
            return False
        if db.query(DailyPressure.id).filter(DailyPressure.user_id == user_id, DailyPressure.record_date == day).first():
            return False
        result = compute_pressure(db, user_id, day)
        db.add(DailyPressure(user_id=user_id, record_date=day, score=result['score'],
                             breakdown=json.dumps(result['breakdown']), computed_at=utc(now).replace(tzinfo=None),
                             source=source, formula_version=FORMULA_VERSION))
        db.commit()
        return True


def run_due(session_factory, now=None, source='scheduled', stop=None):
    now = utc(now or utcnow())
    local = now.astimezone(BEIJING)
    result = dict(created=0, failed=0, scanned=0)
    if local.time() < time(0, 5):
        return result
    try:
        # 读游标先关闭，再逐账号写；避免SQLite读锁阻塞本进程提交。
        with session_factory() as db:
            exists = db.query(DailyPressure.id).filter(DailyPressure.user_id == User.id,
                                                       DailyPressure.record_date == local.date()).exists()
            user_ids = [uid for (uid,) in db.query(User.id).filter(~exists).order_by(User.id).all()]
    except Exception:
        logger.exception('每日压力任务读取账号失败，将在下次检查重试')
        return dict(created=0, failed=1, scanned=0)
    for user_id in user_ids:
        if stop is not None and stop.is_set():
            break
        result['scanned'] += 1
        try:
            result['created'] += int(capture_user(session_factory, user_id, now, source))
        except Exception:
            # 一个账号失败不阻止其他账号，缺失记录下次仍会进入候选。
            result['failed'] += 1
            logger.exception('每日压力记录失败 user_id=%s，将在下次检查重试', user_id)
    return result


def make_lifespan(session_factory, interval=60, clock=None):
    @asynccontextmanager
    async def lifespan(app):
        stopped = Event()
        wake = asyncio.Event()
        state = dict(running=True, timezone='Asia/Shanghai', scheduled_time='00:05', poll_seconds=interval)
        app.state.daily_pressure = state

        async def poll(source):
            now = (clock or utcnow)()
            result = await asyncio.to_thread(run_due, session_factory, now, source, stopped)
            state.update(last_poll_at=utc(now).isoformat(), **result)

        await poll('startup')

        async def worker():
            while not stopped.is_set():
                try:
                    await asyncio.wait_for(wake.wait(), timeout=interval)
                except asyncio.TimeoutError:
                    if not stopped.is_set():
                        await poll('scheduled')

        task = asyncio.create_task(worker())
        try:
            yield
        finally:
            stopped.set()
            wake.set()
            await task
            state['running'] = False
    return lifespan
