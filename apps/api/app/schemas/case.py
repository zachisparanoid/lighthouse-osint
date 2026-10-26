from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from lighthouse_shared import CaseStatus, Role


class CaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    # The acknowledgment gate: both are mandatory at the API boundary.
    legal_basis: str = Field(min_length=10, description="Authorization / scope for this investigation.")
    aup_accepted: bool
    aup_version: str = "1.0"

    @field_validator("aup_accepted")
    @classmethod
    def _must_accept(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError("You must accept the acceptable-use policy to create a case.")
        return v

    @field_validator("legal_basis")
    @classmethod
    def _basis_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("A legal basis / authorization note is required.")
        return v.strip()


class CaseUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    description: str | None = None
    status: CaseStatus | None = None
    legal_basis: str | None = None


class CaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    slug: str
    description: str | None
    status: CaseStatus
    legal_basis: str
    aup_accepted: bool
    aup_accepted_at: datetime | None
    owner_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class CaseSummary(CaseOut):
    entity_count: int = 0
    edge_count: int = 0
    running_jobs: int = 0
    role: Role | None = None


class CaseMemberAdd(BaseModel):
    email: EmailStr
    case_role: Role = Role.VIEWER


class CaseMemberOut(BaseModel):
    user_id: uuid.UUID
    email: EmailStr
    case_role: Role


class GraphLayoutUpdate(BaseModel):
    layout: dict[str, Any]


class RescanConfig(BaseModel):
    enabled: bool = False
    interval_hours: int = Field(default=24, ge=1, le=8760)
    seed_entity_id: uuid.UUID | None = None
    depth: int = Field(default=2, ge=1, le=5)
    budget: int = Field(default=250, ge=1, le=5000)
