"""Collector capability listing + per-case module settings.

Capabilities are computed from the live collector registry combined with BYOK key
presence and a per-case "disabled" set. Module settings (disabled list + autoexpand
defaults) are persisted as a JSON blob in Redis, keyed by case.
"""
from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.registry import capabilities
from app.config import settings
from app.core.audit import write_audit
from app.core.keys import key_presence
from app.core.rbac import (
    CaseContext,
    case_access,
    client_ip,
    get_current_user,
    user_agent,
)
from app.core.redis_client import get_redis
from app.db.models import User
from app.db.session import get_db
from app.schemas.job import ModuleInfoOut, ModuleSettings
from lighthouse_shared import Role

router = APIRouter()


def _settings_key(case_id: uuid.UUID) -> str:
    return f"modules:settings:{case_id}"


def _default_settings() -> ModuleSettings:
    return ModuleSettings(
        disabled=[],
        autoexpand_depth=settings.default_autoexpand_depth,
        autoexpand_budget=settings.default_node_budget,
    )


async def _load_settings(case_id: uuid.UUID) -> ModuleSettings:
    redis = get_redis()
    raw = await redis.get(_settings_key(case_id))
    if not raw:
        return _default_settings()
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return _default_settings()
    defaults = _default_settings()
    return ModuleSettings(
        disabled=data.get("disabled", defaults.disabled),
        autoexpand_depth=data.get("autoexpand_depth", defaults.autoexpand_depth),
        autoexpand_budget=data.get("autoexpand_budget", defaults.autoexpand_budget),
    )


@router.get("/cases/{case_id}/modules", response_model=list[ModuleInfoOut])
async def list_case_modules(
    ctx: CaseContext = Depends(case_access(Role.VIEWER)),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Collector capabilities for a case, reflecting key presence + disabled modules."""
    kp = await key_presence(db, ctx.case.id, ctx.user.id)
    current = await _load_settings(ctx.case.id)
    return capabilities(kp, set(current.disabled))


@router.get("/cases/{case_id}/modules/settings", response_model=ModuleSettings)
async def get_case_module_settings(
    ctx: CaseContext = Depends(case_access(Role.VIEWER)),
) -> ModuleSettings:
    """Read the persisted per-case module settings (or defaults)."""
    return await _load_settings(ctx.case.id)


@router.put("/cases/{case_id}/modules/settings", response_model=ModuleSettings)
async def update_case_module_settings(
    payload: ModuleSettings,
    request: Request,
    ctx: CaseContext = Depends(case_access(Role.ANALYST)),
    db: AsyncSession = Depends(get_db),
) -> ModuleSettings:
    """Persist per-case module settings to Redis."""
    redis = get_redis()
    await redis.set(_settings_key(ctx.case.id), payload.model_dump_json())

    await write_audit(
        db,
        action="module.settings.update",
        actor_id=ctx.user.id,
        target_type="case",
        target_id=ctx.case.id,
        case_id=ctx.case.id,
        ip=client_ip(request),
        user_agent=user_agent(request),
        meta={
            "disabled": payload.disabled,
            "autoexpand_depth": payload.autoexpand_depth,
            "autoexpand_budget": payload.autoexpand_budget,
        },
    )
    await db.commit()
    return payload


@router.get("/modules", response_model=list[ModuleInfoOut])
async def list_modules(
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Global capability list with no case context (no keys, nothing disabled)."""
    return capabilities({}, set())
