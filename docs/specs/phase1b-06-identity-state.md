# Phase 1b · Spec 06 — Identity in graph state, `prepare` revalidation, order authorization by link + scope

**Suggested implementer:** `implementer` (tenancy invariant change)
**Depends on:** 02, 04 · **Blocks:** 07, 08, 09 · **Parallel with:** — (touches shared core files)

## Goal
Move customer identity out of `SupportContext`. After this spec the server context carries only
`shop_id`, `channel`, `channel_user_id`, `now`; who the customer is lives in `customer_identities`
(the truth) and in two graph-state fields (a per-conversation cache that `prepare` re-derives every turn).
`get_order_status` authorizes with one SQL predicate over the identity link and the conversation's
verified order scopes. `verify_identity` does not exist yet (spec 07): in this spec the only writer of
identity links is the demo header path and the eval runner's pre-link, so all existing behaviour and all
10 eval cases stay green.

**The invariant this spec implements** (full text in `phase1b-plan-amendments.md` issue 4):
1. `shop_id`, `channel`, `channel_user_id` come only from `runtime.context`.
2. A customer identity exists only as a `customer_identities` row written by server code.
3. `verified_customer_id` / `verified_order_scopes` are written only by `prepare` (this spec) and `verify_identity` (spec 07).
4. An order is readable iff a link row joins the context's channel user to the order's customer in the same shop **and** (`grant_scope = 'account'` **or** the order number is in `verified_order_scopes`). Every other case returns the identical not-found response.

## Files
| Path | Action | Purpose |
|---|---|---|
| `src/supportkit/core/tenancy/context.py` | modify | add `ChannelUser`; move `CHANNEL_USER_ID_RE` here |
| `src/supportkit/core/graph/state.py` | modify | `SupportContext` without `customer_id`; identity fields + reducers |
| `src/supportkit/core/tenancy/repositories.py` | modify | `VerifiedIdentity`, `load_verified_identity`, `link_identity`; new `get_order_status` signature and SQL |
| `src/supportkit/core/tools/orders.py` | modify | tool reads `runtime.context.user` and `runtime.state` |
| `src/supportkit/core/graph/nodes/prepare.py` | modify | `make_prepare_node(load_identity)` |
| `src/supportkit/core/graph/builder.py` | modify | `load_identity` parameter |
| `src/supportkit/bootstrap.py` | modify | pass a pool-backed identity loader |
| `src/supportkit/api/demo_identity.py` | modify | interim: header customer → account-level link (final form in spec 08) |
| `evals/runner.py` | modify | interim: pre-link when the case names a customer; delete the link afterwards |
| `tests/test_context.py`, `tests/test_graph.py`, `tests/integration/test_graph_postgres.py`, `tests/integration/test_order_tool.py`, `tests/integration/conftest.py` | modify | new signatures and cases (below) |
| `tests/integration/test_identity_state.py` | create | revalidation through the real graph |

## Interfaces

### `core/tenancy/context.py`
```python
CHANNEL_USER_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")   # moved from state.py

@dataclass(frozen=True, slots=True)
class ChannelUser:
    """Who is talking, as established by the channel. Built server-side only."""
    shop_id: str
    channel: str            # "line" | "web"
    channel_user_id: str
    # __post_init__: SHOP_ID_RE, channel in ("line", "web"), CHANNEL_USER_ID_RE -> ValueError otherwise
```
`TenantContext` is unchanged (still used by `customer_exists`).

### `core/graph/state.py`
```python
from supportkit.core.tenancy.context import CHANNEL_USER_ID_RE, ChannelUser   # re-exported name stays importable

@dataclass(frozen=True)
class SupportContext:
    """Server-supplied only, never checkpointed. Carries no customer identity."""
    shop_id: str
    channel: Literal["line", "web"]
    channel_user_id: str
    now: str

    def __post_init__(self) -> None:
        ChannelUser(self.shop_id, self.channel, self.channel_user_id)   # validates all three

    @property
    def user(self) -> ChannelUser: ...

def replace_value(current: str | None, update: str | None) -> str | None:
    """Reducer: last write wins (lets parallel tool calls write the key in one step)."""
    return update

def add_order_scopes(current: list[str] | None, update: list[str]) -> list[str]:
    """Reducer: append the order numbers not already present, keeping order. Never removes."""

class SupportState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    summary: str
    # --- identity cache: written only by prepare and verify_identity ---
    verified_customer_id: Annotated[str | None, replace_value]
    verified_order_scopes: Annotated[list[str], add_order_scopes]
    # --- per-turn fields (reset in prepare) --- (unchanged)
    ...
```
The `customer_id` field and the `tenant` property are deleted. `thread_id_for` and `bangkok_now` are unchanged.

