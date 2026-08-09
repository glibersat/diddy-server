# Diddy Notification Server

Per-user notification backend for ADHD-friendly watch reminders. Two criteria today:

- **Daily schedule** (`/schedules`) — fire a message every day at a fixed local time, e.g. "take
  your meds".
- **ICS reminders** (`/ics-sources`) — parse a personal ICS export and remind N minutes before
  each event.

Delivery follows the companion app's protocol
(`../companion-android/docs/backend-protocol.md`, mirroring InfiniTime's BLE
`doc/ReminderService.md`): the backend pushes a `trigger` JSON message over a persistent
per-user WebSocket at `/ws?api_key=...`, and the phone relays a `snoozed`/`dismissed` `ack`
back once the wearer actually acts on it. There's no delivery guarantee in the protocol itself,
so unacked triggers are automatically resent (`DIDDY_ACK_TIMEOUT_SECONDS`, capped at
`DIDDY_MAX_SEND_ATTEMPTS`).

`rule_type` + `dedupe_key` on the `Notification` table is the seam a future rule type (e.g. a
GenAI daily-summary job) plugs into without touching delivery.

## Running

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env  # adjust as needed
uvicorn app.main:app --reload
```

## Testing

```bash
. .venv/bin/activate
pytest
```

## API

- `POST /users` — create a user, returns `api_key` (send it as `X-API-Key` on every other call)
- `GET /users/me`
- `POST/GET/PATCH/DELETE /schedules` — daily schedules
- `POST/GET/PATCH/DELETE /ics-sources` — ICS reminder sources
- `GET /notifications` — outbox/audit log, including ack status
- `WS /ws?api_key=...` — companion app connection: receives `trigger`, sends `ack`

## Frontend

`frontend/` is a Vite + Vue 3 + TypeScript app for configuring daily reminders and ICS sources
(create/log in with an API key, then manage `/schedules` and `/ics-sources`). It talks to this
server directly over HTTP, so the backend must be running with CORS enabled (already configured
in `app/main.py`).

```bash
cd frontend
npm install
npm run dev  # http://localhost:5173, expects the API at http://localhost:8000
```

Set `VITE_API_BASE` (e.g. in `frontend/.env.local`) to point at a different backend URL.

## Deployment

For anything beyond your own LAN, terminate TLS in front of uvicorn — the companion app
supports `wss://`/`https://` out of the box (`BackendClient.buildWebSocketUrl` in the
Android app), but nothing here does TLS itself.

1. On the target host, set up the venv and app as in **Running** above, but skip `--reload`.
   Bind uvicorn to loopback only — it should never be reachable except through the proxy —
   and run it detached, e.g. in a `screen`/`tmux` session or with `nohup`:
   ```bash
   nohup uvicorn app.main:app --host 127.0.0.1 --port 8000 >> uvicorn.log 2>&1 &
   disown
   ```
   There's no process supervisor here, so a crash or reboot won't bring it back on its
   own — you're restarting it by hand (`pkill -f 'uvicorn app.main:app'`, then rerun the
   command above) when needed.
2. Point DNS at the host, then set up nginx as a TLS-terminating reverse proxy — copy
   `deploy/nginx.conf.example` to `/etc/nginx/sites-available/diddy`, edit `server_name`,
   symlink into `sites-enabled`, `nginx -t`, `systemctl reload nginx`, then run
   `sudo certbot --nginx -d your-domain.example` to provision the cert (certbot rewrites
   the TLS block and sets up auto-renewal). See the comments in that file for why `/ws`
   needs its own `location` block (Upgrade headers, long timeouts, no access log — the
   `?api_key=...` query param shouldn't land in plaintext logs) and why `/users` is
   rate-limited (it's the one endpoint reachable with no API key at all).
3. In the companion app's server field, enter `https://your-domain.example` — the app maps
   that to `wss://` automatically for the `/ws` connection.

**Known gap:** `POST /users` has no auth beyond being reachable at all — anyone who finds
the host can register an account. Fine for a short-lived first test with a disposable
domain; before running this long-term, that endpoint needs real gating (invite token,
admin-created accounts, etc.) on top of the rate limit in the nginx config.

## License

GPLv3 — see [LICENSE](LICENSE).
