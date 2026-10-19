from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.models import Notification, NotificationPreference, Reminder, User
from ..services import notifications as service
from ..utils.security import get_current_user

router = APIRouter()


class Preferences(BaseModel):
    enabled: bool = True
    exam_enabled: bool = True
    task_enabled: bool = True


class ReminderInput(BaseModel):
    enabled: bool
    event_time: str = Field(pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$')
    advance_minutes: int = Field(ge=0, le=43200)


class ReadInput(BaseModel):
    is_read: bool


@router.get('/preferences')
def preferences(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return service.preference(db, user.id)


@router.put('/preferences')
def save_preferences(payload: Preferences, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(NotificationPreference, user.id)
    if not row:
        row = NotificationPreference(user_id=user.id)
        db.add(row)
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    db.commit()
    return service.preference(db, user.id)


@router.get('/reminders/{kind}/{target_id}')
def get_reminder(kind: Literal['exam', 'task'], target_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return service.reminder_data(db, user.id, kind, target_id)


@router.put('/reminders/{kind}/{target_id}')
def save_reminder(kind: Literal['exam', 'task'], target_id: int, payload: ReminderInput, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    source = service.target(db, user.id, kind, target_id)
    row = db.query(Reminder).filter_by(user_id=user.id, target_type=kind, target_id=target_id).first()
    if not row:
        row = Reminder(user_id=user.id, target_type=kind, target_id=target_id)
        db.add(row)
    row.target_created_at = source.created_at
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    db.commit()
    return service.reminder_data(db, user.id, kind, target_id)


@router.post('/check')
def check(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {'created': service.check_due(db, user.id)}


@router.get('')
def history(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=50), unread_only: bool = False,
            user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    base = db.query(Notification).filter_by(user_id=user.id, deleted_at=None)
    unread_count = base.filter_by(is_read=False).count()
    query = base.filter_by(is_read=False) if unread_only else base
    total = query.count()
    rows = query.order_by(Notification.created_at.desc(), Notification.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {'items': [service.notification_data(db, user.id, row) for row in rows], 'unread_count': unread_count,
            'total': total, 'page': page, 'page_size': page_size}


@router.post('/read-all')
def read_all(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.query(Notification).filter_by(user_id=user.id, deleted_at=None, is_read=False).update({'is_read': True})
    db.commit()
    return {'ok': True}


def own_notification(db, user_id, notification_id):
    row = db.query(Notification).filter_by(id=notification_id, user_id=user_id, deleted_at=None).first()
    if not row:
        raise HTTPException(404, '通知不存在')
    return row


@router.patch('/{notification_id}')
def mark(notification_id: int, payload: ReadInput, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = own_notification(db, user.id, notification_id)
    row.is_read = payload.is_read
    db.commit()
    return service.notification_data(db, user.id, row)


@router.delete('/{notification_id}')
def remove(notification_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = own_notification(db, user.id, notification_id)
    row.deleted_at = service.utcnow()
    db.commit()
    return {'ok': True}
