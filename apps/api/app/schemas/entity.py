from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from lighthouse_shared import EntityType, RelationshipType


class EntityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    case_id: uuid.UUID
    type: EntityType
    value: str
    label: str
    attributes: dict[str, Any]
    first_seen: datetime | None
    last_seen: datetime | None
    confidence: int
    source_count: int
    tags: list[str]
    conflicting: bool
    pinned: bool
    created_at: datetime
    updated_at: datetime


class ProvenanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    collector_name: str
    source_url: str | None
    raw_excerpt: dict[str, Any] | None
    retrieved_at: datetime
    license_note: str | None


class EntityDetail(EntityOut):
    provenances: list[ProvenanceOut] = []


class EntityCreate(BaseModel):
    type: EntityType
    value: str = Field(min_length=1)
    label: str | None = None
    tags: list[str] = []
    # Optional: immediately kick off collection from this seed.
    run_collectors: bool = False
    autoexpand: bool = False


class EntityUpdate(BaseModel):
    label: str | None = None
    tags: list[str] | None = None
    pinned: bool | None = None


class BulkAction(BaseModel):
    entity_ids: list[uuid.UUID] = Field(min_length=1)
    action: Literal["tag", "untag", "delete", "pin", "unpin", "run"]
    tag: str | None = None
    collector_name: str | None = None


class EdgeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    case_id: uuid.UUID
    source_entity_id: uuid.UUID
    target_entity_id: uuid.UUID
    relationship: RelationshipType
    confidence: int
    attributes: dict[str, Any]


class EdgeCreate(BaseModel):
    source_entity_id: uuid.UUID
    target_entity_id: uuid.UUID
    relationship: RelationshipType
    attributes: dict[str, Any] = {}


class GraphResponse(BaseModel):
    entities: list[EntityOut]
    edges: list[EdgeOut]
    layout: dict[str, Any] = {}


class NoteCreate(BaseModel):
    body: str = Field(min_length=1)
    entity_id: uuid.UUID | None = None
    pinned: bool = False


class NoteUpdate(BaseModel):
    body: str | None = None
    pinned: bool | None = None


class NoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    case_id: uuid.UUID
    entity_id: uuid.UUID | None
    author_id: uuid.UUID | None
    body: str
    pinned: bool
    created_at: datetime
    updated_at: datetime


class SearchHit(BaseModel):
    entity: EntityOut
    rank: float = 0.0
