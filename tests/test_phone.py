import pytest

from app.routers import phone


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
async def test_ring_phone_sends_ring_message_when_connected(user, monkeypatch):
    fake_manager = FakeConnectionManager({user.id})
    monkeypatch.setattr(phone, "manager", fake_manager)

    result = await phone.ring_phone(user)

    assert result.delivered is True
    assert fake_manager.sent == [(user.id, {"type": "ring"})]


@pytest.mark.asyncio
async def test_ring_phone_reports_not_delivered_when_disconnected(user, monkeypatch):
    fake_manager = FakeConnectionManager(set())
    monkeypatch.setattr(phone, "manager", fake_manager)

    result = await phone.ring_phone(user)

    assert result.delivered is False