### `core/tenancy/repositories.py`
```python
@dataclass(frozen=True, slots=True)
class VerifiedIdentity:
    customer_id: str | None           # the channel user's account-level customer, else None
    order_scopes: tuple[str, ...]     # the requested scopes that are still valid, in input order

async def load_verified_identity(
    conn: psycopg.AsyncConnection, user: ChannelUser, scopes: Sequence[str]
) -> VerifiedIdentity: ...

async def link_identity(
    conn: psycopg.AsyncConnection, user: ChannelUser, customer_id: str,
    grant_scope: Literal["order", "account"],
) -> None: ...

async def get_order_status(
    conn: psycopg.AsyncConnection, user: ChannelUser, order_no: str, scopes: Sequence[str]
) -> OrderStatusRecord | None: ...
```
SQL, verbatim.

`load_verified_identity`, statement 1:
```sql
SELECT customer_id FROM customer_identities
WHERE shop_id = %(shop_id)s AND channel = %(channel)s AND channel_user_id = %(uid)s
  AND grant_scope = 'account'
ORDER BY is_primary DESC, verified_at, customer_id
LIMIT 1
```
statement 2 (skipped when `scopes` is empty):
```sql
SELECT o.order_no FROM orders o
JOIN customer_identities ci
  ON ci.shop_id = o.shop_id AND ci.customer_id = o.customer_id
WHERE o.shop_id = %(shop_id)s AND ci.channel = %(channel)s AND ci.channel_user_id = %(uid)s
  AND o.order_no = ANY(%(scopes)s::text[])
```
`order_scopes` = the input `scopes` (de-duplicated, input order) filtered to the returned set.

`link_identity`:
```sql
INSERT INTO customer_identities (shop_id, channel, channel_user_id, customer_id, is_primary, grant_scope)
VALUES (%(shop_id)s, %(channel)s, %(uid)s, %(customer_id)s,
        NOT EXISTS (SELECT 1 FROM customer_identities
                    WHERE shop_id = %(shop_id)s AND channel = %(channel)s
                      AND channel_user_id = %(uid)s AND is_primary),
        %(grant_scope)s)
ON CONFLICT (shop_id, channel, channel_user_id, customer_id) DO UPDATE
SET verified_at = now(),
    grant_scope = CASE WHEN customer_identities.grant_scope = 'account'
                         OR EXCLUDED.grant_scope = 'account' THEN 'account' ELSE 'order' END
```
(A grant is never downgraded; `is_primary` of an existing row is never changed.)

`get_order_status`: the existing `_ORDER_STATUS_SQL` with its `WHERE` clause replaced by
```sql
WHERE o.shop_id = %(shop_id)s AND o.order_no = %(order_no)s
  AND EXISTS (
      SELECT 1 FROM customer_identities ci
      WHERE ci.shop_id = o.shop_id AND ci.customer_id = o.customer_id
        AND ci.channel = %(channel)s AND ci.channel_user_id = %(uid)s
        AND (ci.grant_scope = 'account' OR o.order_no = ANY(%(scopes)s::text[]))
  )
```
The early `if tenant.customer_id is None: return None` is removed (there is no such argument any more);
the statement returns no row for an unlinked user by itself.

