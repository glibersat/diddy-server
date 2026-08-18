# Architecture

Status snapshot as of 2026-08-06. Written so a fresh session (or a cleared context) can pick up
the project without re-deriving any of this.

## What this is

A per-user notification backend for ADHD-friendly watch reminders. It decides *when* a reminder
is due (two criteria so far) and pushes it to the wearer's watch via a companion phone app,
tracking whether the wearer actually acknowledged it.

Sibling repos in `/home/glibersat/Sources/diddy/`:
- `InfiniSim/InfiniTime/` — the watch firmware (InfiniTime fork) and simulator. Its
  `doc/ReminderService.md` defines the BLE contract this server's delivery protocol mirrors.
- `companion-android/` — the phone app that relays between this server and the watch over BLE.
  Its `docs/backend-protocol.md` is the authoritative spec for the WebSocket protocol described
  below; this server is the "backend" side of that doc.

**When touching delivery/protocol code, read those two docs first** — this file summarizes them
but they're the source of truth, and the companion app / firmware are developed independently.

## Delivery protocol (the load-bearing decision)

Originally built against generic FCM/APNs push, then rebuilt once the companion app's actual
protocol was found. Delivery is **not** push notifications — it's a persistent WebSocket:

- Companion app connects to `ws://<host>/ws?api_key=<user's api key>` and stays connected
  (auto-reconnect with backoff is the phone's job, not this server's).
- Backend → phone: `{"type": "trigger", "notification_id": ..., "kind": ..., "dismissible": ...,
  "snoozeMinutes": [...], "title": ..., "body": ...}` for anything with no useful lead time (a
  `manual` push, or already due by dispatch time). For anything with a future fire time, `{"type":
  "schedule", "notification_id": ..., "fireAt": <epoch>, ...}` instead, sent as soon as the
  `Notification` row exists rather than waiting until it's due — the phone relays this as a BLE
  Schedule write, which the watch stores and fires **locally**, off its own clock, independent of
  any connection at fire time. `{"type": "cancel", "notification_id": ...}` retracts a `schedule`
  that hasn't fired yet (rule edited/removed after it was pushed). All three are fire-and-forget —
  sending one doesn't mean the watch showed/stored it, and if the phone isn't BLE-connected to the
  watch it's silently dropped with no error back to us.
- Phone → backend: `{"type": "ack", "notification_id": ..., "action": "snoozed"|"dismissed",
  "snoozedMinutes": int}`, sent when the wearer explicitly snoozes or dismisses on-watch —
  including well after the fact, since the watch itself now persists and replays an ack produced
  while disconnected (indicate-based Ack characteristic, see `ReminderService.md`). Matched by
  `notification_id` directly (`app/notify/ack.py::record_ack`) — no longer "the most recently
  `sent` notification for that user"; once a reminder can be scheduled ahead and fired while fully
  offline, more than one can plausibly be outstanding at once. `notification_id` can still be null
  if the phone couldn't resolve it (e.g. app process restarted since the `schedule` was sent) —
  logged, not applied to any row.
- There is no ack for "reminder timed out," "was replaced by a newer trigger/schedule," or
  "re-fired after a snooze expires" — snooze re-arming happens entirely on-watch, invisible to the
  backend.
- Invariant carried over from the firmware (`ReminderController::Options`): if `dismissible` is
  `false`, `snooze_minutes` must be non-empty, or the wearer could never clear it. Enforced in
  `app/schemas.py::_ReminderOptionsMixin`.

Because delivery has no guarantee and acks are the only proof of confirmation, unacknowledged
notifications are periodically **resent**: `app/notify/dispatcher.py::requeue_unacked` flips a
`sent` notification back to `pending` once `DIDDY_ACK_TIMEOUT_SECONDS` has passed with no ack,
up to `DIDDY_MAX_SEND_ATTEMPTS` before giving up (`status = failed`). This is the "make sure the
reminder was actually done" mechanism.

Undelivered notifications (phone connected to the backend, but not to the watch over BLE - see
above) don't have to wait out `requeue_undelivered`'s `DIDDY_DELIVERY_TIMEOUT_SECONDS` timeout in
the common case: the companion app sends a `watch_ready` message as soon as its BLE connection to
the watch comes up (including reconnects), and `app/notify/dispatcher.py::resend_now` (wired in
`app/routers/ws.py`) immediately retries anything `sent`-but-not-`delivered` for that user. The
timeout-based `requeue_undelivered` job is still the fallback for when `watch_ready` itself
doesn't arrive.

## Data model (`app/models.py`)

- `User(id, email, api_key, timezone)` — one API key per user, sent as `X-API-Key` on HTTP
  requests and as a query param on the WebSocket. No device/push-token table — a device is just
  "currently has a WebSocket open," tracked in memory, not persisted.
- `DailySchedule` — criterion #1. `time_of_day` (`"HH:MM"`, evaluated in the user's `timezone`),
  `weekdays_mask` (bit 0 = Monday), `message`, plus reminder options (`kind`, `dismissible`,
  `snooze_minutes`) that get copied onto the `Notification` when it fires.
- `IcsSource` — criterion #2. `url_or_path` (http(s) URL or local file path), `offsets_minutes`
  (e.g. `[30, 15]` = remind 30 and 15 minutes before each event), `refresh_minutes` for how often
  to re-fetch/re-parse, plus the same reminder-option fields as `DailySchedule`.
