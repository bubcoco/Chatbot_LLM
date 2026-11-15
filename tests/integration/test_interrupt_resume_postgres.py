"""Phase 0 spike: interrupt -> (new checkpointer = simulated restart) -> resume, on real Postgres.

Proves the mechanism the handoff design relies on (PLAN.md 2.4):
- interrupt(payload, response_schema=...) pauses and surfaces __interrupt__
- state survives in Postgres across a fresh checkpointer connection
- Command(resume=...) is validated against the Pydantic schema
- the interrupt node re-runs from the top on resume (side effects belong elsewhere)
"""

import os
import uuid
from typing import Literal, TypedDict

import psycopg
import pytest
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from pydantic import BaseModel, ValidationError

from supportkit.settings import get_settings

os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK", "true")
DB_URL = get_settings().database_url


def _db_available() -> bool:
    try:
        with psycopg.connect(DB_URL, connect_timeout=2):
            return True
    except psycopg.OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="Postgres not reachable")


class StaffDecision(BaseModel):
    action: Literal["approve", "edit", "takeover"]
    text: str | None = None


class State(TypedDict):
    draft_reply: str
    final_reply: str | None
    handoff_entries: int


def open_ticket(state: State) -> dict:
    return {"handoff_entries": state.get("handoff_entries", 0)}


def human_handoff(state: State) -> dict:
    # Counts executions of this node body, including the re-run on resume.
    entries = state["handoff_entries"] + 1
    decision = interrupt(
        {"draft": state["draft_reply"], "reason": "refund_over_limit"},
        response_schema=StaffDecision,
    )
    if isinstance(decision, dict):
        decision = StaffDecision(**decision)
    if decision.action == "approve":
        reply = state["draft_reply"]
    elif decision.action == "edit":
        reply = decision.text
    else:
        reply = None
    return {"final_reply": reply, "handoff_entries": entries}


def build(checkpointer):
    g = StateGraph(State)
    g.add_node("open_ticket", open_ticket)
    g.add_node("human_handoff", human_handoff)
    g.add_edge(START, "open_ticket")
    g.add_edge("open_ticket", "human_handoff")
    g.add_edge("human_handoff", END)
    return g.compile(checkpointer=checkpointer)


def _config():
    return {"configurable": {"thread_id": f"test:{uuid.uuid4()}"}}


def test_interrupt_survives_restart_and_resumes_with_edit():
    config = _config()

    with PostgresSaver.from_conn_string(DB_URL) as cp:
        result = build(cp).invoke({"draft_reply": "คืนเงิน 1,500 บาทค่ะ"}, config)
        assert "__interrupt__" in result
        assert result["__interrupt__"][0].value["reason"] == "refund_over_limit"

    # Fresh connection = simulated server restart.
    with PostgresSaver.from_conn_string(DB_URL) as cp:
        graph = build(cp)
        assert graph.get_state(config).next == ("human_handoff",)
        out = graph.invoke(
            Command(resume={"action": "edit", "text": "ขอตรวจสอบก่อนนะคะ"}), config
        )
        assert out["final_reply"] == "ขอตรวจสอบก่อนนะคะ"
        assert out["handoff_entries"] == 1  # state written once, after resume
        cp.delete_thread(config["configurable"]["thread_id"])


def test_resume_value_is_validated_by_response_schema():
    config = _config()
    with PostgresSaver.from_conn_string(DB_URL) as cp:
        graph = build(cp)
        graph.invoke({"draft_reply": "draft"}, config)
        with pytest.raises(ValidationError):
            graph.invoke(Command(resume={"action": "refund_everything"}), config)
        # Thread is still paused and can be resumed correctly afterwards.
        out = graph.invoke(Command(resume={"action": "approve"}), config)
        assert out["final_reply"] == "draft"
        cp.delete_thread(config["configurable"]["thread_id"])


def test_delete_thread_removes_checkpoints():
    config = _config()
    tid = config["configurable"]["thread_id"]
    with PostgresSaver.from_conn_string(DB_URL) as cp:
        build(cp).invoke({"draft_reply": "x"}, config)
        cp.delete_thread(tid)
    with psycopg.connect(DB_URL) as conn:
        n = conn.execute("SELECT count(*) FROM checkpoints WHERE thread_id = %s", (tid,))
        assert n.fetchone()[0] == 0
