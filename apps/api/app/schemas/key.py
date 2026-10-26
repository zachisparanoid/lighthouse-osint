from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

from lighthouse_shared import KeyService


class KeyCreate(BaseModel):
    service: KeyService
    value: str = Field(min_length=4)
    label: str = ""
    scope: Literal["user", "case"] = "user"
    case_id: uuid.UUID | None = None


class KeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    service: KeyService
    scope: str
    label: str
    hint: str | None
    is_valid: bool | None
    last_used_at: datetime | None
    owner_case_id: uuid.UUID | None
    owner_user_id: uuid.UUID | None
    created_at: datetime

    @computed_field
    @property
    def masked(self) -> str:
        return "••••" + (self.hint or "")


class KeyTestResult(BaseModel):
    id: uuid.UUID
    service: KeyService
    is_valid: bool
    message: str
