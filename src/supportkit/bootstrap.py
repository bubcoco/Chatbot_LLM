"""Runtime wiring: pool -> checkpointer -> tools -> model -> graph."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph.state import CompiledStateGraph
from psycopg_pool import AsyncConnectionPool

from supportkit.core.graph.builder import build_support_graph
from supportkit.core.llm.factory import get_chat_model
from supportkit.core.tools.orders import build_order_tools
from supportkit.db import create_pool


@dataclass(frozen=True)
class SupportRuntime:
    pool: AsyncConnectionPool
    checkpointer: AsyncPostgresSaver
    graph: CompiledStateGraph
    model_spec: str


@asynccontextmanager
async def open_runtime(
    database_url: str, model_spec: str, *, model: BaseChatModel | None = None
) -> AsyncIterator[SupportRuntime]:
    async with create_pool(database_url) as pool:
        # No setup(): `supportkit migrate` owns the checkpointer tables.
        checkpointer = AsyncPostgresSaver(pool)
        tools = build_order_tools(pool)
        chat_model = model or get_chat_model(model_spec)
        graph = build_support_graph(chat_model, tools, checkpointer, model_name=model_spec)
        yield SupportRuntime(pool, checkpointer, graph, model_spec)
