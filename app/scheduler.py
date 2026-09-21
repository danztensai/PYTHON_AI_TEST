"""Simple HH:MM daily scheduler using APScheduler."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.db import AsyncSessionLocal
from app.executor import TaskExecutor
from app.tasks import TaskService

logger = logging.getLogger(__name__)


class TaskScheduler:
    """
    Minute-tick scheduler.

    Loads enabled tasks whose `time` matches the current HH:MM and runs them
    through TaskExecutor. Deduplicates runs within the same minute for a
    single-process deployment.
    """

    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler()
        self._last_run_minute: str | None = None
        self._lock = asyncio.Lock()

    def start(self) -> None:
        self._scheduler.add_job(
            self._tick,
            trigger="interval",
            seconds=60,
            id="task_minute_tick",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        # Also run immediately so a just-started server can catch the current minute
        self._scheduler.add_job(
            self._tick,
            trigger="date",
            run_date=datetime.now(),
            id="task_startup_tick",
            replace_existing=True,
        )
        self._scheduler.start()
        logger.info("TaskScheduler started (interval=60s)")

    def stop(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("TaskScheduler stopped")

    async def _tick(self) -> None:
        async with self._lock:
            now = datetime.now()
            hhmm = now.strftime("%H:%M")
            minute_key = now.strftime("%Y-%m-%d %H:%M")

            if self._last_run_minute == minute_key:
                logger.debug("Skipping duplicate tick for %s", minute_key)
                return

            self._last_run_minute = minute_key
            logger.debug("Scheduler tick at %s", hhmm)

            async with AsyncSessionLocal() as session:
                try:
                    task_service = TaskService(session)
                    due_tasks = await task_service.list_due_tasks(hhmm)
                    if not due_tasks:
                        await session.commit()
                        return

                    logger.info("Found %s due task(s) at %s", len(due_tasks), hhmm)
                    executor = TaskExecutor(session)

                    # Sequential per tick so quota checks stay accurate for
                    # the same user with multiple due tasks.
                    results = []
                    for task in due_tasks:
                        result = await executor.execute(task)
                        results.append(result)

                    await session.commit()
                    logger.info(
                        "Tick %s finished: %s",
                        hhmm,
                        [(r["task_id"], r["status"]) for r in results],
                    )
                except Exception:
                    await session.rollback()
                    logger.exception("Scheduler tick failed at %s", hhmm)
                    raise
