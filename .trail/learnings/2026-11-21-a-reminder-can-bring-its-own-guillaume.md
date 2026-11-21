---
title: "A reminder can bring its own watch button labels and a « not today » answer, and the watch keeps no schedule of its own"
author: Guillaume
date: 2026-11-21
branch: feature/reminder-labels
id: l-952cda34
scope: repo
status: active
src: agent
touches:
  - app/schemas.py
  - app/notify/dispatcher.py
  - frontend/src/views/NotificationsView.vue
---

## Decided
- 2026-11-21, the user: reminders from The Owl get their own button labels on the watch (labels {done, later, decline}, ASCII, at most 16 characters, reminders only, never alerts). A decline label adds a third "not today" button, acked as "declined". The Owl uses Fait / Plus tard / Pas aujourd'hui for tasks, OK / +15 min for things to know, and Maintenant / Plus tard / Pas aujourd'hui for its daily « Brief du matin ? ». Medication schedules carry no labels, so the meds screen (small corner DONE, hard to dismiss) stays as it was. The user required that.

## Tried and ruled out
- On-watch offline scheduling (Schedule/Cancel characteristics; InfiniTime and companion branches feature/reminder-offline-scheduling): dropped by the user on 2026-11-21. The firmware line is feature/reminder-choices on top of feature/find-my-phone-app-v2; don't build on the offline line.

## Watch out
- Séverine pressed DONE on tasks because the watch offered only +5 / +15 / DONE. Before this change, a "dismissed" ack on a task doesn't prove it was done.
- The phone app reads acks in both the 2-byte form (this firmware) and the 6-byte form (the dropped offline line).
- The InfiniTime DFU package only builds with the firmware virtualenv on PATH as an absolute path (make changes directory, so a relative one breaks). Without it, imgtool fails on a missing cbor and the old zip stays in place.

In the code: app/schemas.py ReminderLabels, NotificationCreate.labels; app/notify/dispatcher.py adds "labels" to the trigger; migration c4d8a1f2e9b7; frontend/src/views/NotificationsView.vue status()/buttons(). Firmware build: cd InfiniSim/InfiniTime/build-firmware && PATH=$(realpath ../.venv-fw/bin):$PATH make pinetime-mcuboot-app. Simulator check: INFINISIM_REMINDER="kind|easyDismiss|snooze|title|body|done|later|decline" INFINISIM_SHOT_AND_EXIT=1 SDL_VIDEODRIVER=offscreen InfiniSim/build/infinisim.
