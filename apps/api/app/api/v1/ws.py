"""WebSocket: live investigation feed.

Auth via an access token in the query string (cookies aren't sent cross-origin to the WS
host). Read-only: the server ignores client messages and only relays case events from the
Redis pub/sub channel, so there's no actionable message to authorize beyond connection.
"""
from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.events import case_channel
from app.core.rbac import authenticate_token
from app.core.redis_client import make_redis
from app.db.models import Case, CaseMember
from app.db.session import SessionLocal
from lighthouse_shared import Role

router = APIRouter()


async def _relay_redis_to_ws(pubsub, websocket: WebSocket) -> None:
    async for message in pubsub.listen():
        if message.get("type") != "message":
            continue
        data = message["data"]
        await websocket.send_text(data if isinstance(data, str) else data.decode())


async def _drain_client(websocket: WebSocket) -> None:
    # We don't accept commands over WS; reading lets us detect disconnects promptly.
    while True:
        await websocket.receive_text()


@router.websocket("/ws/cases/{case_id}")
async def case_feed(websocket: WebSocket, case_id: uuid.UUID, token: str = Query(...)) -> None:
    async with SessionLocal() as db:
        user = await authenticate_token(db, token)
        if user is None:
            await websocket.close(code=4401)
            return
        case = await db.get(Case, case_id)
        if case is None or case.deleted_at is not None:
            await websocket.close(code=4404)
            return
        if not (user.role == Role.ADMIN or case.owner_id == user.id):
            member = await db.get(CaseMember, {"case_id": case_id, "user_id": user.id})
            if member is None:
                await websocket.close(code=4403)
                return

    await websocket.accept()
    redis = make_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(case_channel(case_id))
    await websocket.send_json({"type": "connected", "case_id": str(case_id)})

    relay = asyncio.create_task(_relay_redis_to_ws(pubsub, websocket))
    drain = asyncio.create_task(_drain_client(websocket))
    try:
        done, pending = await asyncio.wait({relay, drain}, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
    except WebSocketDisconnect:
        pass
    finally:
        relay.cancel()
        drain.cancel()
        try:
            await pubsub.unsubscribe(case_channel(case_id))
            await pubsub.aclose()
        except Exception:  # noqa: BLE001
            pass
        await redis.aclose()
