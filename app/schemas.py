"""Pydantic request/response schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class UserCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    quota: int = Field(..., ge=0)


class UserResponse(BaseModel):
    id: int
    name: str
    quota: int
    executed_today: int
    remaining_quota: int

    model_config = {"from_attributes": True}


class TaskCreate(BaseModel):
    user: str = Field(..., min_length=1, description="Username that owns this task")
    time: str = Field(..., description="Daily run time in HH:MM")
    action: str = Field(..., min_length=1, max_length=64)
    target: str = Field(..., min_length=1, max_length=512)
    params: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True

    @field_validator("time")
    @classmethod
    def validate_time(cls, value: str) -> str:
        parts = value.split(":")
        if len(parts) != 2:
            raise ValueError("time must be HH:MM")
        hour, minute = parts
        if not (hour.isdigit() and minute.isdigit()):
            raise ValueError("time must be HH:MM with numeric parts")
        h, m = int(hour), int(minute)
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError("time must be a valid HH:MM clock value")
        return f"{h:02d}:{m:02d}"


class TaskResponse(BaseModel):
    id: int
    user: str
    time: str
    action: str
    target: str
    params: dict[str, Any]
    enabled: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class RunResult(BaseModel):
    task_id: int
    status: str
    message: str