### `core/graph/nodes/prepare.py`, `builder.py`, `bootstrap.py`
```python
# prepare.py
IdentityLoader = Callable[[ChannelUser, Sequence[str]], Awaitable[VerifiedIdentity]]

def make_prepare_node(
    load_identity: IdentityLoader | None,
) -> Callable[[SupportState, Runtime[SupportContext]], Awaitable[dict]]: ...

# builder.py
def build_support_graph(
    model: BaseChatModel, tools: Sequence[BaseTool], checkpointer: BaseCheckpointSaver | None,
    *, model_name: str, load_identity: IdentityLoader | None = None,
) -> CompiledStateGraph: ...
```
`bootstrap.open_runtime` passes
```python
async def load_identity(user: ChannelUser, scopes: Sequence[str]) -> VerifiedIdentity:
    async with pool.connection() as conn:
        return await repositories.load_verified_identity(conn, user, scopes)
```

## Behaviour
**State and prepare**
1. `prepare` is async and returns everything it returns today, plus
   `"verified_customer_id": identity.customer_id` and
   `"verified_order_scopes": Overwrite(list(identity.order_scopes))` (`from langgraph.types import Overwrite`; verified on langgraph 1.2.22 with the Postgres checkpointer and strict msgpack — `Overwrite` bypasses the reducer, which is how scopes shrink).
2. `identity = await load_identity(runtime.context.user, state.get("verified_order_scopes") or [])`.
   If `load_identity is None` (unit tests without a database) → `VerifiedIdentity(None, ())`: no loader means no identity, never "trust the state".
3. `prepare` does not catch database errors. A failed revalidation fails the turn (the checkpointer shares the same database, so the turn could not complete anyway); it must never fall back to the stored values.
4. `run_turn` is unchanged: its graph input is `{"messages": [...]}` only. No API field, header or test helper may put identity keys into graph input in `src/`.
5. `add_order_scopes(None, ["A"]) == ["A"]`; `add_order_scopes(["A"], ["A", "B"]) == ["A", "B"]`; inputs are not mutated.

**Order tool**
6. `get_order_status` (tool): `user = runtime.context.user`; `scopes = list(runtime.state.get("verified_order_scopes") or [])`; `normalized = normalize_order_no(order_no)`; invalid → not-found without a query; else `repositories.get_order_status(conn, user, normalized, scopes)`.
7. The tool does not read `verified_customer_id` at all: account-level access is decided by the link row in SQL, so a wrong value in state cannot widen access.
8. Response contract, error handling, logging and the docstring's argument section are unchanged from Phase 1 spec 04. The not-found response stays the byte-identical `{"found": false, "order_no": "<echo>"}` for: unknown number, another customer's order, another shop's order, unlinked user, linked-but-not-in-scope, malformed number. No second query, log line or metric may distinguish these.
9. Replace the first docstring sentence with: "Look up the current status and shipment tracking of ONE order that the customer you are talking to has verified." and the `found: false` sentence with: `If "found" is false, that order is not among this customer's verified orders: do not guess or invent any detail.`

**Interim identity sources (finalised in specs 08 and 09)**
10. `api/demo_identity.py`: validation and the 400/403 rules are unchanged. `channel_user_id` stays `demo-<customer|guest>-<session>`. When the customer header is present and the customer exists, call `repositories.link_identity(conn, ChannelUser(shop, "web", channel_user_id), customer, "account")` on the same connection, then return `SupportContext(shop, "web", channel_user_id, bangkok_now())`. Guests get no link.
11. `evals/runner.py`: build `SupportContext` without `customer_id`. If `case.customer_context.customer_id` is not `None`, after opening the runtime and before the first turn: `link_identity(conn, ctx.user, customer_id, "account")` on a `runtime.pool` connection. In the existing `finally`, before `adelete_thread`: `DELETE FROM customer_identities WHERE shop_id = %s AND channel = %s AND channel_user_id = %s`.
12. Update the module docstring of `demo_identity.py`: it no longer returns an identity, it creates a server-side link.

## Tests

`tests/test_context.py` — rewrite for the 4-field context: valid construction; `ctx.user == ChannelUser("shop-b", "web", "demo-guest-abc12345")`; invalid channel / `a:b` user id / bad shop raise `ValueError`; `SupportContext` has no attribute `customer_id` or `tenant`; `ChannelUser("shop-b", "sms", "u1")` raises; frozen checks; `thread_id_for`; `TenantContext` tests unchanged.

