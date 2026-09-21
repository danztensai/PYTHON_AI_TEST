# Task Strategy Backend — Product & Technical Specification

## 1. Purpose / problem statement

This project is a **refactor of a messy in-memory script** (`legacy/original_runner.py`) into a modular FastAPI backend that:

1. **Receives** user-submitted task strategies over HTTP.
2. **Runs** enabled tasks daily at a configured `HH:MM` via an in-process scheduler.
3. **Enforces** per-user daily execution quotas so a user cannot exceed their limit within a calendar day.

The original script hard-coded alice/bob users and three tasks, checked quota with a simple in-memory counter, and printed results. The backend preserves that behavioral contract (same seed data, same quota outcomes for comparable runs) while adding persistence, an extensible strategy pattern, structured logging, and a documented API.

## 2. Non-goals

Explicitly **out of scope** for the current design:

| Non-goal | Rationale |
|----------|-----------|
| Real filesystem side effects by default | Strategies **simulate** sync/backup/delete (log only). No destructive FS ops unless explicitly requested and implemented later. |
| Authentication / authorization | Open API; no tokens, roles, or multi-tenant isolation beyond username. |
| Multi-worker / multi-process locking | Scheduler dedupe is **in-process** (`_last_run_minute`). Multiple uvicorn workers would double-run ticks. |
| Docker orchestration beyond a single container | One image, one process. No Compose swarm, K8s, or volume orchestration required. |
| Schema migrations (Alembic) | Tables are created with `Base.metadata.create_all` on startup. |
| Sub-minute cron precision | Minute-interval tick; tasks match wall-clock `HH:MM`. |

## 3. Functional requirements

| ID | Requirement |
|----|-------------|
| FR-1 | A user may own **many tasks** (1:N). |
| FR-2 | Task `params` is a **JSON dict** (arbitrary keys; strategies interpret what they need). |
| FR-3 | All runtime messaging uses the **logging** module (not `print`). |
| FR-4 | Tasks run daily at configured **`HH:MM`** (24-hour clock, validated on create). |
| FR-5 | Daily quota resets by calendar date via **`QuotaUsage.usage_date`** (new date → new row / zero executed). |
| FR-6 | Successful executes burn one unit of the user’s daily quota; unknown actions and failed executes do **not** burn quota. |
| FR-7 | Manual `POST /tasks/{id}/run` uses the **same** executor/quota path as the scheduler. |
| FR-8 | On empty DB, seed alice/bob demo users and their three tasks. |

## 4. Architecture overview

```
                    ┌─────────────────────────────────────┐
                    │           FastAPI (app.main)          │
                    │  /users  /tasks  /tasks/{id}/run      │
                    │  /health                              │
                    └──────────────┬──────────────────────┘
                                   │ AsyncSession
           ┌───────────────────────┼───────────────────────┐
           ▼                       ▼                       ▼
    UserService            TaskService              TaskExecutor
    QuotaService                                    │
           │                       │                ├─ get_strategy()
           │                       │                └─ QuotaService
           ▼                       ▼                       ▼
      SQLAlchemy models ◄──── SQLite (aiosqlite)     ActionStrategy
      User, QuotaUsage, Task                         (STRATEGY_REGISTRY)
                                   ▲
                    TaskScheduler (APScheduler, 60s tick)
                    lifespan start/stop
```

### Module map

| Path | Responsibility |
|------|----------------|
| `app/main.py` | FastAPI app, lifespan (logging, DB init, seed, scheduler), HTTP routes |
| `app/schemas.py` | Pydantic request/response models + `HH:MM` validation |
| `app/models.py` | SQLAlchemy `User`, `QuotaUsage`, `Task` |
| `app/db.py` | Async engine, session factory, `get_db`, `init_db` |
| `app/users.py` | `UserService`, `QuotaService` |
| `app/tasks.py` | `TaskService` (create/list/due) |
| `app/executor.py` | Quota check → strategy → record (or skip/error) |
| `app/strategies.py` | `ActionStrategy` ABC, concrete strategies, `STRATEGY_REGISTRY` |
| `app/scheduler.py` | Minute-tick APScheduler; sequential execution of due tasks |
| `app/seed.py` | alice/bob seed when DB empty |
| `app/logging_config.py` | Root logger setup |
| `legacy/original_runner.py` | In-memory Variant A for A/B tests |

## 5. Data model

### User

| Field | Type | Notes |
|-------|------|-------|
| `id` | int PK | Auto-increment |
| `name` | str(64) | Unique, indexed |
| `quota` | int | Max successful executions per calendar day |

Relationships: `tasks`, `quota_usages` (cascade delete-orphan).

### QuotaUsage

| Field | Type | Notes |
|-------|------|-------|
| `id` | int PK | |
| `user_id` | FK → users | ON DELETE CASCADE |
| `usage_date` | date | Calendar day of the counter |
| `executed` | int | Successful runs counted today |

Unique constraint: `(user_id, usage_date)`.

**Reset semantics:** `QuotaService` looks up (or creates) today’s row. Yesterday’s `executed` does not carry over.

### Task

| Field | Type | Notes |
|-------|------|-------|
| `id` | int PK | |
| `user_id` | FK → users | ON DELETE CASCADE |
| `time` | str(5) | `HH:MM` daily schedule |
| `action` | str(64) | Registry key (`sync`, `backup`, `delete`, …) |
| `target` | str(512) | Path or logical target string |
| `params` | JSON dict | Default `{}` |
| `enabled` | bool | Default `True`; disabled tasks are not due |
| `created_at` | datetime | UTC-naive timestamp on create |

