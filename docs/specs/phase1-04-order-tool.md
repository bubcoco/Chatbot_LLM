# Phase 1 · Spec 04 — Order repository + `get_order_status` tool

**Suggested implementer:** `implementer` (tenancy and ownership enforcement)
**Depends on:** 01, 02 · **Blocks:** 07 · **Parallel with:** 03, 06

## Goal
Implement the one Phase 1 tool. `get_order_status` looks an order up by `shop_id AND customer_id AND order_no`, where the two ids come only from `runtime.context`. An order that does not exist, belongs to another customer, belongs to another shop, or is requested by an unverified user produces the **byte-identical** tool response. The tool's LLM-visible schema contains only `order_no`.

## Files
| Path | Action | Purpose |
|---|---|---|
| `src/supportkit/core/tenancy/repositories.py` | create | SQL, all taking a mandatory `TenantContext` |
| `src/supportkit/core/tools/__init__.py` | create | empty |
| `src/supportkit/core/tools/orders.py` | create | `normalize_order_no`, `build_order_tools` |
| `tests/test_order_no.py` | create | unit tests |
| `tests/integration/conftest.py` | create | `two_shops` fixture (reused by spec 07) |
| `tests/integration/test_order_tool.py` | create | repository + tool tests on real Postgres |

## Interfaces

### `core/tenancy/repositories.py`
```python
@dataclass(frozen=True, slots=True)
class ShipmentSummary:
    carrier: str
    tracking_no: str
    status: str
    shipped_at: datetime | None
    estimated_delivery_date: date | None
    delivered_at: datetime | None

@dataclass(frozen=True, slots=True)
class OrderStatusRecord:
    order_no: str
    status: str
    payment_status: str
    ordered_at: datetime
    total_thb: Decimal
    item_count: int
    synced_at: datetime
    shipment: ShipmentSummary | None

async def get_order_status(
    conn: psycopg.AsyncConnection, tenant: TenantContext, order_no: str
) -> OrderStatusRecord | None: ...

async def customer_exists(conn: psycopg.AsyncConnection, tenant: TenantContext) -> bool:
    """True iff tenant.customer_id is not None and that customer row exists in tenant.shop_id."""

async def shop_has_customers(conn: psycopg.AsyncConnection, shop_id: str) -> bool:
    """True iff at least one customers row has this shop_id (Phase 1 stand-in for 'shop exists')."""
```
`get_order_status` runs exactly this one statement (use `conn.cursor(row_factory=dict_row)`):
```sql
SELECT o.order_no, o.status, o.payment_status, o.ordered_at, o.total_thb, o.synced_at,
       (SELECT COALESCE(SUM(i.qty), 0) FROM order_items i
         WHERE i.shop_id = o.shop_id AND i.order_id = o.order_id) AS item_count,
       s.carrier, s.tracking_no, s.status AS shipment_status,
       s.shipped_at, s.estimated_delivery_date, s.delivered_at
FROM orders o
LEFT JOIN LATERAL (
    SELECT sh.carrier, sh.tracking_no, sh.status, sh.shipped_at,
           sh.estimated_delivery_date, sh.delivered_at
    FROM shipments sh
    WHERE sh.shop_id = o.shop_id AND sh.order_id = o.order_id
    ORDER BY sh.shipped_at DESC NULLS LAST, sh.shipment_id DESC
    LIMIT 1
) s ON TRUE
WHERE o.shop_id = %(shop_id)s AND o.customer_id = %(customer_id)s AND o.order_no = %(order_no)s
```
`customer_exists`: `SELECT 1 FROM customers WHERE shop_id = %s AND customer_id = %s`.
`shop_has_customers`: `SELECT 1 FROM customers WHERE shop_id = %s LIMIT 1`.

### `core/tools/orders.py`
```python
ORDER_NO_RE = re.compile(r"^[A-Z0-9][A-Z0-9-]{2,19}$")

def normalize_order_no(raw: str) -> str | None:
    """strip → remove one leading '#' → strip → upper. Return it if it matches ORDER_NO_RE, else None."""

def build_order_tools(pool: AsyncConnectionPool) -> list[BaseTool]:
    """Returns [get_order_status]. The tool closes over `pool`."""
```
The tool, defined inside `build_order_tools` with `langchain_core.tools.tool`:
```python
@tool
async def get_order_status(order_no: str, runtime: ToolRuntime[SupportContext]) -> str:
    """Look up the current status and shipment tracking of ONE order that belongs to the customer
    you are talking to. Use it whenever the customer asks about an order and gives an order number.
    Returns JSON. If "found" is false, no such order exists for this customer: do not guess or
    invent any detail, and ask the customer to check the number.

    Args:
        order_no: The order number exactly as the customer wrote it, e.g. "BC-1042".
    """
```
`ToolRuntime` is imported from `langgraph.prebuilt`. A parameter named `runtime` typed `ToolRuntime` is injected by `ToolNode` and excluded from the tool schema (verified on langgraph-prebuilt 1.1.2: `list(tool.args) == ["order_no"]`).

