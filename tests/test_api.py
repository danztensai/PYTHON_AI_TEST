"""Real HTTP API tests via httpx AsyncClient."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert set(body["actions"]) == {"backup", "delete", "sync"}


@pytest.mark.asyncio
async def test_users_post_get_404_409(client):
    created = await client.post("/users", json={"name": "carol", "quota": 2})
    assert created.status_code == 201
    data = created.json()
    assert data["name"] == "carol"
    assert data["quota"] == 2
    assert data["executed_today"] == 0
    assert data["remaining_quota"] == 2

    fetched = await client.get("/users/carol")
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "carol"

    missing = await client.get("/users/nobody")
    assert missing.status_code == 404

    dup = await client.post("/users", json={"name": "carol", "quota": 1})
    assert dup.status_code == 409


@pytest.mark.asyncio
async def test_tasks_post_get_validation(seeded_client):
    created = await seeded_client.post(
        "/tasks",
        json={
            "user": "alice",
            "time": "14:30",
            "action": "sync",
            "target": "/extra",
            "params": {"retries": 2},
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["user"] == "alice"
    assert body["time"] == "14:30"
    assert body["params"] == {"retries": 2}

    listed = await seeded_client.get("/tasks", params={"user": "alice"})
    assert listed.status_code == 200
    alice_tasks = listed.json()
    assert len(alice_tasks) >= 3
    assert any(t["target"] == "/extra" for t in alice_tasks)

    unknown = await seeded_client.post(
        "/tasks",
        json={
            "user": "missing_user",
            "time": "12:00",
            "action": "sync",
            "target": "/x",
        },
    )
    assert unknown.status_code == 404

    bad_time = await seeded_client.post(
        "/tasks",
        json={
            "user": "alice",
            "time": "25:99",
            "action": "sync",
            "target": "/x",
        },
    )
    assert bad_time.status_code == 422


@pytest.mark.asyncio
async def test_run_task_success_and_quota_exceeded(seeded_client):
    # Create a user with quota=1 and two tasks
    await seeded_client.post("/users", json={"name": "limited", "quota": 1})
    t1 = await seeded_client.post(
        "/tasks",
        json={"user": "limited", "time": "09:00", "action": "sync", "target": "/one"},
    )
    t2 = await seeded_client.post(
        "/tasks",
        json={"user": "limited", "time": "09:00", "action": "sync", "target": "/two"},
    )
    id1, id2 = t1.json()["id"], t2.json()["id"]

    r1 = await seeded_client.post(f"/tasks/{id1}/run")
    assert r1.status_code == 200
    assert r1.json()["status"] == "success"

    r2 = await seeded_client.post(f"/tasks/{id2}/run")
    assert r2.status_code == 200
    assert r2.json()["status"] == "quota_exceeded"


@pytest.mark.asyncio
async def test_bob_quota_independent_of_alice(seeded_client):
    tasks = (await seeded_client.get("/tasks")).json()
    alice_tasks = [t for t in tasks if t["user"] == "alice"]
    bob_tasks = [t for t in tasks if t["user"] == "bob"]
    assert alice_tasks and bob_tasks

    for t in alice_tasks:
        resp = await seeded_client.post(f"/tasks/{t['id']}/run")
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

    bob = await seeded_client.get("/users/bob")
    assert bob.json()["executed_today"] == 0
    assert bob.json()["remaining_quota"] == 5

    bob_run = await seeded_client.post(f"/tasks/{bob_tasks[0]['id']}/run")
    assert bob_run.status_code == 200
    assert bob_run.json()["status"] == "success"

    bob_after = await seeded_client.get("/users/bob")
    assert bob_after.json()["executed_today"] == 1


@pytest.mark.asyncio
async def test_run_missing_task_404(seeded_client):
    resp = await seeded_client.post("/tasks/999999/run")
    assert resp.status_code == 404
