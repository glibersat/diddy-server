import pytest

from app import schemas
from app.notify import alert
from app.routers import alerts


class FakeConnectionManager:
    """Stands in for the real WebSocket ConnectionManager: records what was "sent"."""

    def __init__(self, connected_users: set[str]):
        self.connected_users = connected_users
        self.sent: list[tuple[str, dict]] = []

    async def send_to_user(self, user_id: str, payload: dict) -> bool:
        if user_id not in self.connected_users:
            return False
        self.sent.append((user_id, payload))
        return True


@pytest.mark.asyncio
async def test_create_alert_sends_alert_message_when_connected(user, monkeypatch):
    fake_manager = FakeConnectionManager({user.id})
    monkeypatch.setattr(alert, "manager", fake_manager)

    result = await alerts.create_alert(schemas.AlertCreate(message="Garage door left open"), user)

    assert result.delivered is True
    assert fake_manager.sent == [(user.id, {"type": "alert", "message": "Garage door left open"})]


@pytest.mark.asyncio
async def test_create_alert_reports_not_delivered_when_disconnected(user, monkeypatch):
    fake_manager = FakeConnectionManager(set())
    monkeypatch.setattr(alert, "manager", fake_manager)

    result = await alerts.create_alert(schemas.AlertCreate(message="Garage door left open"), user)

    assert result.delivered is False
