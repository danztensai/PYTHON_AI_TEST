# AGENTS.md — Instructions for AI coding agents

Paste or forward this file (plus `SPEC.md` / `DEVELOPMENT.md` as needed) into Cursor, Claude, Codex, or similar when continuing work on this repo.

## Project one-liner

**Task Strategy Backend** — FastAPI + SQLite service that stores user task strategies, runs them daily at `HH:MM`, and enforces per-user daily quotas.

### Where docs live

| Doc | Audience | Contents |
|-----|----------|----------|
| [README.md](README.md) | Humans (entry) | Quick setup, run, API summary, Docker, tests |
| [SPEC.md](SPEC.md) | Humans + agents | Product/tech spec, data model, API contract, flows |
| [DEVELOPMENT.md](DEVELOPMENT.md) | Humans + agents | Setup, workflow, extending, debugging, future work |
| **This file** | AI agents | Constraints, ownership map, how-to change safely |

## Hard constraints / do-nots

1. **Do not break quota semantics**
   - Burn quota only after a **successful** `strategy.execute`.
   - Unknown action → `error`, **no** quota burn (resolve strategy **before** quota check).
   - Strategy exception → `failure`, **no** quota burn.
   - Daily reset is via `QuotaUsage.usage_date` (today’s row), not a midnight cron job.
2. **Do not use `print`** — use `logging.getLogger(__name__)`.
3. **Do not add real destructive filesystem operations** unless the human explicitly asks. Strategies stay simulated (log + optional `asyncio.sleep`).
4. **Do not commit secrets** (`.env`, credentials, API keys). `.env` is gitignored; keep it that way.
5. **Do not edit plan files** if any exist in the workspace (agent/plan artifacts) — leave them alone.
6. **Do not assume multi-worker safety** — scheduler dedupe is single-process only; don’t “fix” that without a real lock design.
7. **Do not force-push** or rewrite shared history unless the human explicitly orders it.
8. Prefer **minimal diffs** — match existing style; don’t drive-by refactor unrelated modules.

## Module ownership map

| Change type | Primary files |
|-------------|----------------|
| HTTP routes / status codes | `app/main.py`, `app/schemas.py` |
| Request/response shapes | `app/schemas.py` (+ tests in `tests/test_api.py`) |
| ORM tables / columns | `app/models.py` (then services using them) |
| User CRUD / quota math | `app/users.py` |
| Task CRUD / due queries | `app/tasks.py` |
| Run pipeline (status codes in result body) | `app/executor.py` |
| New/changed actions | `app/strategies.py` |
| Schedule timing / tick behavior | `app/scheduler.py` |
| Demo seed | `app/seed.py` (+ keep `tests/conftest.py` in sync if seed changes) |
| DB URL / session lifecycle | `app/db.py` |
| Logging format | `app/logging_config.py` |
| A/B vs legacy | `legacy/original_runner.py`, `tests/test_ab_comparison.py` |

## How to add a new action strategy

1. Open `app/strategies.py`.
2. Subclass `ActionStrategy`:
   - Set `name = "your_action"` (this is the API `action` string).
   - Implement `async def execute(self, task: Task) -> None`.
   - Read options from `task.params` with safe defaults.
   - Log with `logger.info(...)`; do not touch the real FS unless asked.
3. Register in `STRATEGY_REGISTRY`:
   ```python
   STRATEGY_REGISTRY: dict[str, type[ActionStrategy]] = {
       ...
       YourStrategy.name: YourStrategy,
   }
   ```
4. Update tests:
   - `tests/test_unit.py` — registry membership / smoke execute.
   - `tests/test_api.py` — `/health` actions set if the assertion is exact.
5. Run `pytest -v` (see below).
6. Optionally document params in `SPEC.md` §8 and README modules blurb.

No change to `TaskExecutor` is required if the action is registry-only.

## How to add an API endpoint

1. Add/extend Pydantic models in `app/schemas.py`.
2. Add business logic in the appropriate service (`users.py` / `tasks.py`) — keep routes thin.
3. Register the route in `app/main.py` with correct `status_code` / `response_model` / `HTTPException` mapping.
4. Add coverage in `tests/test_api.py` (prefer `client` / `seeded_client` fixtures from `tests/conftest.py`).
5. Update `SPEC.md` API section and the short README API list.
6. Run `pytest -v`.

## How to run tests before finishing

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest -v
```

- Default suite uses in-memory SQLite via fixtures — **no** need for a live server.
- `tests/test_live_api.py` **skips** if nothing listens on 8000/8001/8002 — that is OK.
- Do not mark work complete if unit/API/A/B tests fail.

## Preferred patterns

| Area | Pattern |
|------|---------|
| I/O | `async` / `await` end-to-end (SQLAlchemy async session, strategies, executor) |
| Logging | Module-level `logger = logging.getLogger(__name__)` |
| API shapes | Pydantic schemas in `schemas.py`; do not return ORM objects from routes |
| Business logic | Service classes (`UserService`, `TaskService`, `QuotaService`, `TaskExecutor`) |
| Dependencies | `Depends(get_db)` for request-scoped sessions |
| Errors | Domain `ValueError` in services → `HTTPException` in routes |
| Extension | Strategy registry > giant `if action == ...` switches |

## Test layout

| File | Covers |
|------|--------|
| `tests/conftest.py` | In-memory engine, seed helpers, `client` / `seeded_client` (lifespan **off** so scheduler does not start in API tests) |
| `tests/test_unit.py` | Users, quota, multi-task params, due list, registry, executor success/quota/unknown-action, strategy smoke |
| `tests/test_api.py` | Health, users 201/404/409, tasks create/list/validation, run + quota, cross-user quota isolation |
| `tests/test_ab_comparison.py` | Outcomes vs `legacy/original_runner.py` at 12:00 and with pre-burned alice quota |
| `tests/test_live_api.py` | Optional smoke against a running uvicorn |

## Common pitfalls

1. **Quota checked before execute** — but **after** strategy resolution. Reordering so quota burns on unknown actions is a regression.
2. **Unknown action does not burn quota** — covered by `test_unknown_action_does_not_consume_quota`.
3. **Sequential same-user ticks** — scheduler must not parallelize due tasks; parallel runs race quota for one user.
4. **Lifespan starts scheduler** — `app.main` lifespan calls `scheduler.start()`. API tests disable lifespan via ASGITransport defaults; if you enable lifespan in tests, expect scheduler side effects.
5. **Creating a task with unknown `action` succeeds** — failure happens at run time (`error`), not at `POST /tasks`.
6. **Changing seed** without updating A/B expectations / `conftest` seed will break comparison tests.
7. **Multiple uvicorn workers** — will duplicate minute ticks; do not claim “fixed” without cross-process locking.
8. **SQLite file** `task_strategy.db` is local state and gitignored — tests should keep using the fixture DB, not the file DB.

## Quick verification checklist (agent)

- [ ] Quota / status semantics unchanged or tests updated intentionally
- [ ] No `print(` introduced
- [ ] New strategy registered + tested
- [ ] `pytest -v` green
- [ ] SPEC/README updated if API or public behavior changed
