from datetime import datetime, timedelta, UTC
from pathlib import Path

import pytest

from app.models import IcsSource, Notification
from app.scheduler.ics import compute_due, expand_occurrences, fetch_ics_text, run_all_ics_ticks, run_ics_source_tick

FIXTURE = Path(__file__).parent / "fixtures" / "sample.ics"


def test_fetch_ics_text_rejects_local_paths():
    with pytest.raises(ValueError):
        fetch_ics_text(str(FIXTURE))


def test_expand_occurrences_includes_single_and_recurring_events():
    ics_text = FIXTURE.read_text()
    window_start = datetime(2024, 1, 3, 0, 0, tzinfo=UTC)
    window_end = datetime(2024, 1, 4, 0, 0, tzinfo=UTC)

    occurrences = expand_occurrences(ics_text, window_start, window_end)
    uids = {o.uid for o in occurrences}

    assert "event-1@example.com" in uids
    assert "event-2-recurring@example.com" in uids  # the 01-03 instance of the daily recurrence


def test_compute_due_only_after_trigger_and_before_start():
    ics_text = FIXTURE.read_text()
    occurrences = expand_occurrences(
        ics_text, datetime(2024, 1, 3, 0, 0, tzinfo=UTC), datetime(2024, 1, 4, 0, 0, tzinfo=UTC)
    )

    before_trigger = compute_due(occurrences, [30, 15], now=datetime(2024, 1, 3, 9, 0, tzinfo=UTC))
    at_30min_trigger = compute_due(occurrences, [30, 15], now=datetime(2024, 1, 3, 9, 30, tzinfo=UTC))
    after_start = compute_due(occurrences, [30, 15], now=datetime(2024, 1, 3, 10, 0, tzinfo=UTC))

    assert before_trigger == []
    assert [offset for _, offset in at_30min_trigger if _.uid == "event-1@example.com"] == [30]
    assert after_start == []  # event has started, no longer "due"


def test_run_ics_source_tick_creates_and_dedupes_notifications(db_session, user, monkeypatch):
    monkeypatch.setattr("app.scheduler.ics.fetch_ics_text", lambda url_or_path: FIXTURE.read_text())
    source = IcsSource(
        user_id=user.id,
        url_or_path="https://example.com/calendar.ics",
        offsets_minutes=[30, 15],
        refresh_minutes=15,
    )
    db_session.add(source)
    db_session.commit()

    now = datetime(2024, 1, 3, 9, 30, tzinfo=UTC)
    created = run_ics_source_tick(db_session, source, now=now)
    created_again = run_ics_source_tick(db_session, source, now=now)

    assert created >= 1
    assert created_again == 0  # same tick again -> nothing new, dedupe_key blocks re-insert
    assert db_session.query(Notification).count() == created
    assert source.last_synced_at == now


def test_run_ics_source_tick_only_refetches_when_stale(db_session, user, monkeypatch):
    """Regression test: reminders used to only get checked once per `refresh_minutes`, so a
    30-minute-before offset could fire anywhere from 30 down to (30 - refresh_minutes) minutes
    before the event, instead of at 30. The fetch itself should stay throttled to
    `refresh_minutes` (it hits a remote server) - but the due-check must run every call."""
    fetch_calls = []

    def fake_fetch(url_or_path):
        fetch_calls.append(url_or_path)
        return FIXTURE.read_text()

    monkeypatch.setattr("app.scheduler.ics.fetch_ics_text", fake_fetch)
    source = IcsSource(
        user_id=user.id,
        url_or_path="https://example.com/calendar.ics",
        offsets_minutes=[30, 15],
        refresh_minutes=15,
    )
    db_session.add(source)
    db_session.commit()

    # First call: no cache yet, must fetch.
    run_ics_source_tick(db_session, source, now=datetime(2024, 1, 3, 9, 5, tzinfo=UTC))
    assert len(fetch_calls) == 1
    assert source.cached_ics_text is not None

    # A minute later - well inside refresh_minutes=15 - must NOT refetch, but must still be able
    # to pick up anything newly due against the cached feed.
    run_ics_source_tick(db_session, source, now=datetime(2024, 1, 3, 9, 6, tzinfo=UTC))
    assert len(fetch_calls) == 1

    # 15+ minutes after the first fetch: due to refetch again.
    run_ics_source_tick(db_session, source, now=datetime(2024, 1, 3, 9, 21, tzinfo=UTC))
    assert len(fetch_calls) == 2


def test_run_ics_source_tick_fires_promptly_on_frequent_ticks(db_session, user, monkeypatch):
    """The core regression: with ticks every minute, the 30-min-before reminder must fire at
    exactly minute 30, not get stuck waiting for a 15-minute refresh window to elapse."""
    monkeypatch.setattr("app.scheduler.ics.fetch_ics_text", lambda url_or_path: FIXTURE.read_text())
    source = IcsSource(
        user_id=user.id,
        url_or_path="https://example.com/calendar.ics",
        offsets_minutes=[30, 15],
        refresh_minutes=15,
    )
    db_session.add(source)
    db_session.commit()

    event_start = datetime(2024, 1, 3, 10, 0, tzinfo=UTC)  # event-1@example.com in the fixture
    fired_at: dict[int, datetime] = {}
    now = event_start - timedelta(minutes=40)
    while now <= event_start:
        run_ics_source_tick(db_session, source, now=now)
        for notification in db_session.query(Notification).filter(Notification.dedupe_key.contains("event-1")):
            for offset in (30, 15):
                if offset not in fired_at and notification.dedupe_key.endswith(f":{offset}"):
                    fired_at[offset] = now
        now += timedelta(minutes=1)

    assert fired_at[30] == event_start - timedelta(minutes=30)
    assert fired_at[15] == event_start - timedelta(minutes=15)


def test_run_all_ics_ticks_checks_every_enabled_source_every_call(db_session, user, monkeypatch):
    monkeypatch.setattr("app.scheduler.ics.fetch_ics_text", lambda url_or_path: FIXTURE.read_text())
    source = IcsSource(
        user_id=user.id,
        url_or_path="https://example.com/calendar.ics",
        offsets_minutes=[30, 15],
        refresh_minutes=15,
    )
    db_session.add(source)
    db_session.commit()

    now = datetime(2024, 1, 3, 9, 30, tzinfo=UTC)
    created = run_all_ics_ticks(db_session, now=now)

    assert created >= 1