### Tool response contract (a JSON string, `json.dumps(..., ensure_ascii=False)`)
Found:
```json
{"found": true, "order_no": "BC-1042", "status": "shipped", "payment_status": "paid",
 "ordered_at": "2026-11-12", "total_thb": "1230.00", "item_count": 3,
 "shipment": {"carrier": "Kerry Express", "tracking_no": "KEX26111042TH", "status": "in_transit",
              "shipped_at": "2026-11-13", "estimated_delivery_date": "2026-11-16", "delivered_at": null},
 "as_of": "2026-11-15T12:00:00+07:00"}
```
- Key order as shown. `shipment` is `null` when the order has none.
- `ordered_at`, `shipped_at`, `delivered_at`: the timestamp converted to `Asia/Bangkok`, date part only (`YYYY-MM-DD`), or `null`.
- `total_thb`: `f"{value:.2f}"`. `as_of`: `synced_at` in `Asia/Bangkok`, `isoformat(timespec="seconds")`.
- No name, phone, email, address, `customer_id`, `shop_id`, `order_id` or line items.

Not found (all four causes):
```json
{"found": false, "order_no": "<echo>"}
```
where `<echo>` = `normalize_order_no(raw)` if not `None`, else `raw.strip()[:32]`.

Temporary failure:
```json
{"error": "temporarily_unavailable"}
```

## Behaviour
1. The tool reads `ctx = runtime.context` and uses `ctx.tenant`. It never reads ids from arguments, state or messages. Extra keys in an LLM tool call (`shop_id`, `customer_id`, ...) are dropped by the schema and have no effect.
2. If `normalize_order_no(order_no)` is `None` → return the not-found response without querying.
3. Otherwise acquire `async with pool.connection() as conn` and call `repositories.get_order_status(conn, ctx.tenant, normalized)`.
4. `repositories.get_order_status` returns `None` immediately (no query) when `tenant.customer_id is None`. Otherwise it runs the single statement above; no row → `None`. There is no second query that could distinguish "exists but not yours" from "does not exist" — do not add one, not even for logging.
5. `None` → not-found response. The response must be identical for: unknown number, another customer's order in the same shop, a number that exists only in another shop, unverified user, malformed number.
6. `psycopg.Error` raised inside the tool body (this includes `psycopg_pool.PoolTimeout` and `PoolClosed`, which subclass `psycopg.OperationalError`) → `logger.exception("get_order_status failed")` and return the temporary-failure response. Catch only `psycopg.Error`, nothing broader. Reason: a `ToolMessage` must always follow the tool call, or the next model call on this thread is rejected by real providers.
7. Logging: one `logger.info("order_lookup shop_id=%s found=%s", shop_id, bool)` per call. Never log `order_no`, `customer_id` or row contents.
8. Every repository function's first statement filters on `shop_id` from the `TenantContext`/argument. No function in `repositories.py` accepts a bare `customer_id` without a `shop_id`.

## Tests

`tests/test_order_no.py`
| Input | Expected |
|---|---|
| `"BC-1042"` | `"BC-1042"` |
| `" bc-1042 "` | `"BC-1042"` |
| `"#BC-1042"` | `"BC-1042"` |
| `"BC1042"` | `"BC1042"` |
| `""`, `"  "`, `"ab"`, `"BC 1042"`, `"BC-1042'; DROP TABLE orders;--"`, `"ออเดอร์"`, `"A" * 21` | `None` |

`tests/integration/conftest.py` — fixture `two_shops` (async, uses `pool`):
- `shop_a = f"t-a-{uuid4().hex[:8]}"`, `shop_b = f"t-b-{uuid4().hex[:8]}"`.
- Inserts: customers `C-1` in both shops and `C-2` in shop A; one product `SKU-1` (price 100) per shop;
  orders — A/`C-1`/`BC-1042` (status `shipped`, total 1230.00, `ordered_at` 2026-11-12 10:15+07, `synced_at` 2026-11-15 12:00+07, one item qty 3) with a shipment (`Kerry Express`, `TRACK-A-1042`, `in_transit`, shipped 2026-11-13 14:00+07, est 2026-11-16);
  A/`C-2`/`BC-1050` (status `delivered`, total 1830.00) with shipment `TRACK-A-1050`;
  A/`C-1`/`BC-1043` (status `pending_payment`, no shipment);
  B/`C-1`/`BC-1042` (status `delivered`, total 3200.00) with shipment `TRACK-B-1042`.
