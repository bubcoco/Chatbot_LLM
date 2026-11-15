"""Conditional edges."""

from typing import Literal

from langchain_core.messages import AIMessage

from supportkit.core.graph.state import SupportState


def route_after_agent(state: SupportState) -> Literal["tools", "finalize"]:
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "tools"
    return "finalize"
