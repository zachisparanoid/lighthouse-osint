from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from lighthouse_shared import CollectorCost, JobStatus


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    case_id: uuid.UUID
    collector_name: str
    target_entity_id: uuid.UUID | None
    status: JobStatus
    progress: int
    result_summary: dict[str, Any] | None
    error: str | None
    depth: int
    parent_job_id: uuid.UUID | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class RunModuleRequest(BaseModel):
    collector_name: str
    target_entity_id: uuid.UUID


class AutoExpandRequest(BaseModel):
    seed_entity_id: uuid.UUID
    depth: int | None = Field(default=None, ge=1, le=5)
    budget: int | None = Field(default=None, ge=1, le=5000)
    disabled: list[str] = []


class ModuleInfoOut(BaseModel):
    name: str
    title: str
    description: str
    accepts: list[str]
    produces: list[str]
    cost: CollectorCost
    requires_key: str | None
    key_present: bool
    enabled: bool
    rate_limit: str
    source_note: str


class ModuleSettings(BaseModel):
    disabled: list[str] = []
    autoexpand_depth: int = Field(default=2, ge=1, le=5)
    autoexpand_budget: int = Field(default=250, ge=1, le=5000)
