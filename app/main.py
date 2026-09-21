"""FastAPI application entrypoint for the Task Strategy Backend."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal, get_db, init_db
from app.executor import TaskExecutor
from app.logging_config import setup_logging
from app.scheduler import TaskScheduler
from app.schemas import RunResult, TaskCreate, TaskResponse, UserCreate, UserResponse
from app.seed import seed_if_empty
from app.strategies import list_actions
from app.tasks import TaskService
from app.users import QuotaService, UserService

logger = logging.getLogger(__name__)

scheduler = TaskScheduler()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    setup_logging()
    await init_db()
    async with AsyncSessionLocal() as session:
        await seed_if_empty(session)
    scheduler.start()
    logger.info("Task Strategy Backend started")
    yield
    scheduler.stop()
    logger.info("Task Strategy Backend stopped")


app = FastAPI(
    title="Task Strategy Backend",
    description="Receive user-submitted task strategies, execute them daily, enforce quotas.",
    version="1.0.0",
    lifespan=lifespan,
)


def _task_to_response(task) -> TaskResponse:
    return TaskResponse(
        id=task.id,
        user=task.user.name,
        time=task.time,
        action=task.action,
        target=task.target,
        params=task.params or {},
        enabled=task.enabled,
        created_at=task.created_at,
    )


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "actions": list_actions()}


@app.post("/users", response_model=UserResponse, status_code=201)
async def create_user(body: UserCreate, db: AsyncSession = Depends(get_db)) -> UserResponse:
    service = UserService(db)
    try:
        user = await service.create_user(name=body.name, quota=body.quota)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    quota = QuotaService(db)
    executed = await quota.get_executed_today(user.id)
    remaining = await quota.remaining_quota(user)
    return UserResponse(
        id=user.id,
        name=user.name,
        quota=user.quota,
        executed_today=executed,
        remaining_quota=remaining,
    )


@app.get("/users/{name}", response_model=UserResponse)
async def get_user(name: str, db: AsyncSession = Depends(get_db)) -> UserResponse:
    user = await UserService(db).get_by_name(name)
    if user is None:
        raise HTTPException(status_code=404, detail=f"User '{name}' not found")

    quota = QuotaService(db)
    executed = await quota.get_executed_today(user.id)
    remaining = await quota.remaining_quota(user)
    return UserResponse(
        id=user.id,
        name=user.name,
        quota=user.quota,
        executed_today=executed,
        remaining_quota=remaining,
    )


@app.post("/tasks", response_model=TaskResponse, status_code=201)
async def create_task(body: TaskCreate, db: AsyncSession = Depends(get_db)) -> TaskResponse:
    service = TaskService(db)
    try:
        task = await service.create_task(
            username=body.user,
            time=body.time,
            action=body.action,
            target=body.target,
            params=body.params,
            enabled=body.enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _task_to_response(task)


@app.get("/tasks", response_model=list[TaskResponse])
async def list_tasks(
    user: str | None = Query(default=None, description="Filter by username"),
    db: AsyncSession = Depends(get_db),
) -> list[TaskResponse]:
    tasks = await TaskService(db).list_tasks(username=user)
    return [_task_to_response(t) for t in tasks]


@app.post("/tasks/{task_id}/run", response_model=RunResult)
async def run_task(task_id: int, db: AsyncSession = Depends(get_db)) -> RunResult:
    task = await TaskService(db).get_by_id(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    result = await TaskExecutor(db).execute(task)
    return RunResult(**result)
