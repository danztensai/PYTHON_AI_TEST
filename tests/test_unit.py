"""Unit tests for users, tasks, strategies, and executor."""

from __future__ import annotations

import pytest

from app.executor import TaskExecutor
from app.models import Task
from app.strategies import (
    STRATEGY_REGISTRY,
    BackupStrategy,
    DeleteStrategy,
    SyncStrategy,
    get_strategy,
    list_actions,
)
from app.tasks import TaskService
from app.users import QuotaService, UserService


@pytest.mark.asyncio
async def test_create_user_and_duplicate_rejection(db_session):
    users = UserService(db_session)
    user = await users.create_user(name="carol", quota=2)
    assert user.id is not None
    assert user.name == "carol"
    assert user.quota == 2

    with pytest.raises(ValueError, match="already exists"):
        await users.create_user(name="carol", quota=1)


@pytest.mark.asyncio
async def test_quota_enforcement_and_remaining(db_session):
    users = UserService(db_session)
    user = await users.create_user(name="dave", quota=2)
    quota = QuotaService(db_session)

    assert await quota.can_execute(user) is True
    assert await quota.remaining_quota(user) == 2
    assert await quota.get_executed_today(user.id) == 0

    await quota.record_execution(user)
    assert await quota.remaining_quota(user) == 1
    assert await quota.can_execute(user) is True

    await quota.record_execution(user)
    assert await quota.remaining_quota(user) == 0
    assert await quota.can_execute(user) is False
    assert await quota.get_executed_today(user.id) == 2


@pytest.mark.asyncio
async def test_multiple_tasks_per_user_with_dict_params(db_session):
    users = UserService(db_session)
    await users.create_user(name="eve", quota=10)
    tasks = TaskService(db_session)

    t1 = await tasks.create_task(
        username="eve",
        time="09:00",
        action="sync",
        target="/a",
        params={"retries": 3, "delay": 0},
    )
    t2 = await tasks.create_task(
        username="eve",
        time="10:00",
        action="backup",
        target="/b",
        params={"destination": "/b.bak"},
    )

    listed = await tasks.list_tasks(username="eve")
    assert len(listed) == 2
    assert t1.params == {"retries": 3, "delay": 0}
    assert t2.params == {"destination": "/b.bak"}
    assert {t.id for t in listed} == {t1.id, t2.id}


@pytest.mark.asyncio
async def test_list_due_tasks_by_hhmm(seeded_session):
    tasks = TaskService(seeded_session)
    due = await tasks.list_due_tasks("12:00")
    assert len(due) == 3
    assert [t.action for t in due] == ["sync", "backup", "delete"]

    none_due = await tasks.list_due_tasks("13:00")
    assert none_due == []


def test_strategy_registry():
    assert set(STRATEGY_REGISTRY.keys()) == {"sync", "backup", "delete"}
    assert list_actions() == ["backup", "delete", "sync"]
    assert isinstance(get_strategy("sync"), SyncStrategy)
    assert isinstance(get_strategy("backup"), BackupStrategy)
    assert isinstance(get_strategy("delete"), DeleteStrategy)
    assert get_strategy("unknown") is None


@pytest.mark.asyncio
async def test_executor_success_then_quota_exceeded(db_session):
    users = UserService(db_session)
    user = await users.create_user(name="frank", quota=1)
    tasks = TaskService(db_session)
    t1 = await tasks.create_task(
        username="frank", time="08:00", action="sync", target="/one"
    )
    t2 = await tasks.create_task(
        username="frank", time="08:00", action="sync", target="/two"
    )
    # Reload with user relationship
    t1 = await tasks.get_by_id(t1.id)
    t2 = await tasks.get_by_id(t2.id)

    executor = TaskExecutor(db_session)
    r1 = await executor.execute(t1)
    assert r1["status"] == "success"

    r2 = await executor.execute(t2)
    assert r2["status"] == "quota_exceeded"
    assert "exceeded quota" in r2["message"]


@pytest.mark.asyncio
async def test_unknown_action_does_not_consume_quota(db_session):
    users = UserService(db_session)
    user = await users.create_user(name="gina", quota=1)
    tasks = TaskService(db_session)
    task = await tasks.create_task(
        username="gina", time="11:00", action="explode", target="/nope"
    )
    task = await tasks.get_by_id(task.id)

    executor = TaskExecutor(db_session)
    result = await executor.execute(task)
    assert result["status"] == "error"
    assert "Unknown action" in result["message"]

    quota = QuotaService(db_session)
    assert await quota.get_executed_today(user.id) == 0
    assert await quota.remaining_quota(user) == 1


@pytest.mark.asyncio
async def test_strategies_execute_without_error(db_session):
    users = UserService(db_session)
    await users.create_user(name="harry", quota=5)
    tasks = TaskService(db_session)

    specs = [
        ("sync", "/data", {"retries": 1, "delay": 0}),
        ("backup", "/srv", {"destination": "/srv.bak"}),
        ("delete", "/tmp", {"dry_run": True}),
    ]
    for action, target, params in specs:
        task = await tasks.create_task(
            username="harry",
            time="07:00",
            action=action,
            target=target,
            params=params,
        )
        task = await tasks.get_by_id(task.id)
        strategy = get_strategy(action)
        assert strategy is not None
        await strategy.execute(task)
