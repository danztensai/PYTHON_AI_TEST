"""OOP action strategies for task execution."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models import Task

logger = logging.getLogger(__name__)


class ActionStrategy(ABC):
    """Base class for pluggable action strategies."""

    name: str = "base"

    @abstractmethod
    async def execute(self, task: Task) -> None:
        """Perform the action for the given task (simulated by default)."""


class SyncStrategy(ActionStrategy):
    name = "sync"

    async def execute(self, task: Task) -> None:
        retries = int(task.params.get("retries", 1))
        delay = float(task.params.get("delay", 0))
        logger.info(
            "SyncStrategy: syncing target=%s retries=%s delay=%s params=%s",
            task.target,
            retries,
            delay,
            task.params,
        )
        if delay > 0:
            await asyncio.sleep(delay)
        # Simulated sync — no real filesystem I/O
        logger.info("SyncStrategy: completed sync for target=%s", task.target)


class BackupStrategy(ActionStrategy):
    name = "backup"

    async def execute(self, task: Task) -> None:
        destination = task.params.get("destination", f"{task.target}.bak")
        logger.info(
            "BackupStrategy: backing up target=%s destination=%s params=%s",
            task.target,
            destination,
            task.params,
        )
        await asyncio.sleep(0)
        logger.info("BackupStrategy: completed backup for target=%s", task.target)


class DeleteStrategy(ActionStrategy):
    name = "delete"

    async def execute(self, task: Task) -> None:
        dry_run = bool(task.params.get("dry_run", True))
        logger.info(
            "DeleteStrategy: deleting target=%s dry_run=%s params=%s",
            task.target,
            dry_run,
            task.params,
        )
        await asyncio.sleep(0)
        logger.info("DeleteStrategy: completed delete for target=%s", task.target)


# Registry: add new strategies here to extend supported actions
STRATEGY_REGISTRY: dict[str, type[ActionStrategy]] = {
    SyncStrategy.name: SyncStrategy,
    BackupStrategy.name: BackupStrategy,
    DeleteStrategy.name: DeleteStrategy,
}


def get_strategy(action: str) -> ActionStrategy | None:
    """Return a strategy instance for the given action key, or None."""
    cls = STRATEGY_REGISTRY.get(action)
    if cls is None:
        return None
    return cls()


def list_actions() -> list[str]:
    return sorted(STRATEGY_REGISTRY.keys())
