"""User management and daily quota control."""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import QuotaUsage, User

logger = logging.getLogger(__name__)


class UserService:
    """CRUD helpers for users."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_user(self, name: str, quota: int) -> User:
        existing = await self.get_by_name(name)
        if existing is not None:
            raise ValueError(f"User '{name}' already exists")
        user = User(name=name, quota=quota)
        self.session.add(user)
        await self.session.flush()
        logger.info("Created user name=%s quota=%s id=%s", name, quota, user.id)
        return user

    async def get_by_name(self, name: str) -> User | None:
        result = await self.session.execute(select(User).where(User.name == name))
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: int) -> User | None:
        result = await self.session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()


class QuotaService:
    """Daily per-user execution quota."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _get_or_create_usage(self, user_id: int, usage_date: date | None = None) -> QuotaUsage:
        usage_date = usage_date or date.today()
        result = await self.session.execute(
            select(QuotaUsage).where(
                QuotaUsage.user_id == user_id,
                QuotaUsage.usage_date == usage_date,
            )
        )
        usage = result.scalar_one_or_none()
        if usage is None:
            usage = QuotaUsage(user_id=user_id, usage_date=usage_date, executed=0)
            self.session.add(usage)
            await self.session.flush()
        return usage

    async def get_executed_today(self, user_id: int) -> int:
        usage = await self._get_or_create_usage(user_id)
        return usage.executed

    async def can_execute(self, user: User) -> bool:
        executed = await self.get_executed_today(user.id)
        return executed < user.quota

    async def remaining_quota(self, user: User) -> int:
        executed = await self.get_executed_today(user.id)
        return max(0, user.quota - executed)

    async def record_execution(self, user: User) -> int:
        usage = await self._get_or_create_usage(user.id)
        usage.executed += 1
        await self.session.flush()
        logger.info(
            "Recorded execution user=%s executed_today=%s quota=%s",
            user.name,
            usage.executed,
            user.quota,
        )
        return usage.executed
