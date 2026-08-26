from app.cli import signal as cli


def test_link_builds_expected_command(monkeypatch):
    captured = {}
    monkeypatch.setattr(cli, "_run", lambda cmd: captured.update(cmd=cmd) or 0)

    exit_code = cli.main(["link", "--device-name", "my-server"])

    assert exit_code == 0
    assert captured["cmd"] == ["signal-cli", "link", "-n", "my-server"]


def test_link_default_device_name(monkeypatch):
    captured = {}
    monkeypatch.setattr(cli, "_run", lambda cmd: captured.update(cmd=cmd) or 0)

    cli.main(["link"])

    assert captured["cmd"] == ["signal-cli", "link", "-n", "diddy-server"]


def test_register_includes_captcha_and_voice_flag(monkeypatch):
    captured = {}
    monkeypatch.setattr(cli, "_run", lambda cmd: captured.update(cmd=cmd) or 0)

    cli.main(["register", "+15551234567", "--captcha", "tok3n", "--voice"])

    assert captured["cmd"] == [
        "signal-cli",
        "-a",
        "+15551234567",
        "register",
        "--captcha",
        "tok3n",
        "--voice",
    ]


def test_verify_builds_expected_command(monkeypatch):
    captured = {}
    monkeypatch.setattr(cli, "_run", lambda cmd: captured.update(cmd=cmd) or 0)

    cli.main(["verify", "+15551234567", "123456"])

    assert captured["cmd"] == ["signal-cli", "-a", "+15551234567", "verify", "123456"]


def test_send_fails_fast_when_no_account_configured(monkeypatch, capsys):
    monkeypatch.setattr(cli.settings, "signal_account", None)

    exit_code = cli.main(["send", "+15559876543", "hello"])

    assert exit_code == 1
    assert "DIDDY_SIGNAL_ACCOUNT is not set" in capsys.readouterr().err


def test_send_uses_configured_account(monkeypatch):
    monkeypatch.setattr(cli.settings, "signal_account", "+15551234567")
    captured = {}
    monkeypatch.setattr(cli, "_run", lambda cmd: captured.update(cmd=cmd) or 0)

    cli.main(["send", "+15559876543", "hello there"])

    assert captured["cmd"] == [
        "signal-cli",
        "-a",
        "+15551234567",
        "send",
        "-m",
        "hello there",
        "+15559876543",
    ]


def test_run_reports_missing_binary(monkeypatch, capsys):
    monkeypatch.setattr(cli.settings, "signal_cli_bin", "does-not-exist-signal-cli")

    exit_code = cli._run(["does-not-exist-signal-cli", "link", "-n", "x"])

    assert exit_code == 1
    assert "not found" in capsys.readouterr().err
