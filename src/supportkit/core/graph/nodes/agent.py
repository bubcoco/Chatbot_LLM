"""agent: one model call."""

from collections.abc import Awaitable, Callable

from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import Runnable
from langgraph.runtime import Runtime

from supportkit.core.graph.prompts import FALLBACK_REPLY, MAX_TOOL_ROUNDS, build_system_prompt
from supportkit.core.graph.state import SupportContext, SupportState


def make_agent_node(
    model_with_tools: Runnable, model_name: str
) -> Callable[[SupportState, Runtime[SupportContext]], Awaitable[dict]]:
    async def agent(state: SupportState, runtime: Runtime[SupportContext]) -> dict:
        response = await model_with_tools.ainvoke(
            [SystemMessage(build_system_prompt(runtime.context)), *state["messages"]]
        )
        meta = response.usage_metadata or {}
        entry = {
            "node": "agent",
            "model": model_name,
            "input_tokens": int(meta.get("input_tokens", 0) or 0),
            "output_tokens": int(meta.get("output_tokens", 0) or 0),
        }
        usage = [*state.get("usage", []), entry]
        rounds = state.get("tool_rounds", 0)
        if response.tool_calls and rounds < MAX_TOOL_ROUNDS:
            return {"messages": [response], "tool_rounds": rounds + 1, "usage": usage}
        text = "" if response.tool_calls else response.text.strip()
        if not text:
            fallback = FALLBACK_REPLY[state["language"]]
            return {
                "messages": [AIMessage(content=fallback)],
                "draft_reply": fallback,
                "usage": usage,
            }
        return {"messages": [response], "draft_reply": text, "usage": usage}

    return agent
