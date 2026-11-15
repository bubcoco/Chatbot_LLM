from langchain_core.messages import AIMessage, ToolMessage

from evals.checks import check_forbidden, check_turn, extract_tool_calls
from evals.models import TurnExpectation


def _msgs():
    return [
        AIMessage(
            content="",
            tool_calls=[{"name": "get_order_status", "args": {"order_no": "BC-1042"}, "id": "c1"}],
        ),
        ToolMessage('{"found": true}', tool_call_id="c1"),
        AIMessage("ok"),
    ]


def test_extract_tool_calls():
    assert extract_tool_calls(_msgs()) == [
        {"name": "get_order_status", "args": {"order_no": "BC-1042"}}
    ]


def test_tool_calls_empty_expectation_fails():
    failures = check_turn(TurnExpectation(tool_calls=[]), "hi", _msgs())
    assert len(failures) == 1 and failures[0].startswith("tool_calls:")


def test_tool_calls_none_not_checked():
    assert check_turn(TurnExpectation(tool_calls=None), "hi", _msgs()) == []


def test_tool_calls_match():
    exp = TurnExpectation(
        tool_calls=[{"name": "get_order_status", "args": {"order_no": "BC-1042"}}]
    )
    assert check_turn(exp, "hi", _msgs()) == []


def test_reply_contains():
    failures = check_turn(TurnExpectation(reply_contains=["A", "B"]), "A only", [])
    assert len(failures) == 1 and "'B'" in failures[0]


def test_reply_contains_any():
    exp = TurnExpectation(reply_contains_any=["x", "y"])
    assert check_turn(exp, "has y", []) == []
    assert len(check_turn(exp, "none", [])) == 1


def test_reply_not_contains():
    failures = check_turn(TurnExpectation(reply_not_contains=["secret"]), "a secret", [])
    assert len(failures) == 1


def test_reply_language():
    failures = check_turn(TurnExpectation(reply_language="th"), "Order is shipped", [])
    assert len(failures) == 1


def test_reply_none_fails_reply_checks():
    for exp in (
        TurnExpectation(reply_contains=["a"]),
        TurnExpectation(reply_contains_any=["a"]),
        TurnExpectation(reply_not_contains=["a"]),
        TurnExpectation(reply_language="en"),
    ):
        assert check_turn(exp, None, []) == ["no reply"]


def test_missing_or_blank_reply_fails_closed():
    # Even a turn with no reply_* checks fails when the graph produced no reply.
    for reply in (None, "", "   "):
        assert check_turn(TurnExpectation(), reply, []) == ["no reply"]


def test_tool_calls_failure_kept_before_no_reply():
    failures = check_turn(TurnExpectation(tool_calls=[]), None, _msgs())
    assert len(failures) == 2
    assert failures[0].startswith("tool_calls:") and failures[1] == "no reply"


def test_tool_calls_wrong_args_fails():
    exp = TurnExpectation(
        tool_calls=[{"name": "get_order_status", "args": {"order_no": "BC-1043"}}]
    )
    failures = check_turn(exp, "hi", _msgs())
    assert len(failures) == 1 and failures[0].startswith("tool_calls:")


def test_forbidden_in_tool_result():
    failures = check_forbidden(
        ["TRACK1"], "clean reply", [ToolMessage('{"tracking_no":"TRACK1"}', tool_call_id="c")]
    )
    assert len(failures) == 1 and "tool result" in failures[0]


def test_forbidden_in_reply():
    failures = check_forbidden(["TRACK1"], "it is TRACK1", [])
    assert len(failures) == 1 and "reply" in failures[0]


def test_forbidden_empty():
    assert check_forbidden([], "anything", _msgs()) == []
