"""Seed original alice/bob demo data if the database is empty."""

from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.tasks import TaskService
from app.users import UserService

logger = logging.getLogger(__name__)

SEED_USERS = [
    {"name": "alice", "quota": 3},
    {"name": "bob", "quota": 5},
]

SEED_TASKS = [
    {"user": "alice", "time": "12:00", "action": "sync", "target": "/data/x", "params": {}},
    {"user": "bob", "time": "12:00", "action": "backup", "target": "/srv/y", "params": {}},
    {"user": "alice", "time": "12:00", "action": "delete", "target": "/tmp/z", "params": {"dry_run": True}},
]


async def seed_if_empty(session: AsyncSession) -> None:
    """Insert the original sample users/tasks when no users exist yet."""
    count = await session.scalar(select(func.count()).select_from(User))
    if count and count > 0:
        logger.info("Database already has %s user(s); skipping seed", count)
        return

    users = UserService(session)
    tasks = TaskService(session)

    for item in SEED_USERS:
        await users.create_user(name=item["name"], quota=item["quota"])

    for item in SEED_TASKS:
        await tasks.create_task(
            username=item["user"],
            time=item["time"],
            action=item["action"],
            target=item["target"],
            params=item.get("params", {}),
        )

    await session.commit()
    logger.info("Seeded %s users and %s tasks", len(SEED_USERS), len(SEED_TASKS))
