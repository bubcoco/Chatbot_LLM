"""Demo chat router (Phase 1). Identity comes only from api.demo_identity."""

import asyncio
import logging
from typing import Literal

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from supportkit.api.demo_identity import demo_context
from supportkit.core.graph.state import SupportContext, thread_id_for
from supportkit.core.graph.turn import get_history, run_turn

logger = logging.getLogger(__name__)

router = APIRouter(tags=["demo"])


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    reply: str
    thread_id: str
    turn_id: str


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: str


class HistoryResponse(BaseModel):
    thread_id: str
    messages: list[HistoryMessage]


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest, request: Request, ctx: SupportContext = Depends(demo_context)  # noqa: B008
) -> ChatResponse:
    text = body.message.strip()
    if not text:
        raise HTTPException(422, "message must not be blank")
    thread_id = thread_id_for(ctx)
    lock = request.app.state.thread_locks.setdefault(thread_id, asyncio.Lock())
    try:
        async with lock:
            result = await run_turn(request.app.state.runtime.graph, ctx, text)
    except psycopg.OperationalError:
        raise HTTPException(503, "database_unavailable") from None
    except Exception:
        logger.exception("chat turn failed")
        raise HTTPException(502, "agent_error") from None
    if result.reply is None:
        raise HTTPException(502, "agent_error")
    return ChatResponse(reply=result.reply, thread_id=result.thread_id, turn_id=result.turn_id)


@router.get("/chat/history", response_model=HistoryResponse)
async def history(
    request: Request, ctx: SupportContext = Depends(demo_context)  # noqa: B008
) -> HistoryResponse:
    try:
        messages = await get_history(request.app.state.runtime.graph, ctx)
    except psycopg.OperationalError:
        raise HTTPException(503, "database_unavailable") from None
    return HistoryResponse(thread_id=thread_id_for(ctx), messages=messages)
