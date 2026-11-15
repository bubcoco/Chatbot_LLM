"""Spec 04: get_order_status repository + tool on real Postgres."""

import json
import logging
import re

import psycopg
import pytest
from langchain_core.messages import AIMessage
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from supportkit.core.graph.state import SupportContext
from supportkit.core.tenancy import repositories
from supportkit.core.tenancy.context import TenantContext
from supportkit.core.tools.orders import build_order_tools

NOW = "2026-11-15T12:00:00+07:00"


async def call_tool(pool, ctx: SupportContext, args: dict, tools=None) -> str:
    tools = tools if tools is not None else build_order_tools(pool)
    builder = StateGraph(MessagesState, context_schema=SupportContext)
    builder.add_node("tools", ToolNode(tools))
    builder.add_edge(START, "tools")
    graph = builder.compile()
    msg = AIMessage(
        content="",
        tool_calls=[{"name": "get_order_status", "args": args, "id": "c1", "type": "tool_call"}],
    )
    out = await graph.ainvoke({"messages": [msg]}, context=ctx)
    return out["messages"][-1].content


def _ctx(shop: str, customer: str | None) -> SupportContext:
    return SupportContext(shop, "web", "u1", customer, NOW)


def _not_found(order_no: str) -> str:
    return json.dumps({"found": False, "order_no": order_no}, ensure_ascii=False)


async def test_found_full_shape(pool, two_shops):
    raw = await call_tool(pool, _ctx(two_shops.shop_a, "C-1"), {"order_no": "BC-1042"})
    assert json.loads(raw) == {
        "found": True,
        "order_no": "BC-1042",
        "status": "shipped",
        "payment_status": "paid",
        "ordered_at": "2026-11-12",
        "total_thb": "1230.00",
        "item_count": 3,
        "shipment": {
            "carrier": "Kerry Express",
            "tracking_no": "TRACK-A-1042",
            "status": "in_transit",
            "shipped_at": "2026-11-13",
            "estimated_delivery_date": "2026-11-16",
            "delivered_at": None,
        },
        "as_of": "2026-11-15T12:00:00+07:00",
    }
    assert list(json.loads(raw)) == [
        "found", "order_no", "status", "payment_status", "ordered_at",
        "total_thb", "item_count", "shipment", "as_of",
    ]


async def test_lowercase_input_no_shipment(pool, two_shops):
    raw = await call_tool(pool, _ctx(two_shops.shop_a, "C-1"), {"order_no": "bc-1043"})
    data = json.loads(raw)
    assert data["found"] is True
    assert data["status"] == "pending_payment"
    assert data["shipment"] is None


async def test_other_customer_same_shop_not_found(pool, two_shops):
    raw = await call_tool(pool, _ctx(two_shops.shop_a, "C-1"), {"order_no": "BC-1050"})
    assert raw == _not_found("BC-1050")


async def test_nonexistent_not_found(pool, two_shops):
    raw = await call_tool(pool, _ctx(two_shops.shop_a, "C-1"), {"order_no": "BC-7777"})
    assert raw == _not_found("BC-7777")


async def test_not_yours_identical_to_nonexistent(pool, two_shops):
    ctx = _ctx(two_shops.shop_a, "C-1")
    not_yours = await call_tool(pool, ctx, {"order_no": "BC-1050"})
    missing = await call_tool(pool, ctx, {"order_no": "BC-7777"})
    assert not_yours.replace("BC-1050", "X") == missing.replace("BC-7777", "X")


async def test_other_shop_same_order_no(pool, two_shops):
    raw = await call_tool(pool, _ctx(two_shops.shop_b, "C-1"), {"order_no": "BC-1042"})
    data = json.loads(raw)
    assert data["found"] is True
    assert data["total_thb"] == "3200.00"
    assert data["shipment"]["tracking_no"] == "TRACK-B-1042"
    assert "TRACK-A-1042" not in raw


async def test_order_exists_only_in_other_shop(pool, two_shops):
    raw = await call_tool(pool, _ctx(two_shops.shop_b, "C-1"), {"order_no": "BC-1050"})
    assert raw == _not_found("BC-1050")


async def test_unverified_user(pool, two_shops):
    raw = await call_tool(pool, _ctx(two_shops.shop_a, None), {"order_no": "BC-1042"})
    assert raw == _not_found("BC-1042")


async def test_llm_supplied_ids_ignored(pool, two_shops):
    args = {"order_no": "BC-1042", "shop_id": two_shops.shop_b, "customer_id": "C-1"}
    raw = await call_tool(pool, _ctx(two_shops.shop_a, "C-2"), args)
    assert json.loads(raw)["found"] is False
    assert "TRACK-A-1042" not in raw
    assert "TRACK-B-1042" not in raw