- `Notification` — the outbox/audit log, and the only thing the scheduler and the dispatcher
  share. `rule_type` + `rule_id` point back at whichever rule produced it; `dedupe_key` is a
  unique constraint that makes "decide this is due" idempotent (see below). `status` is
  `pending → sent → acked`, or `failed` if delivery/ack never happens within the retry budget.

**Extensibility seam for the planned GenAI summary feature**: a new rule type is just a new table
+ a new "decide it's due" scheduler job that inserts `Notification` rows with its own
`rule_type` and a stable `dedupe_key`. It does not touch the WebSocket/dispatch/ack code at all —
that's the whole point of routing everything through `Notification`.

## Scheduler (`app/scheduler/`, wired in `app/scheduler/jobs.py`)

Four APScheduler jobs (`AsyncIOScheduler`, started/stopped in `app/main.py`'s lifespan):

| Job | Interval (default) | Does |
|---|---|---|
| `_daily_tick` | 60s (`DIDDY_DAILY_TICK_SECONDS`) | `daily.py::run_daily_schedule_tick` — for each enabled `DailySchedule`, computes its *next* occurrence (today's if still upcoming, otherwise the next enabled weekday) and inserts a `Notification` for it ahead of time, with `scheduled_for` set to that future fire time (dedupe key = `daily:{schedule_id}:{occurrence_date}`, so re-running before the next occurrence rolls into view is a no-op). |
| `_ics_tick` | 300s (`DIDDY_ICS_REFRESH_SECONDS`) | `ics.py::run_all_ics_ticks` — for each `IcsSource` due for refresh, fetches + parses the ICS (including basic `RRULE` expansion via `dateutil`), and for each event×offset seen within the lookahead window (not yet started), inserts a `Notification` ahead of its actual trigger time (dedupe key includes event UID + occurrence start + offset). |
| `_dispatch_tick` | 30s (`DIDDY_DISPATCH_TICK_SECONDS`) | `dispatcher.py::dispatch_pending` (async) — sends every `pending` `Notification` over the recipient's WebSocket(s) via `ConnectionManager`, as a `trigger` (already due, or a `manual` push) or a `schedule` (future `scheduled_for`) — see `dispatcher.py::_payload_for`. |
| `_requeue_tick` | 30s | `dispatcher.py::requeue_unacked` — the resend-until-acked logic described above. |

Decide-it's-due (`daily.py`, `ics.py`) and deliver-it (`dispatcher.py`) are deliberately separate
jobs talking only through the `Notification` table — this is the seam future rule types use.

**Known gap: no `cancel` on edit/delete of an already-pushed schedule.** Because occurrences are
now enqueued and pushed (as `schedule`) well ahead of their fire time, a `PATCH`/`DELETE` on a
`DailySchedule` or `IcsSource` (`app/routers/schedules.py`, `app/routers/ics_sources.py`) can
land *after* the watch already has the old version stored. `dispatcher.py::send_cancel` exists as
a primitive for this (sends `{"type": "cancel", "notification_id": ...}`, see
`companion-android/docs/backend-protocol.md`), but nothing calls it yet — the update/delete
handlers don't look up affected `pending`/`sent` `Notification` rows and cancel them. Today the
watch just keeps the stale entry until it fires as originally scheduled (or a later `schedule`
with the same `notification_id` happens to replace it, which won't occur for a genuinely deleted
schedule). Wiring this up means: on `PATCH`/`DELETE`, query `Notification` rows for that
`rule_type`/`rule_id` still `pending` or `sent`-but-not-yet-due, call `send_cancel` on each, and
decide whether to delete or re-enqueue them depending on whether the rule was edited vs removed.

Known sharp edge already hit once and fixed: SQLite round-trips lose Python `datetime` tzinfo and
plain-`String` enum columns lose their Python enum wrapper on any re-query/refresh. Don't do
naive `datetime` arithmetic or call `.value` on a column typed `Mapped[SomeStrEnum] =
mapped_column(String, ...)` — treat the attribute as "might be a bare `str` at any time" (our
enums subclass `str` specifically so this degrades safely).

## API surface

- `POST /users`, `GET /users/me`
- `POST/GET/PATCH/DELETE /schedules` (`app/routers/schedules.py`)
- `POST/GET/PATCH/DELETE /ics-sources` (`app/routers/ics_sources.py`)
- `GET /notifications` — outbox/audit log including ack status (`app/routers/notifications.py`)
- `WS /ws?api_key=...` (`app/routers/ws.py`) — companion app connection

Auth is `X-API-Key` header (`app/auth.py::get_current_user`) for HTTP, `api_key` query param for
the WebSocket. Deliberately minimal per an earlier decision — no signup/session flow.

## Stack & layout

FastAPI + SQLAlchemy 2.0 + SQLite + APScheduler, Python ≥3.11, dependencies in `pyproject.toml`
managed with `uv` (`uv sync --extra dev`, venv at `.venv/`). Full layout and how to run/test:
see `README.md`.

## What's not built yet

- The companion app's `BackendClient.kt` isn't wired against this server's `/ws` — protocol
  matches on paper and was smoke-tested with a throwaway Python WS client, not the real app.
- No GenAI summary rule type yet (the planned third criterion — daily summary of
  emails/appointments). Slots in as described above.
- No auth beyond a bare API key; fine for a trusted LAN, not for anything exposed further.
