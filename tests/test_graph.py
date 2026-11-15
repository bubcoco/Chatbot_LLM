import json
import re
from uuid import uuid4

from langchain.tools import ToolRuntime
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

from supportkit.core.graph.builder import build_support_graph
from supportkit.core.graph.prompts import FALLBACK_REPLY
from supportkit.core.graph.state import SupportContext, thread_id_for
from supportkit.core.graph.turn import get_history, run_turn
from supportkit.core.llm.fake import GREETING, RuleBasedFakeModel, ScriptedChatModel

CTX = SupportContext("t-graph", "web", f"u-{uuid4().hex[:8]}", "C-1", "2026-11-15T12:00:00+07:00")
TH1 = "ออเดอร์ BC-1042 ถึงไหนแล้วคะ"


def make_stub_tool(seen: list):
    @tool
    async def get_order_status(order_no: str, runtime: ToolRuntime[SupportContext]) -> str:
        """Stub."""
        seen.append((runtime.context.shop_id, runtime.context.customer_id, order_no))
        return json.dumps(
            {
                "found": True,
                "order_no": order_no,
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
            },
            ensure_ascii=False,
        )

    return get_order_status


def fresh_ctx() -> SupportContext:
    return SupportContext("t-graph", "web", f"u-{uuid4().hex[:8]}", "C-1", CTX.now)


def graph_with(model, seen, saver=None):
    return build_support_graph(
        model, [make_stub_tool(seen)], saver or InMemorySaver(), model_name="test-model"
    )


def cfg(ctx):
    return {"configurable": {"thread_id": thread_id_for(ctx)}}


def tc(order_no="BC-1", **extra):
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "get_order_status",
                "args": {"order_no": order_no, **extra},
                "id": f"call_{uuid4().hex[:10]}",
                "type": "tool_call",
            }
        ],
    )


async def test_order_flow():
    seen: list = []
    ctx = fresh_ctx()
    g = graph_with(RuleBasedFakeModel(), seen)
    r = await run_turn(g, ctx, TH1)
    assert "KEX26111042TH" in r.reply and "BC-1042" in r.reply
    assert seen == [("t-graph", "C-1", "BC-1042")]
    assert [type(m) for m in r.messages] == [AIMessage, ToolMessage, AIMessage]
    assert r.messages[0].tool_calls
    assert r.thread_id == f"t-graph:web:{ctx.channel_user_id}"
    assert re.fullmatch(r"[0-9a-f]{32}", r.turn_id)


async def test_followup_and_state():
    seen: list = []
    ctx = fresh_ctx()
    g = graph_with(RuleBasedFakeModel(), seen)
    r1 = await run_turn(g, ctx, TH1)
    snap = await g.aget_state(cfg(ctx))
    v = snap.values
    assert v["language"] == "th"
    assert v["tool_rounds"] == 1
    assert v["final_reply"] == v["draft_reply"]
    assert len(v["usage"]) == 2
    for e in v["usage"]:
        assert set(e) == {"node", "model", "input_tokens", "output_tokens"}
        assert e["model"] == "test-model"
    r2 = await run_turn(g, ctx, "แล้วเลขพัสดุล่ะคะ")
    assert "KEX26111042TH" in r2.reply
    assert len(seen) == 1
    assert r2.turn_id != r1.turn_id
    hist = await get_history(g, ctx)
    assert [h["role"] for h in hist] == ["user", "assistant", "user", "assistant"]
    assert all(h["text"] for h in hist)
    assert await get_history(g, fresh_ctx()) == []


async def test_english_greeting():
    seen: list = []
    ctx = fresh_ctx()
    g = graph_with(RuleBasedFakeModel(), seen)
    r = await run_turn(g, ctx, "hello")
    assert r.reply == GREETING["en"]
    assert seen == []
    v = (await g.aget_state(cfg(ctx))).values
    assert v["language"] == "en" and v["tool_rounds"] == 0


async def test_tool_round_limit():
    seen: list = []
    ctx = fresh_ctx()
    model = ScriptedChatModel(responses=[tc() for _ in range(6)])
    g = graph_with(model, seen)
    r = await run_turn(g, ctx, TH1)
    assert r.reply == FALLBACK_REPLY["th"]
    assert len(seen) == 4
    msgs = (await g.aget_state(cfg(ctx))).values["messages"]
    for i, m in enumerate(msgs):
        if isinstance(m, AIMessage) and m.tool_calls:
            assert isinstance(msgs[i + 1], ToolMessage)


async def test_empty_reply_fallback():
    ctx = fresh_ctx()
    g = graph_with(ScriptedChatModel(responses=[AIMessage(content="")]), [])
    r = await run_turn(g, ctx, TH1)
    assert r.reply == FALLBACK_REPLY["th"]
    g2 = graph_with(ScriptedChatModel(responses=[AIMessage(content="")]), [])
    r2 = await run_turn(g2, fresh_ctx(), "hello")
    assert r2.reply == FALLBACK_REPLY["en"]


async def test_content_blocks_flattened():
    msg = AIMessage(content=[{"type": "text", "text": "สวัสดีค่ะ"}])
    g = graph_with(ScriptedChatModel(responses=[msg]), [])
    r = await run_turn(g, fresh_ctx(), "สวัสดี")
    assert r.reply == "สวัสดีค่ะ"


async def test_system_prompt_not_leaking_or_stored():
    ctx = fresh_ctx()
    model = ScriptedChatModel(responses=[AIMessage("ok")])
    g = graph_with(model, [])
    await run_turn(g, ctx, "hello")
    first = model.calls[0][0]
    assert isinstance(first, SystemMessage)
    assert "2026-11-15T12:00:00+07:00" in first.content
    for secret in ("t-graph", "C-1", ctx.channel_user_id):
        assert secret not in first.content
    msgs = (await g.aget_state(cfg(ctx))).values["messages"]
    assert not any(isinstance(m, SystemMessage) for m in msgs)


async def test_threads_independent():
    c1, c2 = fresh_ctx(), fresh_ctx()
    g = graph_with(RuleBasedFakeModel(), [])
    await run_turn(g, c1, "hello")
    await run_turn(g, c2, TH1)
    h1, h2 = await get_history(g, c1), await get_history(g, c2)
    assert len(h1) == 2 and len(h2) == 2
    assert h1[0]["text"] == "hello" and h2[0]["text"] == TH1


def test_graph_nodes():
    g = graph_with(RuleBasedFakeModel(), [])
    ids = set(g.get_graph().nodes)
    assert ids == {"__start__", "prepare", "agent", "tools", "finalize", "__end__"}


async def test_llm_cannot_override_tenant_args():
    seen: list = []
    model = ScriptedChatModel(
        responses=[tc("BC-1", shop_id="evil", customer_id="C-9"), AIMessage("done")]
    )
    g = graph_with(model, seen)
    await run_turn(g, fresh_ctx(), "BC-1")
    assert seen == [("t-graph", "C-1", "BC-1")]
