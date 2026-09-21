# Task Strategy Backend

FastAPI + SQLite service that accepts user-submitted task strategies, runs them daily at a configured `HH:MM`, and enforces per-user daily quotas.

## Documentation

| Doc | Purpose |
|-----|---------|
| [CONTEXT.md](CONTEXT.md) | Origin story / problem & solution (original script, refactor drivers, map to current design) |
| [SPEC.md](SPEC.md) | Product & technical specification (requirements, data model, API contract, execution flow) |
| [DEVELOPMENT.md](DEVELOPMENT.md) | Local/Docker setup, project layout, extending, testing, debugging |
| [AGENTS.md](AGENTS.md) | Instructions for AI coding agents (constraints, ownership map, how-tos) |

## Setup

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

## Run

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open interactive docs at http://127.0.0.1:8000/docs

On first start the service seeds:

| User  | Quota | Tasks |
|-------|-------|--------|
| alice | 3     | sync `/data/x`, delete `/tmp/z` at 12:00 |
| bob   | 5     | backup `/srv/y` at 12:00 |

## API

- `POST /users` — `{ "name": "carol", "quota": 2 }`
- `GET /users/{name}` — quota + today's usage
- `POST /tasks` — submit a strategy (dict `params` supported)
- `GET /tasks?user=alice` — list tasks (one user can have many)
- `POST /tasks/{id}/run` — run a task immediately (same executor/quota path as the scheduler)
- `GET /health` — liveness + registered action names

### Example task submit

```json
{
  "user": "alice",
  "time": "12:00",
  "action": "sync",
  "target": "/data/x",
  "params": { "retries": 3, "delay": 0 }
}
```

## Modules

| Module | Role |
|--------|------|
| `app/users.py` | User management & daily quota |
| `app/models.py` / `app/tasks.py` | Task data model & repository |
| `app/executor.py` / `app/strategies.py` | Extensible strategy executor |
| `app/scheduler.py` | Minute-tick HH:MM scheduler |

Actions are simulated (logged) by default. Add a new action by subclassing `ActionStrategy` and registering it in `STRATEGY_REGISTRY`.

## Testing

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest -v
```

## Docker

```bash
docker build -t task-strategy-backend .
docker run --rm -p 8000:8000 task-strategy-backend
```
