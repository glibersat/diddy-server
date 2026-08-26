"""Admin CLI for setting up the server's own Signal account - the account app/notify/signal.py
sends notifications from. Thin wrapper around signal-cli
(https://github.com/AsamK/signal-cli), which must be installed and on PATH (or pointed at via
DIDDY_SIGNAL_CLI_BIN / DIDDY_SIGNAL_CLI_CONFIG_DIR - see app/config.py).

Two ways to get an account:

1. Link as a secondary device on a Signal account you already use day to day (like linking
   Signal Desktop) - no CAPTCHA needed, the easiest path for a self-hosted server:

       uv run diddy-signal link
       # scan the printed QR code: Signal app -> Settings -> Linked devices -> Link new device
       uv run diddy-signal status

2. Register a brand new number outright. Needs a CAPTCHA token from
   https://signalcaptchas.org/registration/generate.html (solve it, then copy the
   "signalcaptcha://..." token out of the redirect URL):

       uv run diddy-signal register +15551234567 --captcha <token>
       # a verification code arrives by SMS (or --voice for a phone call)
       uv run diddy-signal verify +15551234567 123456

Either way, once `status` shows the account registered, put its number in .env:

    DIDDY_SIGNAL_ACCOUNT=+15551234567

and set each user's `signal_number` (the number *they* want messaged) via `PATCH /users/me`.
"""

import argparse
import subprocess
import sys

from app.config import settings


def _base_cmd(account: str | None = None) -> list[str]:
    cmd = [settings.signal_cli_bin]
    if settings.signal_cli_config_dir:
        cmd += ["--config", settings.signal_cli_config_dir]
    if account:
        cmd += ["-a", account]
    return cmd


def _run(cmd: list[str]) -> int:
    """Runs signal-cli with stdio inherited, not captured - QR codes, prompts, and error output
    all show up directly in the admin's terminal, exactly as if they'd run signal-cli by hand."""
    print(f"$ {' '.join(cmd)}", file=sys.stderr)
    try:
        return subprocess.run(cmd).returncode
    except FileNotFoundError:
        print(
            f"error: {settings.signal_cli_bin!r} not found - install signal-cli "
            "(https://github.com/AsamK/signal-cli) or set DIDDY_SIGNAL_CLI_BIN",
            file=sys.stderr,
        )
        return 1


def cmd_link(args: argparse.Namespace) -> int:
    return _run(_base_cmd() + ["link", "-n", args.device_name])


def cmd_register(args: argparse.Namespace) -> int:
    cmd = _base_cmd(args.number) + ["register", "--captcha", args.captcha]
    if args.voice:
        cmd.append("--voice")
    return _run(cmd)


def cmd_verify(args: argparse.Namespace) -> int:
    return _run(_base_cmd(args.number) + ["verify", args.code])


def cmd_status(args: argparse.Namespace) -> int:  # noqa: ARG001
    print(f"DIDDY_SIGNAL_ACCOUNT = {settings.signal_account or '(not set)'}")
    return _run(_base_cmd() + ["listAccounts"])


def cmd_send(args: argparse.Namespace) -> int:
    if not settings.signal_account:
        print(
            "error: DIDDY_SIGNAL_ACCOUNT is not set - run `diddy-signal link` "
            "(or `register` + `verify`) first",
            file=sys.stderr,
        )
        return 1
    return _run(_base_cmd(settings.signal_account) + ["send", "-m", args.message, args.to])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="diddy-signal", description="Configure the server's Signal account")
    sub = parser.add_subparsers(dest="command", required=True)

    p_link = sub.add_parser("link", help="link as a secondary device on an existing Signal account (no CAPTCHA)")
    p_link.add_argument("--device-name", default="diddy-server")
    p_link.set_defaults(func=cmd_link)

    p_register = sub.add_parser("register", help="register a brand new number (needs a CAPTCHA token)")
    p_register.add_argument("number", help="E.164 phone number, e.g. +15551234567")
    p_register.add_argument(
        "--captcha", required=True, help="token from https://signalcaptchas.org/registration/generate.html"
    )
    p_register.add_argument("--voice", action="store_true", help="request a voice call instead of SMS")
    p_register.set_defaults(func=cmd_register)

    p_verify = sub.add_parser("verify", help="verify the SMS/voice code sent after `register`")
    p_verify.add_argument("number")
    p_verify.add_argument("code")
    p_verify.set_defaults(func=cmd_verify)

    p_status = sub.add_parser("status", help="show the configured account and signal-cli's registered accounts")
    p_status.set_defaults(func=cmd_status)

    p_send = sub.add_parser("send", help="send a test message from the configured account")
    p_send.add_argument("to", help="recipient E.164 phone number")
    p_send.add_argument("message")
    p_send.set_defaults(func=cmd_send)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
