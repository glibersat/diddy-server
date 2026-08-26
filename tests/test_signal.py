import pytest

from app.notify import signal


def test_signal_configured_false_by_default(monkeypatch):
    monkeypatch.setattr(signal.settings, "signal_account", None)
    assert signal.signal_configured() is False


def test_signal_configured_true_when_account_set(monkeypatch):
    monkeypatch.setattr(signal.settings, "signal_account", "+15551234567")
    assert signal.signal_configured() is True


@pytest.mark.asyncio
async def test_send_signal_message_returns_false_when_unconfigured(monkeypatch):
    monkeypatch.setattr(signal.settings, "signal_account", None)

    result = await signal.send_signal_message("+15559876543", "hi")

    assert result is False


class _FakeProcess:
    def __init__(self, returncode: int, stderr: bytes = b""):
        self.returncode = returncode
        self._stderr = stderr

    async def communicate(self):
        return b"", self._stderr


@pytest.mark.asyncio
async def test_send_signal_message_success(monkeypatch):
    monkeypatch.setattr(signal.settings, "signal_account", "+15551234567")
    captured = {}

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        captured["cmd"] = cmd
        return _FakeProcess(returncode=0)

    monkeypatch.setattr(signal.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    result = await signal.send_signal_message("+15559876543", "Take your meds")

    assert result is True
    assert captured["cmd"] == (
        "signal-cli",
        "-a",
        "+15551234567",
        "send",
        "-m",
        "Take your meds",
        "+15559876543",
    )


@pytest.mark.asyncio
async def test_send_signal_message_failure_returns_false(monkeypatch):
    monkeypatch.setattr(signal.settings, "signal_account", "+15551234567")

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        return _FakeProcess(returncode=1, stderr=b"Untrusted identity")

    monkeypatch.setattr(signal.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    result = await signal.send_signal_message("+15559876543", "Take your meds")

    assert result is False


@pytest.mark.asyncio
async def test_send_signal_message_missing_binary_returns_false(monkeypatch):
    monkeypatch.setattr(signal.settings, "signal_account", "+15551234567")

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        raise FileNotFoundError()

    monkeypatch.setattr(signal.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    result = await signal.send_signal_message("+15559876543", "Take your meds")

    assert result is False


def test_cli_args_includes_config_dir_when_set(monkeypatch):
    monkeypatch.setattr(signal.settings, "signal_account", "+15551234567")
    monkeypatch.setattr(signal.settings, "signal_cli_config_dir", "/etc/diddy/signal-cli")

    args = signal._cli_args("send", "-m", "hi", "+15559876543")

    assert args == [
        "signal-cli",
        "--config",
        "/etc/diddy/signal-cli",
        "-a",
        "+15551234567",
        "send",
        "-m",
        "hi",
        "+15559876543",
    ]
