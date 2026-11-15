"""Graph context and state (PLAN.md 2.7)."""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal, TypedDict
from zoneinfo import ZoneInfo

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from supportkit.core.tenancy.context import TenantContext

CHANNEL_USER_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")  # no ":" -> thread_id is unambiguous


@dataclass(frozen=True)
class SupportContext:
    """Server-supplied only, never checkpointed."""

    shop_id: str
    channel: Literal["line", "web"]
    channel_user_id: str
    customer_id: str | None  # None = identity not verified
    now: str  # ISO datetime, Asia/Bangkok

    def __post_init__(self) -> None:
        TenantContext(self.shop_id, self.customer_id)  # validates both ids
        if self.channel not in ("line", "web"):
            raise ValueError(f"invalid channel: {self.channel!r}")
        if not isinstance(self.channel_user_id, str) or not CHANNEL_USER_ID_RE.fullmatch(
            self.channel_user_id
        ):
            raise ValueError(f"invalid channel_user_id: {self.channel_user_id!r}")

    @property
    def tenant(self) -> TenantContext:
        return TenantContext(self.shop_id, self.customer_id)


def thread_id_for(ctx: SupportContext) -> str:
    return f"{ctx.shop_id}:{ctx.channel}:{ctx.channel_user_id}"


def bangkok_now() -> str:
    return datetime.now(ZoneInfo("Asia/Bangkok")).isoformat(timespec="seconds")


class SupportState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    summary: str  # summary of older, removed messages
    # --- per-turn fields (reset in prepare) ---
    turn_id: str
    language: Literal["th", "en"]
    triage: dict | None  # intent, in_scope, injection_risk, sentiment, wants_human
    memory_context: str  # memory formatted for the prompt
    in_business_hours: bool
    tool_rounds: int
    tool_failures: int
    guard_attempts: int
    guard_violations: list[str]
    escalation_reasons: list[str]
    draft_reply: str | None
    staff_decision: dict | None  # {action, text, staff_id}
    handoff_mode: Literal["none", "human"]
    final_reply: str | None
    usage: list[dict]  # {node, model, input_tokens, output_tokens}
