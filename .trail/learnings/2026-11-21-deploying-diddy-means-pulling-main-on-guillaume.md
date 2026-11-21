---
title: "Deploying Diddy means pulling main on the server, migrating, restarting it in its tmux pane, and copying a locally built frontend"
author: Guillaume
date: 2026-11-21
branch: main
id: l-ed3c45f2
scope: repo
status: active
src: agent
touches:
  - README.md
---

## Decided
- Diddy runs on the same VPS as Hibou (ubuntu@n8n.iocraft.org), from a git checkout in ~/diddy/diddy-server that is updated only by `git pull --ff-only origin main`. So a feature branch is merged into main locally (`--no-ff`, "Merge branch '…'") and pushed to GitHub first.
- Order: back up diddy.db (`cp -p diddy.db diddy.db.pre-<what>-<date>.bak`; there is no sqlite3 on the host), pull, `uv run alembic upgrade head`, then restart.
- No systemd unit: uvicorn runs in tmux pane 1:0.0 (`uv run uvicorn app.main:app --port 8090`, loopback only). Restart with `tmux send-keys -t 1:0.0 C-c`, wait until port 8090 is free, send the same command again, then poll /health.
- The server has no node. Build the frontend on the laptop with `VITE_API_BASE= npm run build` (empty: nginx serves the API on the same origin) and `rsync -a --delete dist/` into ~/diddy/diddy-server/frontend/dist/, the nginx root for diddy.iocraft.org.

## Watch out
- Without VITE_API_BASE set (even empty), the build calls http://localhost:8000.
- uvicorn's own access log (the tmux scrollback) prints the WebSocket URL, and older phone apps put their API key in the query string there. nginx keeps /ws out of its log, but uvicorn doesn't.
- An nginx location lists the API prefixes explicitly: a new top-level route needs adding to /etc/nginx/sites-enabled/diddy-server.conf.

In the code: deploy/nginx.conf.example, README.md "Deployment"; on the host: ~/diddy/diddy-server, /etc/nginx/sites-enabled/diddy-server.conf.
