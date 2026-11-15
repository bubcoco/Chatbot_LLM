import json
from uuid import uuid4

from langchain.tools import ToolRuntime
from langchain_core.tools import tool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from supportkit.core.graph.builder import build_support_graph
from supportkit.core.graph.state import SupportContext
from supportkit.core.graph.turn import get_history, run_turn
from supportkit.core.llm.fake import RuleBasedFakeModel
from supportkit.db import create_pool


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


async def _count(pool, thread_id: str) -> int:
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT count(*) AS n FROM checkpoints WHERE thread_id = %s", (thread_id,)
        )
        return (await cur.fetchone())["n"]


async def test_restart_keeps_history(pool, database_url):
    ctx = SupportContext(
        "t-graph", "web", f"u-{uuid4().hex[:8]}", "C-1", "2026-11-15T12:00:00+07:00"
    )
    saver_a = AsyncPostgresSaver(pool)
    seen_a: list = []
    graph_a = build_support_graph(
        RuleBasedFakeModel(), [make_stub_tool(seen_a)], saver_a, model_name="test-model"
    )
    r1 = await run_turn(graph_a, ctx, "ออเดอร์ BC-1042 ถึงไหนแล้วคะ")
    assert seen_a == [("t-graph", "C-1", "BC-1042")]
    try:
        assert await _count(pool, r1.thread_id) > 0
        async with create_pool(database_url, max_size=2) as pool_b:
            saver_b = AsyncPostgresSaver(pool_b)
            seen_b: list = []
            graph_b = build_support_graph(
                RuleBasedFakeModel(), [make_stub_tool(seen_b)], saver_b, model_name="test-model"
            )
            r2 = await run_turn(graph_b, ctx, "แล้วเลขพัสดุล่ะคะ")
            assert "KEX26111042TH" in r2.reply
            assert seen_b == []
            assert len(await get_history(graph_b, ctx)) == 4
    finally:
        await saver_a.adelete_thread(r1.thread_id)
    assert await _count(pool, r1.thread_id) == 0
