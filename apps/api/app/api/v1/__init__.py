"""Aggregate all v1 routers into a single router mounted under /api/v1."""
from fastapi import APIRouter

from app.api.v1 import audit, auth, cases, edges, entities, jobs, keys, modules, reports, ws

api_router = APIRouter()
api_router.include_router(auth.router, tags=["auth"])
api_router.include_router(cases.router, tags=["cases"])
api_router.include_router(entities.router, tags=["entities"])
api_router.include_router(edges.router, tags=["edges"])
api_router.include_router(jobs.router, tags=["jobs"])
api_router.include_router(modules.router, tags=["modules"])
api_router.include_router(keys.router, tags=["keys"])
api_router.include_router(reports.router, tags=["reports"])
api_router.include_router(audit.router, tags=["audit"])
api_router.include_router(ws.router, tags=["ws"])

__all__ = ["api_router"]
