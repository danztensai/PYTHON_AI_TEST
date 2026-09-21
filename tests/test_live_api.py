"""Optional live API smoke tests against a running uvicorn instance."""

from __future__ import annotations

import httpx
import pytest

CANDIDATE_BASES = (
    "http://127.0.0.1:8001",
    "http://127.0.0.1:8000",
    "http://127.0.0.1:8002",
)


def _find_live_base() -> str | None:
    for base in CANDIDATE_BASES:
        try:
            with httpx.Client(base_url=base, timeout=1.0) as client:
                resp = client.get("/health")
                if resp.status_code == 200:
                    return base
        except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError):
            continue
    return None


@pytest.fixture(scope="module")
def live_base() -> str:
    base = _find_live_base()
    if base is None:
        pytest.skip("No live API reachable on 8000/8001/8002")
    return base


@pytest.mark.asyncio
async def test_live_health(live_base: str):
    async with httpx.AsyncClient(base_url=live_base, timeout=2.0) as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "actions" in body


@pytest.mark.asyncio
async def test_live_users_alice(live_base: str):
    async with httpx.AsyncClient(base_url=live_base, timeout=2.0) as client:
        resp = await client.get("/users/alice")
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "alice"
        assert "quota" in body


@pytest.mark.asyncio
async def test_live_list_tasks(live_base: str):
    async with httpx.AsyncClient(base_url=live_base, timeout=2.0) as client:
        resp = await client.get("/tasks")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
