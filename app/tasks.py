"""Task repository and service helpers."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Task, User
from app.users import UserService

logger = logging.getLogger(__name__)


class TaskService:
    """Create and query tasks. A user may own many tasks."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserService(session)

    async def create_task(
        self,
        username: str,
        time: str,
        action: str,
        target: str,
        params: dict[str, Any] | None = None,
        enabled: bool = True,
    ) -> Task:
        user = await self.users.get_by_name(username)
        if user is None:
            raise ValueError(f"User '{username}' not found")

        task = Task(
            user_id=user.id,
            time=time,
            action=action,
            target=target,
            params=params or {},
            enabled=enabled,
        )
        self.session.add(task)
        await self.session.flush()
        # Ensure relationship is available for response mapping
        await self.session.refresh(task, attribute_names=["user"])
        logger.info(
            "Created task id=%s user=%s time=%s action=%s target=%s",
            task.id,
            username,
            time,
            action,
            target,
        )
        return task

    async def get_by_id(self, task_id: int) -> Task | None:
        result = await self.session.execute(
            select(Task).options(selectinload(Task.user)).where(Task.id == task_id)
        )
        return result.scalar_one_or_none()

    async def list_tasks(self, username: str | None = None) -> list[Task]:
        stmt = select(Task).options(selectinload(Task.user))
        if username is not None:
            stmt = stmt.join(User).where(User.name == username)
        stmt = stmt.order_by(Task.id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_due_tasks(self, hhmm: str) -> list[Task]:
        """Return enabled tasks scheduled for the given HH:MM."""
        result = await self.session.execute(
            select(Task)
            .options(selectinload(Task.user))
            .where(Task.enabled.is_(True), Task.time == hhmm)
            .order_by(Task.id)
        )
        return list(result.scalars().all())
