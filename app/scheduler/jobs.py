import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import settings
from app.db import SessionLocal
from app.notify.dispatcher import dispatch_pending, requeue_unacked, requeue_undelivered
from app.scheduler.daily import run_daily_schedule_tick
from app.scheduler.ics import run_all_ics_ticks

logger = logging.getLogger("diddy.scheduler")


def _daily_tick() -> None:
    with SessionLocal() as db:
        run_daily_schedule_tick(db)


def _ics_tick() -> None:
    with SessionLocal() as db:
        run_all_ics_ticks(db)


async def _dispatch_tick() -> None:
    with SessionLocal() as db:
        await dispatch_pending(db)


def _requeue_tick() -> None:
    with SessionLocal() as db:
        requeue_unacked(db)


def _requeue_undelivered_tick() -> None:
    with SessionLocal() as db:
        requeue_undelivered(db)


def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(_daily_tick, "interval", seconds=settings.daily_tick_seconds, id="daily_tick")
    scheduler.add_job(_ics_tick, "interval", seconds=settings.ics_refresh_seconds, id="ics_tick")
    scheduler.add_job(_dispatch_tick, "interval", seconds=settings.dispatch_tick_seconds, id="dispatch_tick")
    scheduler.add_job(
        _requeue_tick, "interval", seconds=settings.dispatch_tick_seconds, id="requeue_tick"
    )
    scheduler.add_job(
        _requeue_undelivered_tick,
        "interval",
        seconds=settings.dispatch_tick_seconds,
        id="requeue_undelivered_tick",
    )
    return scheduler
