"""Single entry point for executing one customer turn."""

from dataclasses import dataclass

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langgraph.graph.state import CompiledStateGraph

from supportkit.core.graph.state import SupportContext, thread_id_for


@dataclass(frozen=True)
class TurnResult:
    thread_id: str
    turn_id: str
    reply: str | None
    messages: list[AnyMessage]  # this turn only: everything after the turn's HumanMessage


def _config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}, "recursion_limit": 25}


async def run_turn(graph: CompiledStateGraph, ctx: SupportContext, text: str) -> TurnResult:
    thread_id = thread_id_for(ctx)
    out = await graph.ainvoke({"messages": [HumanMessage(text)]}, _config(thread_id), context=ctx)
    msgs = out["messages"]
    last_human = max(i for i, m in enumerate(msgs) if isinstance(m, HumanMessage))
    return TurnResult(
        thread_id, out["turn_id"], out.get("final_reply"), list(msgs[last_human + 1 :])
    )


async def get_history(graph: CompiledStateGraph, ctx: SupportContext) -> list[dict[str, str]]:
    snapshot = await graph.aget_state(_config(thread_id_for(ctx)))
    history: list[dict[str, str]] = []
    for m in snapshot.values.get("messages", []):
        if isinstance(m, HumanMessage):
            history.append({"role": "user", "text": m.text})
        elif isinstance(m, AIMessage) and not m.tool_calls and m.text:
            history.append({"role": "assistant", "text": m.text})
    return history
