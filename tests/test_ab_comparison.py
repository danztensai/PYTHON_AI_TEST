"""A/B comparison: original in-memory runner vs refactored TaskExecutor."""

from __future__ import annotations

import pytest

from app.executor import TaskExecutor
from app.tasks import TaskService
from app.users import QuotaService, UserService
from legacy.original_runner import run_original


def _outcomes(events: list[dict]) -> list[tuple]:
    return [(e["user"], e["action"], e["target"], e["status"]) for e in events]


def _run_original_with_starting_executed(now_hhmm: str, starting_executed: dict[str, int]) -> dict:
    """Same algorithm as Variant A, but with pre-burned executed counters."""
    users = {
        "alice": {"quota": 3, "executed": starting_executed.get("alice", 0)},
        "bob": {"quota": 5, "executed": starting_executed.get("bob", 0)},
    }
    tasks = [
        {"user": "alice", "time": "12:00", "action": "sync", "target": "/data/x"},
        {"user": "bob", "time": "12:00", "action": "backup", "target": "/srv/y"},
        {"user": "alice", "time": "12:00", "action": "delete", "target": "/tmp/z"},
    ]

    events: list[dict] = []
    for task in tasks:
        if task["time"] != now_hhmm:
            continue
        user = task["user"]
        if users[user]["executed"] >= users[user]["quota"]:
            events.append(
                {
                    "user": user,
                    "action": task["action"],
                    "target": task["target"],
                    "status": "quota_exceeded",
                    "message": f"{user} has exceeded quota.",
                }
            )
            continue
        events.append(
            {
                "user": user,
                "action": task["action"],
                "target": task["target"],
                "status": "success",
                "message": f"Executing {task['action']} on {task['target']} for {user}",
            }
        )
        users[user]["executed"] += 1

    return {
        "events": events,
        "executed": {name: data["executed"] for name, data in users.items()},
    }


@pytest.mark.asyncio
async def test_ab_comparison_at_1200(seeded_session):
    variant_a = run_original("12:00")

    tasks = await TaskService(seeded_session).list_due_tasks("12:00")
    executor = TaskExecutor(seeded_session)
    events_b: list[dict] = []
    for task in tasks:
        result = await executor.execute(task)
        events_b.append(
            {
                "user": task.user.name,
                "action": task.action,
                "target": task.target,
                "status": result["status"],
            }
        )

    assert _outcomes(variant_a["events"]) == _outcomes(events_b)

    users = UserService(seeded_session)
    quota = QuotaService(seeded_session)
    alice = await users.get_by_name("alice")
    bob = await users.get_by_name("bob")
    executed_b = {
        "alice": await quota.get_executed_today(alice.id),
        "bob": await quota.get_executed_today(bob.id),
    }
    assert executed_b == variant_a["executed"]


@pytest.mark.asyncio
async def test_ab_alice_quota_burned(seeded_session):
    """If Variant A would skip alice (quota already used), Variant B must too."""
    variant_a = _run_original_with_starting_executed("12:00", {"alice": 3, "bob": 0})

    users = UserService(seeded_session)
    quota = QuotaService(seeded_session)
    alice = await users.get_by_name("alice")
    for _ in range(alice.quota):
        await quota.record_execution(alice)

    due = await TaskService(seeded_session).list_due_tasks("12:00")
    executor = TaskExecutor(seeded_session)
    events_b: list[dict] = []
    for task in due:
        result = await executor.execute(task)
        events_b.append(
            {
                "user": task.user.name,
                "action": task.action,
                "target": task.target,
                "status": result["status"],
            }
        )

    assert _outcomes(variant_a["events"]) == _outcomes(events_b)
    assert all(e["status"] == "quota_exceeded" for e in events_b if e["user"] == "alice")
    assert any(e["status"] == "success" for e in events_b if e["user"] == "bob")
