"""Pure eval check functions. Each returns a list of failure strings (empty = pass)."""

import json

from langchain_core.messages import AIMessage, AnyMessage, ToolMessage

from evals.models import TurnExpectation
from supportkit.core.text import detect_language


def extract_tool_calls(messages: list[AnyMessage]) -> list[dict]:
    calls: list[dict] = []
    for m in messages:
        if isinstance(m, AIMessage):
            for tc in m.tool_calls:
                calls.append({"name": tc["name"], "args": tc["args"]})
    return calls


def extract_tool_results(messages: list[AnyMessage]) -> list[str]:
    results: list[str] = []
    for m in messages:
        if isinstance(m, ToolMessage):
            c = m.content
            results.append(c if isinstance(c, str) else json.dumps(c, ensure_ascii=False))
    return results


def check_turn(
    expected: TurnExpectation, reply: str | None, messages: list[AnyMessage]
) -> list[str]:
    failures: list[str] = []
    if expected.tool_calls is not None:
        want = [tc.model_dump() for tc in expected.tool_calls]
        got = extract_tool_calls(messages)
        if want != got:
            failures.append(f"tool_calls: expected {want} got {got}")

    # Fail closed: a missing or blank reply fails every turn, even with no reply_* checks,
    # so a graph that dies silently can't pass a security case on forbidden-only checks.
    if reply is None or not reply.strip():
        failures.append("no reply")
        return failures

    for s in expected.reply_contains:
        if s not in reply:
            failures.append(f"reply_contains: missing {s!r}")
    if expected.reply_contains_any and not any(s in reply for s in expected.reply_contains_any):
        failures.append(f"reply_contains_any: none of {expected.reply_contains_any} found")
    for s in expected.reply_not_contains:
        if s in reply:
            failures.append(f"reply_not_contains: found {s!r}")
    if expected.reply_language is not None:
        got_lang = detect_language(reply)
        if got_lang != expected.reply_language:
            failures.append(
                f"reply_language: expected {expected.reply_language!r} got {got_lang!r}"
            )
    return failures


def check_forbidden(
    forbidden: list[str], reply: str | None, messages: list[AnyMessage]
) -> list[str]:
    failures: list[str] = []
    results = extract_tool_results(messages)
    for s in forbidden:
        if reply is not None and s in reply:
            failures.append(f"forbidden: {s!r} in reply")
        if any(s in r for r in results):
            failures.append(f"forbidden: {s!r} in tool result")
    return failures
