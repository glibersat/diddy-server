from datetime import datetime, timedelta, UTC
from pathlib import Path

from app.models import DailySchedule, IcsSource, NotificationStatus, RuleType, User
from app.notify import next_up
from app.notify.queue import enqueue_notification

FIXTURE = Path(__file__).parent / "fixtures" / "sample.ics"


def test_next_reminder_none_with_no_rules(db_session, user):
    assert next_up.next_reminder(db_session, user.id) is None


def queue(db_session, user_id, key, scheduled_for):
    return enqueue_notification(
        db_session,
        user_id,
        rule_type=RuleType.manual,
        rule_id=key,
        dedupe_key=key,
        title="Hibou",
        body="Appeler le dentiste",
        scheduled_for=scheduled_for,
    )


def test_next_reminder_includes_a_queued_reminder(db_session, user):
    db_session.add(DailySchedule(user_id=user.id, time_of_day="20:00", message="Evening walk"))
    db_session.commit()
    now = datetime(2024, 1, 3, 7, 0, tzinfo=UTC)
    due = now + timedelta(hours=1)
    queue(db_session, user.id, "soon", due)

    result = next_up.next_reminder(db_session, user.id, now=now)

    assert (result.rule_type, result.title, result.body) == (RuleType.manual, "Hibou", "Appeler le dentiste")
    assert result.scheduled_for == due


def test_next_reminder_keeps_an_earlier_rule_ahead_of_a_queued_reminder(db_session, user):
    db_session.add(DailySchedule(user_id=user.id, time_of_day="09:00", message="Take meds"))
    db_session.commit()
    now = datetime(2024, 1, 3, 7, 0, tzinfo=UTC)
    queue(db_session, user.id, "later", now + timedelta(hours=5))

    assert next_up.next_reminder(db_session, user.id, now=now).body == "Take meds"


def test_next_reminder_skips_queued_reminders_already_due_or_gone_out(db_session, user):
    now = datetime(2024, 1, 3, 7, 0, tzinfo=UTC)
    queue(db_session, user.id, "overdue", now - timedelta(minutes=1))
    sent = queue(db_session, user.id, "sent", now + timedelta(hours=1))
    sent.status = NotificationStatus.sent
    db_session.commit()

    assert next_up.next_reminder(db_session, user.id, now=now) is None


def test_next_reminder_leaves_out_another_users_queued_reminder(db_session, user):
    other = User(email="other@example.com", timezone="Europe/Paris")
    db_session.add(other)
    db_session.commit()
    now = datetime(2024, 1, 3, 7, 0, tzinfo=UTC)
    queue(db_session, other.id, "theirs", now + timedelta(hours=1))

    assert next_up.next_reminder(db_session, user.id, now=now) is None


def test_next_reminder_picks_soonest_daily_schedule(db_session, user):
    # user is Europe/Paris (UTC+1 in January) - 09:00 local == 08:00 UTC
    soon = DailySchedule(user_id=user.id, time_of_day="09:00", message="Take meds")
    later = DailySchedule(user_id=user.id, time_of_day="20:00", message="Evening walk")
    db_session.add_all([soon, later])
    db_session.commit()

    now = datetime(2024, 1, 3, 7, 0, tzinfo=UTC)  # 08:00 local, before both
    result = next_up.next_reminder(db_session, user.id, now=now)

    assert result.rule_type == RuleType.daily_schedule
    assert result.body == "Take meds"
    assert result.scheduled_for == datetime(2024, 1, 3, 8, 0, tzinfo=UTC)


def test_next_reminder_skips_disabled_and_wrong_weekday(db_session, user):
    disabled = DailySchedule(user_id=user.id, time_of_day="09:00", message="Off", enabled=False)
    # 2024-01-03 is a Wednesday (bit 2); mask only allows Monday (bit 0)
    monday_only = DailySchedule(user_id=user.id, time_of_day="09:00", message="Mondays", weekdays_mask=0b0000001)
    db_session.add_all([disabled, monday_only])
    db_session.commit()

    now = datetime(2024, 1, 3, 7, 0, tzinfo=UTC)
    result = next_up.next_reminder(db_session, user.id, now=now)

    assert result.body == "Mondays"
    assert result.scheduled_for.weekday() == 0


def test_next_reminder_includes_ics_source(db_session, user, monkeypatch):
    monkeypatch.setattr("app.scheduler.ics.fetch_ics_text", lambda url_or_path: FIXTURE.read_text())
    source = IcsSource(user_id=user.id, url_or_path="https://example.com/cal.ics", offsets_minutes=[30])
    schedule = DailySchedule(user_id=user.id, time_of_day="23:59", message="Late one")
    db_session.add_all([source, schedule])
    db_session.commit()

    now = datetime(2024, 1, 3, 9, 0, tzinfo=UTC)  # event-1 starts 10:00 per fixture -> trigger 09:30
    result = next_up.next_reminder(db_session, user.id, now=now)

    assert result.rule_type == RuleType.ics_reminder
    assert result.scheduled_for == datetime(2024, 1, 3, 9, 30, tzinfo=UTC)


def test_next_reminder_ignores_unreachable_ics_source(db_session, user, monkeypatch):
    def _boom(url_or_path):
        raise Exception("connection refused")

    monkeypatch.setattr("app.scheduler.ics.fetch_ics_text", _boom)
    source = IcsSource(user_id=user.id, url_or_path="https://example.com/cal.ics", offsets_minutes=[30])
    schedule = DailySchedule(user_id=user.id, time_of_day="09:00", message="Fallback")
    db_session.add_all([source, schedule])
    db_session.commit()

    now = datetime(2024, 1, 3, 7, 0, tzinfo=UTC)
    result = next_up.next_reminder(db_session, user.id, now=now)

    assert result.body == "Fallback"
