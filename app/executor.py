"""Task executor: quota check, strategy dispatch, logging."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Task
from app.strategies import get_strategy
from app.users import QuotaService

logger = logging.getLogger(__name__)


class TaskExecutor:
    """Execute a single task with quota enforcement and strategy dispatch."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.quota = QuotaService(session)

    async def execute(self, task: Task) -> dict[str, Any]:
        user = task.user
        username = user.name if user is not None else f"user_id={task.user_id}"

        logger.info(
            "Starting task id=%s user=%s action=%s target=%s",
            task.id,
            username,
            task.action,
            task.target,
        )

        strategy = get_strategy(task.action)
        if strategy is None:
            message = f"Unknown action '{task.action}'"
            logger.error(
                "task_id=%s user=%s action=%s target=%s error=%s",
                task.id,
                username,
                task.action,
                task.target,
                message,
            )
            return {"task_id": task.id, "status": "error", "message": message}

        if not await self.quota.can_execute(user):
            message = f"{username} has exceeded quota."
            logger.warning(
                "task_id=%s user=%s action=%s target=%s skipped=%s",
                task.id,
                username,
                task.action,
                task.target,
                message,
            )
            return {"task_id": task.id, "status": "quota_exceeded", "message": message}

        try:
            await strategy.execute(task)
            await self.quota.record_execution(user)
            message = f"Executing {task.action} on {task.target} for {username}"
            logger.info(
                "task_id=%s user=%s action=%s target=%s status=success",
                task.id,
                username,
                task.action,
                task.target,
            )
            return {"task_id": task.id, "status": "success", "message": message}
        except Exception as exc:
            message = f"Execution failed: {exc}"
            logger.exception(
                "task_id=%s user=%s action=%s target=%s status=failure error=%s",
                task.id,
                username,
                task.action,
                task.target,
                exc,
            )
            return {"task_id": task.id, "status": "failure", "message": message}
