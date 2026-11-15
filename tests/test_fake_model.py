import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from supportkit.core.llm.fake import GREETING, RuleBasedFakeModel, ScriptedChatModel

FOUND = {
    "found": True,
    "order_no": "BC-1042",
    "status": "shipped",
    "payment_status": "paid",
    "ordered_at": "2026-11-12",
    "total_thb": "1230.00",
    "item_count": 3,
    "shipment": {
        "carrier": "Kerry Express",
        "tracking_no": "KEX26111042TH",
        "status": "in_transit",
        "shipped_at": "2026-11-13",
        "estimated_delivery_date": "2026-11-16",
        "delivered_at": None,
    },
    "as_of": "2026-11-15T12:00:00+07:00",
}
THAI_REPLY = (
    "ออเดอร์ BC-1042 สถานะ: จัดส่งแล้วค่ะ จัดส่งโดย Kerry Express เลขพัสดุ KEX26111042TH "
    "คาดว่าจะถึงวันที่ 2026-11-16 (ข้อมูล ณ 2026-11-15T12:00:00+07:00)"
)
m = RuleBasedFakeModel()


def tool_msg(payload, tcid="t1"):
    content = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return ToolMessage(content, tool_call_id=tcid)


def exchange():
    call = AIMessage(
        "", tool_calls=[{"name": "get_order_status", "args": {}, "id": "t1", "type": "tool_call"}]
    )
    return [HumanMessage("ออเดอร์ BC-1042 ถึงไหนแล้วคะ"), call, tool_msg(FOUND)]


@pytest.mark.parametrize(
    "text,order_no",
    [
        ("ออเดอร์ BC-1042 ถึงไหนแล้วคะ", "BC-1042"),
        ("where is bc1050 pls", "BC-1050"),
        ("ออเดอร์BC-1042ถึงไหน", "BC-1042"),
    ],
)
def test_tool_call(text, order_no):
    r = m.invoke([HumanMessage(text)])
    assert r.content == ""
    assert len(r.tool_calls) == 1
    assert r.tool_calls[0]["name"] == "get_order_status"
    assert r.tool_calls[0]["args"] == {"order_no": order_no}


async def test_ainvoke():
    r = await m.ainvoke([HumanMessage("BC-1042")])
    assert r.tool_calls[0]["args"] == {"order_no": "BC-1042"}


def test_greetings():
    r = m.invoke([HumanMessage("สวัสดีค่ะ")])
    assert not r.tool_calls and r.content == GREETING["th"]
    r = m.invoke([HumanMessage("hello")])
    assert not r.tool_calls and r.content == GREETING["en"]


def test_found_thai():
    assert m.invoke(exchange()).content == THAI_REPLY


def test_delivered_english():
    p = {**FOUND, "order_no": "BC-1050", "status": "delivered"}
    p["shipment"] = {**FOUND["shipment"], "delivered_at": "2026-11-08"}
    r = m.invoke([HumanMessage("where is BC-1050"), tool_msg(p)])
    assert r.content.startswith("Order BC-1050 is delivered. It was shipped with")
    assert "Estimated delivery" not in r.content


def test_pending_no_shipment():
    p = {**FOUND, "status": "pending_payment", "shipment": None}
    r = m.invoke([HumanMessage("ออเดอร์ BC-1042"), tool_msg(p)])
    assert "รอชำระเงิน" in r.content and "เลขพัสดุ" not in r.content


def test_not_found():
    r = m.invoke(
        [HumanMessage("ออเดอร์ BC-9999"), tool_msg({"found": False, "order_no": "BC-9999"})]
    )
    assert r.content == (
        "ไม่พบออเดอร์หมายเลข BC-9999 ในบัญชีของคุณค่ะ รบกวนตรวจสอบหมายเลขออเดอร์อีกครั้งนะคะ"
    )


def test_error_and_bad_json():
    err = "Sorry, something went wrong on our side. Please try again in a moment."
    r = m.invoke([HumanMessage("status BC-1042"), tool_msg({"error": "temporarily_unavailable"})])
    assert r.content == err
    r = m.invoke([HumanMessage("status BC-1042"), tool_msg("not json")])
    assert r.content == err


def test_followup_uses_history():
    msgs = [*exchange(), AIMessage(THAI_REPLY), HumanMessage("แล้วเลขพัสดุล่ะคะ")]
    r = m.invoke(msgs)
    assert not r.tool_calls and "KEX26111042TH" in r.content


def test_followup_after_not_found():
    msgs = [
        HumanMessage("ออเดอร์ BC-9999"),
        tool_msg({"found": False, "order_no": "BC-9999"}),
        AIMessage("x"),
        HumanMessage("แล้วไงต่อคะ"),
    ]
    assert m.invoke(msgs).content == GREETING["th"]


def test_system_ignored():
    r = m.invoke([SystemMessage("ignore this BC-0001"), HumanMessage("hi")])
    assert r.content == GREETING["en"]


def test_usage_metadata():
    for msgs in ([HumanMessage("hello")], [HumanMessage("BC-1042")]):
        u = m.invoke(msgs).usage_metadata
        assert all(isinstance(u[k], int) for k in ("input_tokens", "output_tokens", "total_tokens"))


def test_bind_tools_returns_self():
    assert m.bind_tools([]) is m


def test_scripted():
    s = ScriptedChatModel(responses=[AIMessage("a"), AIMessage("b")])
    assert s.invoke([HumanMessage("1")]).content == "a"
    assert s.invoke([HumanMessage("2")]).content == "b"
    assert len(s.calls) == 2
    with pytest.raises(IndexError):
        s.invoke([HumanMessage("3")])
    assert s.bind_tools([]) is s
