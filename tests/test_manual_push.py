import pytest

from app.models import Notification, NotificationStatus, ReminderKind, RuleType
from app.notify.manual import push_notification


def test_push_notification_enqueues_pending_notification(db_session, user):
    notification = push_notification(db_session, user, title="Heads up", body="Water the plants")

    assert notification.rule_type == RuleType.manual
    assert notification.status == NotificationStatus.pending
    assert notification.title == "Heads up"
    assert notification.body == "Water the plants"
    assert notification.kind == ReminderKind.generic
    assert notification.dismissible is True
    assert notification.snooze_minutes == []
    assert db_session.query(Notification).count() == 1


def test_push_notification_defaults_title_to_reminder(db_session, user):
    notification = push_notification(db_session, user, body="Stand up and stretch")
    assert notification.title == "Reminder"


def test_push_notification_each_call_gets_a_distinct_dedupe_key(db_session, user):
    first = push_notification(db_session, user, body="First")
    second = push_notification(db_session, user, body="Second")

    assert first.dedupe_key != second.dedupe_key
    assert db_session.query(Notification).count() == 2


def test_push_notification_rejects_non_dismissible_without_snooze(db_session, user):
    with pytest.raises(ValueError):
        push_notification(db_session, user, body="Take medication", dismissible=False, snooze_minutes=[])


def test_push_notification_allows_non_dismissible_with_snooze(db_session, user):
    notification = push_notification(
        db_session, user, body="Take medication", dismissible=False, snooze_minutes=[5, 15]
    )
    assert notification.dismissible is False
    assert notification.snooze_minutes == [5, 15]
