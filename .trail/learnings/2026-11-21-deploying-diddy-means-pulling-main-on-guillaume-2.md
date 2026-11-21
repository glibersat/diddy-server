---
title: "Deploying Diddy means pulling main on the server and restarting it in its tmux pane, and the watch is flashed from the laptop"
author: Guillaume
date: 2026-11-21
branch: main
id: l-590de76d
scope: repo
status: active
replaces: l-ed3c45f2
src: agent
touches:
  - README.md
---

## Decided
- Diddy runs on the same VPS as Hibou (ubuntu@n8n.iocraft.org), from a git checkout in ~/diddy/diddy-server that is updated only by `git pull --ff-only origin main`. So a feature branch is merged into main locally (`--no-ff`, "Merge branch '…'") and pushed to GitHub first.
- Order: back up diddy.db (`cp -p diddy.db diddy.db.pre-<what>-<date>.bak`; there is no sqlite3 on the host), pull, `uv run alembic upgrade head`, then restart.
- No systemd unit: uvicorn runs in tmux pane 1:0.0 (`uv run uvicorn app.main:app --port 8090`, loopback only). Restart with `tmux send-keys -t 1:0.0 C-c`, wait until port 8090 is free, send the same command again, then poll /health.
- The server has no node. Build the frontend on the laptop with `VITE_API_BASE= npm run build` (empty: nginx serves the API on the same origin) and `rsync -a --delete dist/` into ~/diddy/diddy-server/frontend/dist/, the nginx root for diddy.iocraft.org.
- The watch is flashed from the laptop over Bluetooth with tools/infinitime_dfu.py (bleak, legacy Nordic DFU as InfiniTime's DfuService implements it). Stop the phone app first (adb shell am force-stop org.iocraft.diddy.companion): the watch takes one connection at a time. Reopen the app afterwards by launching it; its BridgeService isn't exported, so `am start-foreground-service` is refused.

## Tried and ruled out
- Flashing from Séverine's phone with Nordic's nRF DFU app (2026-11-21): it stopped at 25% with "GATT CONN TIMEOUT" when the phone was used meanwhile. Her phone is in use; driving its screen over adb is fragile.
- Connecting from the laptop with its old pairing: the watch dropped the link during service discovery. Removing the laptop's pairing (bluetoothctl remove <address>) fixed it; DFU needs no pairing.

## Watch out
- Without VITE_API_BASE set (even empty), the build calls http://localhost:8000.
- uvicorn's own access log (the tmux scrollback) prints the WebSocket URL, and older phone apps put their API key in the query string there. nginx keeps /ws out of its log, but uvicorn doesn't.
- An nginx location lists the API prefixes explicitly: a new top-level route needs adding to /etc/nginx/sites-enabled/diddy-server.conf.
- InfiniTime expects 20-byte DFU packet writes and divides by the packet receipt interval: send opcode 0x08 with a non-zero count before 0x03, or the watch faults.
- After a new image boots, it must be validated on the watch (Settings > Firmware > Validate), or MCUBoot goes back to the old one at the next reboot.

In the code: deploy/nginx.conf.example, README.md "Deployment"; on the host: ~/diddy/diddy-server, /etc/nginx/sites-enabled/diddy-server.conf. Flashing: `uv run --no-project --with bleak python -I tools/infinitime_dfu.py <watch address> <pinetime-mcuboot-app-dfu-*.zip>`.