## 6. API contract

Base URL (local): `http://127.0.0.1:8000`  
Interactive docs: `/docs`

### `GET /health`

**Response `200`**

```json
{ "status": "ok", "actions": ["backup", "delete", "sync"] }
```

`actions` is the sorted registry of known strategy names.

---

### `POST /users`

**Request**

```json
{ "name": "carol", "quota": 2 }
```

| Field | Constraints |
|-------|-------------|
| `name` | 1–64 chars |
| `quota` | integer ≥ 0 |

**Response `201`** — `UserResponse`

```json
{
  "id": 3,
  "name": "carol",
  "quota": 2,
  "executed_today": 0,
  "remaining_quota": 2
}
```

| Status | When |
|--------|------|
| `201` | Created |
| `409` | Username already exists |
| `422` | Validation error |

---

### `GET /users/{name}`

**Response `200`** — same `UserResponse` shape.

| Status | When |
|--------|------|
| `200` | Found |
| `404` | Unknown user |

---

### `POST /tasks`

**Request**

```json
{
  "user": "alice",
  "time": "12:00",
  "action": "sync",
  "target": "/data/x",
  "params": { "retries": 3, "delay": 0 },
  "enabled": true
}
```

| Field | Constraints |
|-------|-------------|
| `user` | Existing username |
| `time` | Valid `HH:MM` (normalized to zero-padded) |
| `action` | Non-empty string (unknown actions allowed at create; fail at run) |
| `target` | 1–512 chars |
| `params` | Object, default `{}` |
| `enabled` | bool, default `true` |

**Response `201`** — `TaskResponse`

```json
{
  "id": 4,
  "user": "alice",
  "time": "12:00",
  "action": "sync",
  "target": "/data/x",
  "params": { "retries": 3, "delay": 0 },
  "enabled": true,
  "created_at": "2026-09-21T09:00:00"
}
```

| Status | When |
|--------|------|
| `201` | Created |
| `404` | User not found |
| `422` | Invalid body / bad `time` |

---

### `GET /tasks`

Query: optional `user=<username>` filter.

**Response `200`** — `TaskResponse[]` ordered by `id`.

---

### `POST /tasks/{task_id}/run`

Runs immediately through `TaskExecutor` (same path as scheduler).

**Response `200`** — `RunResult`

```json
{
  "task_id": 1,
  "status": "success",
  "message": "Executing sync on /data/x for alice"
}
```

| `status` | Meaning | Quota burned? |
|----------|---------|---------------|
| `success` | Strategy completed | Yes |
| `quota_exceeded` | User at daily limit | No |
| `error` | Unknown action (or similar pre-exec error) | No |
| `failure` | Strategy raised exception | No |

| Status | When |
|--------|------|
| `200` | Run attempted (result in body) |
| `404` | Task id not found |

---

## 7. Execution flow

```
lifespan start
  → setup_logging()
  → init_db()          # create tables
  → seed_if_empty()    # alice/bob if no users
  → scheduler.start()  # 60s interval + immediate startup tick

each scheduler tick (_tick):
  → acquire asyncio lock
  → if already ran this calendar minute → return
  → list_due_tasks(current HH:MM)  # enabled + matching time
  → for each due task (sequential):
        TaskExecutor.execute(task)
  → commit session

TaskExecutor.execute(task):
  1. resolve strategy via get_strategy(action)
     - None → status "error", return (no quota)
  2. QuotaService.can_execute(user)
     - False → status "quota_exceeded", return
  3. strategy.execute(task)
     - success → record_execution → status "success"
     - exception → status "failure" (no quota burn)
```

**Why sequential?** Same-user multiple due tasks must see updated quota between runs (matches original script order).

## 8. Action strategy pattern and registry

- Abstract base: `ActionStrategy` with `name` and `async def execute(task)`.
- Concrete: `SyncStrategy`, `BackupStrategy`, `DeleteStrategy` (simulated I/O).
- Registry: `STRATEGY_REGISTRY: dict[str, type[ActionStrategy]]` in `app/strategies.py`.
- Lookup: `get_strategy(action)` → instance or `None`.
- Discovery: `list_actions()` for `/health`.

Built-in params (convention, not schema-enforced):

| Action | Common params |
|--------|----------------|
| `sync` | `retries` (int, default 1), `delay` (float seconds, default 0) |
| `backup` | `destination` (default `{target}.bak`) |
| `delete` | `dry_run` (bool, default `True`) |

## 9. Seed data

Inserted only when `users` table is empty:

| User | Quota | Tasks |
|------|-------|--------|
| alice | 3 | `sync` `/data/x` @ 12:00; `delete` `/tmp/z` @ 12:00 (`dry_run: true`) |
| bob | 5 | `backup` `/srv/y` @ 12:00 |

Defined in `app/seed.py` (mirrored in `tests/conftest.py` for tests).

## 10. Tech stack

| Layer | Choice |
|-------|--------|
| HTTP API | **FastAPI** |
| ORM | **SQLAlchemy** 2.x async |
| DB driver | **aiosqlite** → file `task_strategy.db` |
| Scheduler | **APScheduler** `AsyncIOScheduler` |
| Validation | **Pydantic** v2 |
| Server | **uvicorn** |
| Tests | pytest, pytest-asyncio, httpx |

Python target for Docker: **3.12**.
