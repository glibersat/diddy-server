import asyncio
import time
from datetime import datetime, UTC

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.websockets import WebSocketDisconnect

from app.db import Base
from app.models import AckAction, Notification, NotificationStatus, RuleType, User
from app.notify import dispatcher
from app.notify.connection_manager import ConnectionManager
from app.notify.queue import enqueue_notification
from app.routers import ws


@pytest.fixture()
def session_factory(monkeypatch, tmp_path):
    # A file, not in-memory: the handler's DB work runs on the threadpool, and each thread needs
    # its own connection to the same database - like production, not one shared connection
    # whose rollback from one thread would wipe another's uncommitted write.
    engine = create_engine(f"sqlite:///{tmp_path / 'ws.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(ws, "SessionLocal", factory)
    return factory


@pytest.fixture()
def ws_user(session_factory):
    with session_factory() as db:
        user = User(email="ada@example.com", timezone="UTC")
        db.add(user)
        db.commit()
        db.refresh(user)
        notification = Notification(
            user_id=user.id,
            rule_type=RuleType.manual,
            rule_id="r",
            dedupe_key="manual:r",
            scheduled_for=datetime.now(UTC),
            title="Reminder",
            body="Take meds",
            status=NotificationStatus.sent,
            sent_at=datetime.now(UTC),
        )
        db.add(notification)
        db.commit()
        return user


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(ws.router)
    return TestClient(app)


def _wait_for_ack(session_factory, expected_action: AckAction) -> None:
    """Messages are handled on the threadpool, so poll while the socket is still open rather
    than asserting after close (which can cut an in-flight handler short in TestClient)."""
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        with session_factory() as db:
            n = db.query(Notification).one()
            if n.status == NotificationStatus.acked:
                assert n.ack_action == expected_action
                return
        time.sleep(0.01)
    pytest.fail("ack was never recorded")


def test_ws_accepts_api_key_header(client, ws_user, session_factory):
    with client.websocket_connect("/ws", headers={"X-API-Key": ws_user.api_key}) as conn:
        conn.send_json({"type": "ack", "action": "dismissed", "snoozedMinutes": 0})
        _wait_for_ack(session_factory, AckAction.dismissed)


def test_ws_still_accepts_query_param_key(client, ws_user, session_factory):
    with client.websocket_connect(f"/ws?api_key={ws_user.api_key}") as conn:
        conn.send_json({"type": "ack", "action": "dismissed", "snoozedMinutes": 0})
        _wait_for_ack(session_factory, AckAction.dismissed)


def test_ws_rejects_missing_or_bad_key(client, ws_user):
    for url, headers in (("/ws", {}), ("/ws", {"X-API-Key": "nope"})):
        with pytest.raises(WebSocketDisconnect) as excinfo:
            with client.websocket_connect(url, headers=headers) as conn:
                conn.receive_text()
        assert excinfo.value.code == 4401


def test_ws_survives_garbage_and_handler_errors(client, ws_user, session_factory, monkeypatch):
    """Non-JSON text, a binary frame and a handler blowing up must each be logged and skipped -
    not close the phone's connection, which would drop the ack that follows."""

    def boom(*args, **kwargs):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(ws, "record_heart_rate", boom)
    with client.websocket_connect("/ws", headers={"X-API-Key": ws_user.api_key}) as conn:
        conn.send_text("not json {")
        conn.send_bytes(b"\x00\x01")
        conn.send_json(["not", "an", "object"])
        conn.send_json({"type": "heart_rate", "bpm": 72, "timestamp": 1735689600000})
        conn.send_json({"type": "ack", "action": "snoozed", "snoozedMinutes": 5})
        _wait_for_ack(session_factory, AckAction.snoozed)


class _StalledSocket:
    def __init__(self):
        self.closed = False

    async def send_json(self, payload):
        await asyncio.sleep(3600)

    async def close(self, code=1000):
        self.closed = True


class _OkSocket:
    def __init__(self):
        self.sent = []

    async def send_json(self, payload):
        self.sent.append(payload)


@pytest.mark.asyncio
async def test_send_to_user_times_out_and_drops_stalled_socket(monkeypatch):
    monkeypatch.setattr("app.notify.connection_manager.settings.ws_send_timeout_seconds", 0.05)
    manager = ConnectionManager()
    stalled, ok = _StalledSocket(), _OkSocket()
    manager._connections["u"] = {stalled, ok}

    assert await asyncio.wait_for(manager.send_to_user("u", {"type": "ring"}), timeout=1) is True
    assert ok.sent == [{"type": "ring"}]
    assert manager._connections["u"] == {ok}
    await asyncio.sleep(0)  # let the background close run
    assert stalled.closed


@pytest.mark.asyncio
async def test_dispatch_loop_sends_as_soon_as_something_is_enqueued(db_session, user, monkeypatch):
    class FakeManager:
        def __init__(self):
            self.sent = []

        def is_connected(self, user_id):
            return True

        async def send_to_user(self, user_id, payload):
            self.sent.append(payload)
            return True

    fake = FakeManager()
    monkeypatch.setattr(dispatcher, "manager", fake)
    monkeypatch.setattr(dispatcher.settings, "dispatch_tick_seconds", 3600)  # only a wake can trigger it
    factory = sessionmaker(bind=db_session.get_bind(), autoflush=False, expire_on_commit=False)

    loop_task = asyncio.create_task(dispatcher.run_dispatch_loop(factory))
    try:
        await asyncio.sleep(0)  # let the loop bind its wake event
        enqueue_notification(
            db_session, user.id, rule_type=RuleType.manual, rule_id="r", dedupe_key="manual:r", title="T", body="B"
        )
        for _ in range(100):
            if fake.sent:
                break
            await asyncio.sleep(0.01)
        assert [p["body"] for p in fake.sent] == ["B"]
    finally:
        loop_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await loop_task
