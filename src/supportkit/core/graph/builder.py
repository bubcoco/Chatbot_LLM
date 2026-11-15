"""Support graph: prepare -> agent <-> tools -> finalize."""

from collections.abc import Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

from supportkit.core.graph.nodes.agent import make_agent_node
from supportkit.core.graph.nodes.finalize import finalize
from supportkit.core.graph.nodes.prepare import prepare
from supportkit.core.graph.routing import route_after_agent
from supportkit.core.graph.state import SupportContext, SupportState


def build_support_graph(
    model: BaseChatModel,
    tools: Sequence[BaseTool],
    checkpointer: BaseCheckpointSaver | None,
    *,
    model_name: str,
) -> CompiledStateGraph:
    g = StateGraph(SupportState, context_schema=SupportContext)
    g.add_node("prepare", prepare)
    g.add_node("agent", make_agent_node(model.bind_tools(list(tools)), model_name))
    g.add_node("tools", ToolNode(list(tools)))
    g.add_node("finalize", finalize)
    g.add_edge(START, "prepare")
    g.add_edge("prepare", "agent")
    g.add_conditional_edges("agent", route_after_agent, ["tools", "finalize"])
    g.add_edge("tools", "agent")
    g.add_edge("finalize", END)
    return g.compile(checkpointer=checkpointer)