`tests/test_graph.py` — contexts become `SupportContext("t-graph", "web", uid, NOW)`; the stub tool records `(runtime.context.shop_id, order_no)`; expectations change accordingly (`seen == [("t-graph", "BC-1042")]`, and in `test_llm_cannot_override_tenant_args` `seen == [("t-graph", "BC-1")]`). Add:
| Test | Steps | Expected |
|---|---|---|
| `test_identity_cleared_without_loader` | invoke the graph with input `{"messages": [...], "verified_customer_id": "C-9", "verified_order_scopes": ["BC-1"]}` (direct `graph.ainvoke`, no loader) | final state has `verified_customer_id is None` and `verified_order_scopes == []` |
| `test_prepare_overwrites_from_loader` | loader stub returns `VerifiedIdentity("C-1", ("BC-2",))` and records its arguments; same poisoned input as above | loader called with `ChannelUser("t-graph","web",uid)` and `["BC-1"]`; final state `"C-1"` / `["BC-2"]` |
| `test_scopes_persist_to_next_turn_through_loader` | loader echoes its `scopes` argument; a stub tool returns `Command(update={"verified_order_scopes": ["BC-7"], "messages": [ToolMessage("{}", tool_call_id=runtime.tool_call_id)]})`; turn 1 calls it via `ScriptedChatModel`; turn 2 is plain text | after turn 1 scopes `["BC-7"]`; in turn 2 the loader receives `["BC-7"]` |
| `test_parallel_scope_writes_merge` | one `AIMessage` with two calls to that stub tool (`BC-7`, `BC-8`) | no error; scopes `["BC-7", "BC-8"]` |
| `test_reducers` | rule 5 cases; `replace_value("a", None) is None` | as stated |
| `test_run_turn_input_has_no_identity` | spy on `graph.ainvoke` | the input dict's keys are exactly `{"messages"}` |

`tests/integration/test_graph_postgres.py` — 4-field context; stub records `(shop_id, order_no)`.

`tests/integration/conftest.py` — `two_shops` phones: A/`C-1` `"0812345678"`, A/`C-2` `"+66 82 345 6789"`, B/`C-1` `"091-555-0201"` (spec 07 needs them). Add a fixture
```python
@pytest.fixture
def linked(pool):
    async def _link(shop: str, customer: str | None, grant: str = "account") -> SupportContext:
        """New channel user `u-<8 hex>` in `shop`; linked to `customer` with `grant` unless customer is None."""
    return _link
```
(links vanish with the customers in the `two_shops` teardown via `ON DELETE CASCADE`).

`tests/integration/test_order_tool.py` — `call_tool(pool, ctx, args, *, scopes=(), tools=None)` builds
`StateGraph(SupportState, context_schema=SupportContext)` with the `ToolNode` and invokes with
`{"messages": [msg], "verified_order_scopes": list(scopes)}`. Phase 1 cases 1–15 keep their expected
results, with "context (shop, customer)" now meaning `await linked(shop, customer)` (account grant) and
`None` meaning an unlinked user. Case 13 becomes `get_order_status(conn, ChannelUser(shop_a, "web", "u-nobody"), "BC-1042", [])` → `None`. Add:

