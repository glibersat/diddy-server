from datetime import datetime, UTC
from pathlib import Path

from app.models import DailySchedule, IcsSource, RuleType
from app.notify import next_up

FIXTURE = Path(__file__).parent / "fixtures" / "sample.ics"


def test_next_reminder_none_with_no_rules(db_session, user):
    assert next_up.next_reminder(db_session, user.id) is None


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
