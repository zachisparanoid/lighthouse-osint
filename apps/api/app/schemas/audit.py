from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    actor_id: uuid.UUID | None
    action: str
    target_type: str | None
    target_id: str | None
    case_id: uuid.UUID | None
    ip: str | None
    user_agent: str | None
    meta: dict[str, Any]
    created_at: datetime