| # | Setup | Call | Expected |
|---|---|---|---|
| 16 | A user linked to `C-1` with grant `order`; scopes `["BC-1042"]` | `BC-1042` | found, `TRACK-A-1042` |
| 17 | same | `BC-1043` (also `C-1`'s, not in scopes) | exactly not-found |
| 18 | A user linked to `C-1` grant `order`; scopes `[]` | `BC-1042` | not-found |
| 19 | A user linked to `C-1` grant `order`; scopes `["BC-1050"]` (`C-2`'s order) | `BC-1050` | not-found: a scope without a link to that customer authorizes nothing |
| 20 | unlinked A user; scopes `["BC-1042"]` | `BC-1042` | not-found: state alone authorizes nothing |
| 21 | B user linked to B/`C-1` grant `order`; scopes `["BC-1043"]` (exists only in A) | `BC-1043` | not-found |
| 22 | a user id linked in shop A to `C-1` (account); context = **shop B** with the same `channel_user_id` | `BC-1042` | not-found (B's order is not exposed through A's link; no `TRACK-`) |
| 23 | A user linked to `C-1` (order) and to `C-2` (order); scopes `["BC-1042", "BC-1050"]` | both | both found |
| 24 | A user linked to `C-1` grant `account`, channel `"web"`; context with channel `"line"` and the same user id | `BC-1042` | not-found |
| 25 | raw strings of 17, 18, 19, 20 with the order number replaced by a constant | | all equal to the Phase 1 not-found string |
| 26 | `link_identity`: first link for a user | row | `is_primary` true, grant as given |
| 27 | second link, other customer | rows | second has `is_primary` false; exactly one primary |
| 28 | re-link same customer `order` → `account` → `order` | row | grant ends `account`; one row; `verified_at` not earlier than before |
| 29 | `link_identity` for a customer id that exists only in the other shop | | `psycopg.errors.ForeignKeyViolation` |
| 30 | `load_verified_identity`: account link to `C-1` | `scopes=[]` | `VerifiedIdentity("C-1", ())` |
| 31 | order link to `C-1` | `scopes=["BC-1042", "BC-1050", "BC-7777", "BC-1042"]` | `VerifiedIdentity(None, ("BC-1042",))` |
| 32 | links: `C-2` order (primary), `C-1` account (not primary) | | `customer_id == "C-1"` |
| 33 | unlinked user | `scopes=["BC-1042"]` | `VerifiedIdentity(None, ())` |

`tests/integration/test_identity_state.py` — real pool, `build_support_graph(..., load_identity=<pool-backed loader>)`, real `build_order_tools(pool)`, `InMemorySaver`, `ScriptedChatModel`:
| # | Steps | Expected |
|---|---|---|
| 1 | account-linked user asks for `BC-1042` over two turns; between the turns `DELETE FROM customer_identities` for that user | turn 1 tool result found; turn 2 tool result not-found; state `verified_customer_id` is `"C-1"` after turn 1 and `None` after turn 2 |
| 2 | user linked to `C-1` with grant `order`; call `graph.ainvoke` directly with the poisoned input `{"messages": [HumanMessage(...)], "verified_order_scopes": ["BC-1042", "BC-1050"]}`; the script calls `get_order_status` for `BC-1042` and then `BC-1050` | final state scopes are `["BC-1042"]`; `BC-1042` found, `BC-1050` not-found |
| 3 | unlinked user; direct `graph.ainvoke` with poisoned input `verified_customer_id="C-1"`, `verified_order_scopes=["BC-1042"]` | lookup not-found; final state `None` / `[]` |

`tests/integration/test_api_chat.py`, `test_eval_runner.py`, `test_serve_smoke.py`, UI tests: no change needed; they must pass as they are (the header customer is now a link).

## Acceptance
```powershell
.\.venv\Scripts\ruff.exe check src tests db seed evals ui
$env:LANGGRAPH_STRICT_MSGPACK='true'; .\.venv\Scripts\python.exe -m pytest -q        # whole suite green, none skipped
.\.venv\Scripts\supportkit.exe eval --require-all                                   # 10/10
```
- `rg -n "customer_id" src/supportkit/core/graph src/supportkit/core/tools` shows only the `verified_customer_id` state field and its use in `prepare`; never a tool parameter, never `runtime.context.customer_id`.
- `rg -n "\.tenant\b" src` returns nothing.
- `rg -n "verified_order_scopes|verified_customer_id" src` shows: declarations in `state.py`, the write in `core/graph/nodes/prepare.py`, and one read of `verified_order_scopes` in `core/tools/orders.py`. Nothing else.
- After an eval run: `select count(*) from customer_identities where channel_user_id like 'eval-%'` is 0.

## Out of scope
- `verify_identity`, rate limiting, `IdentityPolicy`, prompt changes (spec 07).
- The demo pre-verify flag, `/health`, UI (spec 08). New eval cases (spec 09).
- Long-term memory keys, `list_my_orders`.
- Do not add a code path that lets a caller pass a customer id into `run_turn`, the graph input or a tool.
