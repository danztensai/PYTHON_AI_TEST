# CONTEXT.md — Origin story, problem, and solution

Historical context for developers and AI agents: why this backend exists, what the original script looked like, and how the refactor maps to the current codebase.

## 1. Background

A previous engineer left a working but messy in-memory script that ran scheduled actions for a few hard-coded users under simple quota checks. We were asked to refactor that script into a maintainable backend: modular, persistent, testable, and safe for multiple people (and AI agents) to extend without breaking the original behavioral contract.

## 2. The original code (verbatim)

The initial script is preserved below as a historical artifact. An adapted copy lives in `legacy/original_runner.py` for A/B comparison tests against the refactored executor.

```python
import datetime

users = {
 'alice': {'quota': 3, 'executed': 0},
 'bob': {'quota': 5, 'executed': 0}
}

tasks = [
 {'user': 'alice', 'time': '12:00', 'action': 'sync', 'target': '/data/x'},
 {'user': 'bob', 'time': '12:00', 'action': 'backup', 'target': '/srv/y'},
 {'user': 'alice', 'time': '12:00', 'action': 'delete', 'target': '/tmp/z'},
]

def run():
 now = datetime.datetime.now().strftime('%H:%M')
 for task in tasks:
     if task['time'] == now:
         user = task['user']
         if users[user]['executed'] >= users[user]['quota']:
             print(f"{user} has exceeded quota.")
             continue
         print(f"Executing {task['action']} on {task['target']} for {user}")
         users[user]['executed'] += 1
```

## 3. Problems with the initial design

- Everything in one function / global dicts — hard to extend
- No persistence (lost on restart)
- No HTTP/API to submit strategies
- `print` instead of logging
- No pluggable action strategies
- Quota never resets by calendar day
- Tight coupling of schedule check, quota, and execution
- Difficult for multiple developers / AI agents to change safely

## 4. Requirements / guidance that drove the refactor

**Required modular design:**

- User management & quota control module
- Task data model
- Task executor (extensible)
- Scheduling system (simple OK)

**Required behaviors:**

- Single user can have multiple tasks
- Task parameters configurable (e.g. dict input)
- Task execution must use logging module

**Optional extensions that were implemented:**

- Different action strategies (OOP / strategy pattern)
- Async execution version (FastAPI + async SQLAlchemy + async strategies)

**Delivery choices made with stakeholder:**

- FastAPI HTTP API (not in-process only)
- SQLite persistence (not memory-only)

## 5. Solution — what was done

| Original | Solution |
|----------|----------|
| globals `users` / `tasks` | SQLite `User`, `QuotaUsage`, `Task` |
| `run()` loop | `TaskScheduler` + `TaskExecutor` |
| `print` | `logging` |
| if action string inline | `ActionStrategy` registry (`sync` / `backup` / `delete`) |
| no API | FastAPI endpoints |
| no tests | unit, API, A/B vs legacy, live |

**Concrete deliverables:**

- `app/` — FastAPI app (`main`, `schemas`, `models`, `db`, `users`, `tasks`, `executor`, `strategies`, `scheduler`, `seed`, `logging_config`)
- `legacy/original_runner.py` — adapted original for A/B comparison
- `tests/` — unit, API, A/B (`test_ab_comparison.py`), optional live smoke
- Docker image (`Dockerfile`) for one-command run
- Docs: `README.md`, `SPEC.md`, `DEVELOPMENT.md`, `AGENTS.md`, this file

**Behavioral compatibility preserved:**

- Seed data: alice (quota 3) and bob (quota 5) with the same three 12:00 tasks
- Quota-exceeded messaging style aligned with the original
- A/B tests in `tests/test_ab_comparison.py` compare outcomes vs the legacy runner

## 6. How to use this context

Reading order:

1. **CONTEXT.md** (this file) — origin story, original code, problem → solution map  
2. **SPEC.md** — product/tech contract (data model, API, flows)  
3. **DEVELOPMENT.md** — setup, extending, testing, debugging  
4. **AGENTS.md** — coding-agent constraints and ownership map (agents: read CONTEXT first)
