"""Sends a Signal message from the server's own account (app/config.py::signal_account,
configured via the `diddy-signal` CLI - see app/cli/signal.py) to a user's `signal_number`.

This is a second, independent delivery channel alongside the watch's BLE trigger - see
Notification.signal_sent_at in app/models.py for how app/notify/dispatcher.py avoids re-sending
it on every watch-trigger resend. Fire-and-forget, like ring_phone: once signal-cli hands the
message to Signal's servers, delivery/retry from there is Signal's problem, not ours - there's no
`delivered`/`ack` round trip to track the way there is for the watch.
"""

import asyncio
import logging

from app.config import settings

logger = logging.getLogger("diddy.notify.signal")


def signal_configured() -> bool:
    return bool(settings.signal_account)


def _cli_args(*args: str) -> list[str]:
    cmd = [settings.signal_cli_bin]
    if settings.signal_cli_config_dir:
        cmd += ["--config", settings.signal_cli_config_dir]
    cmd += ["-a", settings.signal_account, *args]
    return cmd


async def send_signal_message(to_number: str, text: str) -> bool:
    if not signal_configured():
        logger.warning("Signal message to %s skipped: no signal_account configured", to_number)
        return False

    cmd = _cli_args("send", "-m", text, to_number)
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
    except FileNotFoundError:
        logger.error("signal-cli binary %r not found - see app/cli/signal.py for setup", settings.signal_cli_bin)
        return False

    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.warning("signal-cli send to %s failed (exit %s): %s", to_number, proc.returncode, stderr.decode(errors="replace").strip())
        return False
    return True