- Yields a small object with `.shop_a`, `.shop_b`. Teardown deletes those two shops' rows (shipments, order_items, orders, products, customers).

`tests/integration/test_order_tool.py` — invoke the tool the way production does: a one-node graph `StateGraph(MessagesState, context_schema=SupportContext)` with `ToolNode(build_order_tools(pool))`, input `AIMessage(content="", tool_calls=[{"name": "get_order_status", "args": args, "id": "c1", "type": "tool_call"}])`, `context=SupportContext(shop, "web", "u1", customer, now)`; the result is `out["messages"][-1].content`. Put this in a helper `call_tool(pool, ctx, args) -> str`.

| # | Context (shop, customer) | args | Expected |
|---|---|---|---|
| 1 | A, `C-1` | `{"order_no": "BC-1042"}` | parsed JSON equals the found example shape: `found` true, `status` `"shipped"`, `total_thb` `"1230.00"`, `item_count` 3, `ordered_at` `"2026-11-12"`, `shipment.tracking_no` `"TRACK-A-1042"`, `shipment.delivered_at` null, `as_of` `"2026-11-15T12:00:00+07:00"` |
| 2 | A, `C-1` | `{"order_no": "bc-1043"}` | `found` true, `status` `"pending_payment"`, `shipment` is null |
| 3 | A, `C-1` | `{"order_no": "BC-1050"}` (belongs to C-2) | exactly `{"found": false, "order_no": "BC-1050"}` |
| 4 | A, `C-1` | `{"order_no": "BC-7777"}` (nonexistent) | exactly `{"found": false, "order_no": "BC-7777"}` |
| 5 | Identity check | responses of #3 and #4 with the order number replaced by a constant | the two raw strings are equal |
| 6 | B, `C-1` | `{"order_no": "BC-1042"}` | found, `total_thb` `"3200.00"`, tracking `"TRACK-B-1042"`; string does not contain `"TRACK-A-1042"` |
| 7 | B, `C-1` | `{"order_no": "BC-1050"}` (exists only in A) | exactly `{"found": false, "order_no": "BC-1050"}` |
| 8 | A, `None` (unverified) | `{"order_no": "BC-1042"}` | exactly `{"found": false, "order_no": "BC-1042"}` |
| 9 | A, `C-2` | `{"order_no": "BC-1042", "shop_id": <shop_b>, "customer_id": "C-1"}` | not found; contains neither tracking number (LLM-supplied ids ignored) |
| 10 | A, `C-1` | `{"order_no": "x'; DROP TABLE orders;--"}` | `found` false; afterwards `SELECT count(*) FROM orders WHERE shop_id = shop_a` still 3 |
| 11 | Schema | `tools[0].tool_call_schema.model_json_schema()["properties"]` | keys are exactly `["order_no"]`; the JSON schema text contains none of `shop_id`, `customer_id`, `runtime` |
| 12 | A, `C-1`; pool whose connections fail (pass a tool built on a **closed** pool, or monkeypatch `repositories.get_order_status` to raise `psycopg.OperationalError`) | `{"order_no": "BC-1042"}` | exactly `{"error": "temporarily_unavailable"}` |
| 13 | Repository direct: `get_order_status(conn, TenantContext(shop_a, None), "BC-1042")` | | `None` |
| 14 | `customer_exists` for (A, `C-2`) / (B, `C-2`) / (A, `None`); `shop_has_customers(shop_a)` / `("t-none-x")` | | `True` / `False` / `False`; `True` / `False` |
| 15 | No PII: response of #1 | | contains none of `full_name`, `phone`, `C-1`, shop id |

## Acceptance criteria
```powershell
.\.venv\Scripts\ruff.exe check src tests db
$env:LANGGRAPH_STRICT_MSGPACK='true'; .\.venv\Scripts\python.exe -m pytest -q tests/test_order_no.py tests/integration/test_order_tool.py   # all pass, none skipped (DB up, migrated)
$env:LANGGRAPH_STRICT_MSGPACK='true'; .\.venv\Scripts\python.exe -m pytest -q                                                                # whole suite green
```
`rg -n "customer_id|shop_id" src/supportkit/core/tools/orders.py` shows them only as reads of `runtime.context` / log fields — never as a tool parameter.

## Out of scope
- Other tools (`list_my_orders`, tracking, products, policy), identity verification, failed-lookup limits, PII masking helpers (Phase 2).
- Graph, API, seed. Do not import from `seed/`.
- Do not add a "this order belongs to someone else" path, hint, log line or metric.
