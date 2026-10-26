"""FastAPI application entrypoint."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, select

from app.api.v1 import api_router
from app.config import settings
from app.core.redis_client import close_redis
from app.core.security import hash_password
from app.db.models import User
from app.db.session import SessionLocal
from lighthouse_shared import Role

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger("lighthouse")


async def _bootstrap_admin() -> None:
    """Create the first admin from env vars, only if there are no users yet."""
    if not (settings.bootstrap_admin_email and settings.bootstrap_admin_password):
        return
    try:
        async with SessionLocal() as db:
            count = await db.scalar(select(func.count()).select_from(User))
            if count and count > 0:
                return
            db.add(User(
                email=settings.bootstrap_admin_email.lower(),
                password_hash=hash_password(settings.bootstrap_admin_password),
                role=Role.ADMIN,
            ))
            await db.commit()
            logger.info("Bootstrapped admin user %s", settings.bootstrap_admin_email)
    except Exception as exc:  # noqa: BLE001 — never block startup on a transient DB hiccup
        logger.warning("Admin bootstrap skipped: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.assert_production_safe()  # refuse insecure prod config
    await _bootstrap_admin()
    yield
    await close_redis()


app = FastAPI(
    title="Lighthouse API",
    version="1.0.0",
    description="Ethically-scoped OSINT investigation platform — public sources only.",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception):  # pragma: no cover
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})


@app.get("/health", tags=["meta"])
async def health() -> dict:
    return {"status": "ok", "service": "lighthouse-api", "version": "1.0.0"}


@app.get("/", tags=["meta"])
async def root() -> dict:
    return {"service": "Lighthouse API", "docs": "/api/docs", "health": "/health"}
