import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import heart_rate, ics_sources, notifications, phone, schedules, users, ws
from app.scheduler.jobs import build_scheduler

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Schema is owned by Alembic now, not created here - run `alembic upgrade head` before
    # starting the app (see README.md's "Database migrations" section).
    scheduler = build_scheduler()
    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown()


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
app.include_router(notifications.router)
app.include_router(heart_rate.router)
app.include_router(phone.router)
app.include_router(ws.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
