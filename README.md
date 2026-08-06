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
