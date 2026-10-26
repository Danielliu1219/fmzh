import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import jwt
from fastapi import Depends, FastAPI, Header
from fastapi.testclient import TestClient
from icalendar import Calendar, Event
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, get_db
from app.models.models import Exam, IcsImportReceipt, StudySetting, Task, User
from app.routers import exams
from app.services.calendar_io import parse_events
from app.utils.security import get_current_user


class IcsTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.engine = create_engine('sqlite:///' + (Path(self.temp.name) / 'test.db').as_posix(), connect_args={'check_same_thread': False})
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, autoflush=False)
        self.owner = User(username='owner', hashed_password='unused')
        self.peer = User(username='peer', hashed_password='unused')
        self.db.add_all([self.owner, self.peer]); self.db.flush()
        self.exam = Exam(user_id=self.owner.id, subject='数学', exam_date=date.today() + timedelta(days=10))
        self.db.add_all([self.exam, StudySetting(user_id=self.owner.id, daily_minutes=120)]); self.db.commit()
        app = FastAPI()
        def database():
            with Session(self.engine, autoflush=False) as db: yield db
        def current(x_user_id: int = Header(default=self.owner.id), db=Depends(get_db)):
            return db.get(User, x_user_id)
        app.dependency_overrides[get_db] = database
        app.dependency_overrides[get_current_user] = current
        app.include_router(exams.router, prefix='/api/exams')
        self.client = TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        self.client.close(); self.db.close(); self.engine.dispose(); self.temp.cleanup()

    def calendar(self, minutes=(30,), day=None, title='复习', recurring=False):
        calendar = Calendar()
        calendar.add('version', '2.0'); calendar.add('prodid', '-//test//EN')
        for i, amount in enumerate(minutes):
            event = Event()
            start = datetime.combine(day or date.today(), datetime.min.time()) + timedelta(hours=9+i)
            event.add('summary', title + str(i)); event.add('dtstart', start); event.add('dtend', start+timedelta(minutes=amount))
            if recurring: event.add('rrule', {'freq': 'daily', 'count': 3})
            calendar.add_component(event)
        return calendar.to_ical()

    def preview(self, content=None, status=200, extra=None):
        response = self.client.post('/api/exams/import-ics', data={'exam_id': self.exam.id, **(extra or {})}, files={'file': ('test.ics', content or self.calendar(), 'text/calendar')})
        self.assertEqual(response.status_code, status, response.text)
        return response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text

    def confirm(self, preview, status=200, headers=None):
        response = self.client.post('/api/exams/import-ics/confirm', json={'preview_token': preview['preview_token']}, headers=headers)
        self.assertEqual(response.status_code, status, response.text)
        return response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text

    def test_preview_is_read_only_and_cancel_needs_no_cleanup(self):
        before = {table.name: self.db.execute(table.select()).all() for table in Base.metadata.sorted_tables}
        preview = self.preview()
        self.assertEqual(preview['count'], 1); self.assertEqual(preview['imported'], 0)
        self.assertEqual(before, {table.name: self.db.execute(table.select()).all() for table in Base.metadata.sorted_tables})

    def test_confirm_and_repeated_file_or_token_are_idempotent(self):
        preview = self.preview()
        self.assertEqual(self.confirm(preview)['imported'], 1)
        self.assertTrue(self.confirm(preview)['already_imported'])
        self.assertTrue(self.preview()['already_imported'])
        self.assertEqual(self.db.query(Task).count(), 1)
        self.assertEqual(self.db.query(IcsImportReceipt).count(), 1)

    def test_two_new_events_are_accumulated_before_budget_check(self):
        preview = self.preview(self.calendar((75, 75)))
        self.assertEqual(preview['conflicts'][0]['planned_minutes'], 150)
        self.confirm(preview, 409)
        self.assertEqual(self.db.query(Task).count(), 0)

    def test_receipt_remains_idempotent_after_account_session_changes(self):
        preview = self.preview()
        self.confirm(preview)
        self.owner.auth_key = 'new-session-key'; self.db.commit()
        preview = self.preview()
        self.assertTrue(preview['already_imported'])
        self.assertTrue(self.confirm(preview)['already_imported'])
        self.assertEqual(self.db.query(Task).count(), 1)

    def test_all_subject_workload_and_shared_budget_cannot_be_bypassed(self):
        second = Exam(user_id=self.owner.id, subject='英语', exam_date=self.exam.exam_date)
        self.db.add(second); self.db.flush()
        self.db.add(Task(user_id=self.owner.id, exam_id=second.id, title='其他科', plan_date=date.today(), estimated_minutes=100)); self.db.commit()
        preview = self.preview(extra={'daily_limit_minutes': 960})
        self.assertEqual(preview['daily_limit_minutes'], 120)
        self.assertTrue(preview['conflicts']); self.confirm(preview, 409)
        self.assertEqual(self.db.query(Task).count(), 1)

    def test_dates_before_today_and_after_exam_are_not_confirmable(self):
        for day in [date.today()-timedelta(days=1), self.exam.exam_date+timedelta(days=1)]:
            preview = self.preview(self.calendar(day=day))
            self.assertTrue(preview['conflicts']); self.confirm(preview, 409)

    def test_budget_task_and_exam_changes_invalidate_preview(self):
        preview = self.preview()
        self.db.get(StudySetting, self.owner.id).daily_minutes = 90; self.db.commit()
        self.confirm(preview, 409)
        preview = self.preview()
        self.db.add(Task(user_id=self.owner.id, exam_id=self.exam.id, title='new', plan_date=date.today(), estimated_minutes=10)); self.db.commit()
        self.confirm(preview, 409)
        preview = self.preview()
        self.exam.subject = 'renamed'; self.db.commit()
        self.confirm(preview, 409)

    def test_other_owner_invalid_purpose_expired_and_tampered_tokens_rejected(self):
        preview = self.preview()
        self.confirm(preview, 409, {'X-User-ID': str(self.peer.id)})
        for changes in [{'typ': 'access'}, {'exp': datetime.now(timezone.utc)-timedelta(seconds=10)}, {'sid': 'stale'}]:
            payload = jwt.decode(preview['preview_token'], settings.SECRET_KEY, algorithms=['HS256'])
            payload.update(changes)
            self.confirm({'preview_token': jwt.encode(payload, settings.SECRET_KEY, algorithm='HS256')}, 409)
        self.confirm({'preview_token': 'invalid'}, 409)
        self.assertEqual(self.db.query(Task).count(), 0)

    def test_concurrent_confirm_inserts_once(self):
        preview = self.preview()
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: self.client.post('/api/exams/import-ics/confirm', json={'preview_token': preview['preview_token']}), range(2)))
        self.assertEqual([r.status_code for r in responses], [200, 200], [r.text for r in responses])
        self.assertEqual(self.db.query(Task).count(), 1)

    def test_failed_commit_rolls_back_receipt_and_all_tasks(self):
        preview = self.preview(self.calendar((30, 30)))
        with patch.object(Session, 'commit', side_effect=RuntimeError('injected')):
            self.confirm(preview, 500)
        self.assertEqual(self.db.query(Task).count(), 0)
        self.assertEqual(self.db.query(IcsImportReceipt).count(), 0)
        self.assertEqual(self.confirm(preview)['imported'], 2)

    def test_invalid_recurrence_and_oversize_input_rejected(self):
        self.preview(b'not a calendar', 400)
        self.preview(self.calendar(recurring=True), 400)
        self.preview(self.calendar(minutes=(-10,)), 400)
        with patch.object(settings, 'MAX_UPLOAD_SIZE_MB', 0): self.preview(status=413)

    def test_utc_event_moves_to_shanghai_day_and_duplicates_are_reported(self):
        cal = Calendar(); cal.add('version', '2.0')
        event = Event(); event.add('summary', '跨时区')
        start = datetime.combine(date.today(), datetime.min.time(), tzinfo=timezone.utc) - timedelta(hours=1)
        event.add('dtstart', start); event.add('duration', timedelta(minutes=30))
        cal.add_component(event); cal.add_component(event)
        events, skipped = parse_events(cal.to_ical().decode())
        self.assertEqual(events[0]['day'], date.today().isoformat()); self.assertEqual(skipped, 1)

    def test_export_round_trip_special_text_event_count_dates_and_utf8_folding(self):
        special = '中文' * 80 + '\nEND:VEVENT\nBEGIN:VEVENT\nSUMMARY:伪造\\逗号,分号;'
        self.exam.subject = '数,学;\\\n新行'
        self.exam.location = '教室;A,\\\n二楼'
        self.exam.note = special
        task = Task(user_id=self.owner.id, exam_id=self.exam.id, title=special, plan_date=date.today(), estimated_minutes=45)
        self.db.add(task); self.db.commit()
        response = self.client.get('/api/exams/export-ics')
        self.assertEqual(response.status_code, 200)
        events = Calendar.from_ical(response.content).walk('VEVENT')
        self.assertEqual(len(events), 2)
        self.assertEqual(str(events[0]['SUMMARY']), '【考试】' + self.exam.subject)
        self.assertEqual(str(events[0]['LOCATION']), self.exam.location)
        self.assertEqual(events[0].decoded('DTEND'), self.exam.exam_date + timedelta(days=1))
        self.assertEqual(str(events[1]['SUMMARY']), '【任务】' + self.exam.subject + '·' + special)
        self.assertIsNotNone(events[1].decoded('DTSTAMP').tzinfo)
        self.assertEqual((events[1].decoded('DTEND')-events[1].decoded('DTSTART')).total_seconds(), 45*60)
        for line in response.content.split(b'\r\n'):
            self.assertLessEqual(len(line), 75)
            line.decode('utf-8')


if __name__ == '__main__': unittest.main()
