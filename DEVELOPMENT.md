# DEVELOPMENT.md — How to use & continue development

Companion to [CONTEXT.md](CONTEXT.md) (origin story / problem & solution), [README.md](README.md) (quick start), [SPEC.md](SPEC.md) (full contract), and [AGENTS.md](AGENTS.md) (AI agent rules).

## Local setup

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### Run the API

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- App: http://127.0.0.1:8000  
- OpenAPI UI: http://127.0.0.1:8000/docs  
- Health: http://127.0.0.1:8000/health  

On first start with an empty DB, alice/bob and three demo tasks are seeded automatically.

### Dev / test dependencies

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest -v
```

## Docker build / run

```bash
docker build -t task-strategy-backend .
docker run --rm -p 8000:8000 task-strategy-backend
```

Image: Python 3.12-slim, copies `app/`, runs uvicorn on port 8000.  
SQLite file lives inside the container filesystem unless you mount a volume for persistence.

## Project layout

```
.
├── AGENTS.md                 # Instructions for AI coding agents
├── DEVELOPMENT.md            # This file
├── SPEC.md                   # Product & technical specification
├── README.md                 # Short entry point
├── Dockerfile
├── .dockerignore
├── .gitignore
├── requirements.txt
├── requirements-dev.txt
├── pytest.ini
├── task_strategy.db          # Created at runtime (gitignored)
├── app/
│   ├── __init__.py
│   ├── main.py               # FastAPI app + routes + lifespan
│   ├── schemas.py            # Pydantic models
│   ├── models.py             # SQLAlchemy models
│   ├── db.py                 # Engine / sessions
│   ├── users.py              # User + quota services
│   ├── tasks.py              # Task service
│   ├── executor.py           # Run pipeline
│   ├── strategies.py         # Action strategies + registry
│   ├── scheduler.py          # APScheduler minute tick
│   ├── seed.py               # Demo data
│   └── logging_config.py
├── legacy/
│   └── original_runner.py    # In-memory Variant A
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_unit.py
    ├── test_api.py
    ├── test_ab_comparison.py
    └── test_live_api.py
```

## Day-to-day workflow

1. **Change** code in the owning module (see AGENTS.md ownership map).
2. **Test** with `pytest -v` (unit + API + A/B).
3. **Run** locally with uvicorn if you need scheduler/live behavior.
4. **Update docs** (`SPEC.md` / README) when API or public behavior changes.

Keep diffs focused. Prefer extending services and strategies over stuffing logic into `main.py`.

## Extending

### New strategy

See step-by-step in [AGENTS.md](AGENTS.md#how-to-add-a-new-action-strategy). Summary: subclass in `app/strategies.py` → register → test → optionally document params in SPEC.

### New field on Task

1. Add column on `Task` in `app/models.py`.
2. Extend `TaskCreate` / `TaskResponse` in `app/schemas.py`.
3. Pass through `TaskService.create_task` and `_task_to_response` in `main.py`.
4. **Note:** There is no Alembic yet. Existing `task_strategy.db` will **not** auto-alter columns. Delete the DB file (dev only) or migrate manually so `create_all` can recreate, or introduce Alembic (see future work).
5. Update tests and SPEC data-model section.

### Change quota policy

Quota lives in `app/users.py` (`QuotaService`):

- `can_execute` / `remaining_quota` / `record_execution`
- Date keying via `_get_or_create_usage(..., usage_date=date.today())`

If you change when quota burns, update `app/executor.py` and the unit/API/A/B tests that encode the current contract. Preserve A/B parity with `legacy/original_runner.py` unless the human intentionally diverges from the legacy script.

## Testing guide

| Suite | Command / trigger | Notes |
|-------|-------------------|--------|
| Unit | `pytest tests/test_unit.py -v` | Services, executor, strategies |
| API | `pytest tests/test_api.py -v` | httpx ASGI client; lifespan off |
| A/B vs legacy | `pytest tests/test_ab_comparison.py -v` | Compares to `legacy/original_runner.py` |
| Live | Start uvicorn, then `pytest tests/test_live_api.py -v` | Skips if ports 8000/8001/8002 unreachable |
| All | `pytest -v` | Recommended before finishing a change |

Fixtures (`tests/conftest.py`) use in-memory SQLite + `StaticPool` so tests do not touch `task_strategy.db`.

## DB notes

| Topic | Detail |
|-------|--------|
| File | `task_strategy.db` at repo root (`app/db.py` → `DB_PATH`) |
| Git | Ignored via `*.db` in `.gitignore` |
| Create | `init_db()` on lifespan start (`Base.metadata.create_all`) |
| Seed | `seed_if_empty()` only when user count is 0 |
| Reset (dev) | Stop the server, delete `task_strategy.db`, restart |

## Debugging tips

- **OpenAPI `/docs`** — try endpoints interactively and inspect schemas.
- **Logs** — look for `task_id=... user=... status=...` lines from executor/scheduler; format set in `logging_config.py`.
- **Quota surprises** — `GET /users/{name}` shows `executed_today` / `remaining_quota` for today.
- **Scheduler not firing** — confirm lifespan started (uvicorn run of `app.main:app`, not a bare import); tick is every 60s and dedupes per calendar minute; tasks need `enabled=true` and exact `HH:MM` match to local wall clock.
- **Tests vs live DB** — failing live smoke ≠ fixture failure; check which DB the running process is using.
- **Unknown action** — create succeeds; run returns `status: "error"` without burning quota.
- **Compare to legacy** — `python -c "from legacy.original_runner import run_original; print(run_original('12:00'))"` then run the same due tasks through `TaskExecutor`.

## Suggested future work

| Idea | Why |
|------|-----|
| Auth (API keys / JWT) | Protect mutating endpoints; multi-tenant safety |
| Real adapters | Optional real FS/network strategies behind feature flags / `dry_run` |
| Multi-worker lock | Redis/DB lease so multiple processes don’t double-run ticks |
| Alembic migrations | Evolve schema without deleting SQLite files |
| Cron precision | CronTrigger or exact `HH:MM` jobs instead of 60s poll; timezone-aware schedule |
| Task update/delete APIs | Enable/disable, retarget, cancel without raw DB edits |
| Observability | Structured JSON logs, metrics for quota skips / failures |

None of the above are required for the current single-container demo scope (see SPEC non-goals).
