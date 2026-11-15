"""Eval case schema and dataset loader. Later phases may add optional fields only."""

import json
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

Category = Literal[
    "correct_answer",
    "tool_selection",
    "groundedness",
    "memory",
    "escalation",
    "security",
    "out_of_scope",
    "language",
]

CASE_ID_RE = re.compile(r"^[a-z0-9-]+$")


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ToolCallExpectation(_Model):
    name: str
    args: dict[str, Any]


class TurnExpectation(_Model):
    tool_calls: list[ToolCallExpectation] | None = None  # None = not checked; [] = none allowed
    reply_contains: list[str] = []
    reply_contains_any: list[str] = []
    reply_not_contains: list[str] = []
    reply_language: Literal["th", "en"] | None = None


class Turn(_Model):
    user: str
    restart_before: bool = False
    expected: TurnExpectation = TurnExpectation()


class CustomerContext(_Model):
    customer_id: str | None
    channel: Literal["line", "web"] = "web"


class CaseExpectation(_Model):
    forbidden: list[str] = []


class EvalCase(_Model):
    id: str
    category: Category
    language: Literal["th", "en"]
    shop_id: str
    customer_context: CustomerContext
    tags: list[str] = []
    notes: str = ""
    turns: list[Turn] = Field(min_length=1)
    expected: CaseExpectation = CaseExpectation()

    @field_validator("id")
    @classmethod
    def _check_id(cls, v: str) -> str:
        if not CASE_ID_RE.fullmatch(v):
            raise ValueError(f"id must match {CASE_ID_RE.pattern}")
        return v


def load_cases(path: Path) -> list[EvalCase]:
    """One JSON object per non-blank line (UTF-8). ValueError names the offending line number."""
    cases: list[EvalCase] = []
    seen: set[str] = set()
    text = Path(path).read_text(encoding="utf-8")
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError(f"{path}: line {lineno}: invalid JSON: {e}") from e
        try:
            case = EvalCase.model_validate(data)
        except ValidationError as e:
            raise ValueError(f"{path}: line {lineno}: schema violation: {e}") from e
        if case.id in seen:
            raise ValueError(f"{path}: line {lineno}: duplicate id {case.id!r}")
        seen.add(case.id)
        cases.append(case)
    return cases
