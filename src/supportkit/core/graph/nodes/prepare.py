"""prepare: reset per-turn fields."""

from uuid import uuid4

from langchain_core.messages import HumanMessage

from supportkit.core.graph.state import SupportState
from supportkit.core.text import detect_language


def prepare(state: SupportState) -> dict:
    last_human = next((m for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), None)
    text = last_human.text if last_human is not None else ""
    return {
        "turn_id": uuid4().hex,
        "language": detect_language(text),
        "tool_rounds": 0,
        "tool_failures": 0,
        "guard_attempts": 0,
        "guard_violations": [],
        "escalation_reasons": [],
        "draft_reply": None,
        "staff_decision": None,
        "final_reply": None,
        "usage": [],
    }