async def test_sql_injection_attempt(pool, two_shops):
    raw = await call_tool(
        pool, _ctx(two_shops.shop_a, "C-1"), {"order_no": "x'; DROP TABLE orders;--"}
    )
    assert json.loads(raw)["found"] is False
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT count(*) AS n FROM orders WHERE shop_id = %s", (two_shops.shop_a,)
        )
        assert (await cur.fetchone())["n"] == 3


async def test_schema_exposes_only_order_no(pool):
    tools = build_order_tools(pool)
    schema = tools[0].tool_call_schema.model_json_schema()
    assert list(schema["properties"]) == ["order_no"]
    text = json.dumps(schema)
    for banned in ("shop_id", "customer_id", "runtime"):
        assert banned not in text
    assert list(tools[0].args) == ["order_no"]


async def test_db_failure_returns_temporarily_unavailable(pool, two_shops, monkeypatch):
    async def boom(*_a, **_k):
        raise psycopg.OperationalError("down")

    monkeypatch.setattr(repositories, "get_order_status", boom)
    raw = await call_tool(pool, _ctx(two_shops.shop_a, "C-1"), {"order_no": "BC-1042"})
    assert raw == '{"error": "temporarily_unavailable"}'


async def test_repository_unverified_returns_none(pool, two_shops):
    async with pool.connection() as conn:
        result = await repositories.get_order_status(
            conn, TenantContext(two_shops.shop_a, None), "BC-1042"
        )
    assert result is None


async def test_customer_exists_and_shop_has_customers(pool, two_shops):
    async with pool.connection() as conn:
        assert await repositories.customer_exists(conn, TenantContext(two_shops.shop_a, "C-2"))
        assert not await repositories.customer_exists(conn, TenantContext(two_shops.shop_b, "C-2"))
        assert not await repositories.customer_exists(conn, TenantContext(two_shops.shop_a, None))
        assert await repositories.shop_has_customers(conn, two_shops.shop_a)
        assert not await repositories.shop_has_customers(conn, "t-none-x")


async def test_no_pii_in_response(pool, two_shops):
    raw = await call_tool(pool, _ctx(two_shops.shop_a, "C-1"), {"order_no": "BC-1042"})
    # Spec correction (approved by orchestrator): "C-1" is a substring of "BC-1042", so the
    # customer id is checked structurally on the parsed JSON instead of on the raw string.
    data = json.loads(raw)

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                yield "key", key
                yield from walk(value)
        elif isinstance(node, list):
            for value in node:
                yield from walk(value)
        else:
            yield "value", node

    banned_keys = {"customer_id", "shop_id", "full_name", "phone", "email", "order_id"}
    for kind, item in walk(data):
        if kind == "key":
            assert item not in banned_keys
        else:
            assert item not in ("C-1", two_shops.shop_a)
    for banned in ("full_name", "phone", two_shops.shop_a, "0800000000"):
        assert banned not in raw


@pytest.mark.parametrize("raw_no", ["", "  ", "ออเดอร์"])
async def test_malformed_never_queries(pool, two_shops, monkeypatch, raw_no):
    async def boom(*_a, **_k):
        raise AssertionError("must not query")

    monkeypatch.setattr(repositories, "get_order_status", boom)
    raw = await call_tool(pool, _ctx(two_shops.shop_a, "C-1"), {"order_no": raw_no})
    assert raw == json.dumps({"found": False, "order_no": raw_no.strip()[:32]}, ensure_ascii=False)


async def test_log_hygiene(pool, two_shops, caplog):
    ctx = _ctx(two_shops.shop_a, "C-1")
    messages: dict[str, str] = {}
    with caplog.at_level(logging.INFO, logger="supportkit"):
        for key, order_no in [
            ("found", "BC-1042"),
            ("not_yours", "BC-1050"),
            ("missing", "BC-7777"),
            ("malformed", "x'; DROP"),
        ]:
            caplog.clear()
            await call_tool(pool, ctx, {"order_no": order_no})
            messages[key] = " | ".join(r.getMessage() for r in caplog.records)
        assert all(messages.values())
    for msg in messages.values():
        for banned in ("BC-1042", "BC-1050", "BC-7777"):
            assert banned not in msg
        assert "customer" not in msg
        assert not re.search(r"\bC-1\b", msg)
    assert messages["not_yours"] == messages["missing"]


async def test_repository_unverified_issues_no_query(pool, two_shops, monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("query issued")

    async with pool.connection() as conn:
        monkeypatch.setattr(conn, "cursor", boom)
        monkeypatch.setattr(conn, "execute", boom)
        result = await repositories.get_order_status(
            conn, TenantContext(two_shops.shop_a, None), "BC-1042"
        )
    assert result is None
