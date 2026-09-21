"""Shared fixtures for unit, API, and A/B tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import Task, User  # noqa: F401 — register metadata
from app.tasks import TaskService
from app.users import UserService

SEED_USERS = [
    {"name": "alice", "quota": 3},
    {"name": "bob", "quota": 5},
]

SEED_TASKS = [
    {"user": "alice", "time": "12:00", "action": "sync", "target": "/data/x", "params": {}},
    {"user": "bob", "time": "12:00", "action": "backup", "target": "/srv/y", "params": {}},
    {
        "user": "alice",
        "time": "12:00",
        "action": "delete",
        "target": "/tmp/z",
        "params": {"dry_run": True},
    },
]


async def _seed(session: AsyncSession) -> None:
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


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def db_session(session_factory) -> AsyncGenerator[AsyncSession, None]:
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def seeded_session(session_factory) -> AsyncGenerator[AsyncSession, None]:
    async with session_factory() as session:
        await _seed(session)
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(session_factory) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    # httpx>=0.28 dropped lifespan=; default is off (no app lifespan).
    # Older httpx: ASGITransport(app=app, lifespan="off")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def seeded_client(session_factory) -> AsyncGenerator[AsyncClient, None]:
    async with session_factory() as session:
        await _seed(session)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
