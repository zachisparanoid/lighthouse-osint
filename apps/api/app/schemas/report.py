from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ReportSection = Literal["summary", "inventory", "findings", "graph", "provenance", "timeline"]


class ReportCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    sections: list[ReportSection] = ["summary", "inventory", "findings", "graph", "provenance"]
    format: Literal["pdf", "json", "csv", "bundle"] = "pdf"
    entity_ids: list[uuid.UUID] | None = None  # None => whole case
    min_confidence: int = Field(default=0, ge=0, le=100)
    # Optional base64 PNG of the graph captured client-side for the snapshot section.
    graph_snapshot_png: str | None = None


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    case_id: uuid.UUID
    title: str
    config: dict[str, Any]
    format: str
    status: str
    file_path: str | None
    artifacts: dict[str, Any]
    error: str | None
    generated_at: datetime | None
    created_at: datetime
