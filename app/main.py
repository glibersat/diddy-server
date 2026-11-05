import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import (
    alerts,
    heart_rate,
    ics_sources,
    location,
    notifications,
    phone,
    schedules,
    todo_lists,
    users,
    ws,
)
from app.db import SessionLocal
from app.notify.dispatcher import run_dispatch_loop
from app.scheduler.jobs import build_scheduler

logging.basicConfig(level=logging.INFO)
# At INFO httpx logs every URL it fetches, and a calendar feed's URL is its password.
logging.getLogger("httpx").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Schema is owned by Alembic now, not created here - run `alembic upgrade head` before
    # starting the app (see README.md's "Database migrations" section).
    dispatch_loop = asyncio.create_task(run_dispatch_loop(SessionLocal))
    scheduler = build_scheduler()
    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown()
        dispatch_loop.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await dispatch_loop


app = FastAPI(title="Diddy Notification Server", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users.router)
app.include_router(schedules.router)
app.include_router(ics_sources.router)
app.include_router(todo_lists.router)
app.include_router(notifications.router)
app.include_router(heart_rate.router)
app.include_router(location.router)
app.include_router(phone.router)
app.include_router(alerts.router)
app.include_router(ws.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
