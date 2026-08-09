from datetime import datetime, UTC
from pathlib import Path

import pytest

from app.models import IcsSource, Notification
from app.scheduler.ics import compute_due, expand_occurrences, fetch_ics_text, run_ics_source_tick

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
