# Phase 1b · Spec 04 — Per-conversation lock (replaces the API's in-process locks)

**Suggested implementer:** `implementer` (concurrency)
**Depends on:** 02 (`conversations`) · **Blocks:** 06 · **Parallel with:** 03, 05

## Goal
A database-backed mutual-exclusion helper for one conversation, usable by every process that touches a
thread (API now; worker, staff API and memory job later), and its use in `POST /chat` instead of
`app.state.thread_locks`. Design and justification: `phase1b-plan-amendments.md` issue 6 — a
**session-level advisory lock on a dedicated pool**, not a row lock. The helper was verified with a spike
on psycopg 3.3.9 / Postgres 17: the lock survives the commit of the transaction that set `lock_timeout`,
a timed-out waiter gets `psycopg.errors.LockNotAvailable` and its connection stays usable, and a pool
`reset` callback releases a lock that was never unlocked.

## Files
| Path | Action | Purpose |
|---|---|---|
| `src/supportkit/core/tenancy/lock.py` | create | `conversation_lock`, `ConversationBusy` |
| `src/supportkit/db.py` | modify | `create_lock_pool` |
| `src/supportkit/bootstrap.py` | modify | `SupportRuntime.lock_pool`; opened and closed with the runtime |
| `src/supportkit/api/chat.py` | modify | use `conversation_lock`; 409 on busy |
| `src/supportkit/api/app.py` | modify | delete `app.state.thread_locks` |
| `tests/integration/test_lock.py` | create | lock tests |
| `tests/integration/test_api_chat.py` | modify | one new test; cleanup of `conversations` rows |
| `tests/integration/conftest.py` | modify | `two_shops` teardown also deletes `conversations` rows of its shops |

## Interfaces
```python
# src/supportkit/db.py
def create_lock_pool(database_url: str, *, max_size: int = 8) -> AsyncConnectionPool:
    """Unopened pool used ONLY for conversation locks. One connection is held per in-flight turn."""
```
Exactly: `AsyncConnectionPool(database_url, min_size=1, max_size=max_size, open=False, timeout=5.0,
kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row}, reset=_release_all_locks)`
with
```python
async def _release_all_locks(conn: psycopg.AsyncConnection) -> None:
    await conn.execute("SELECT pg_advisory_unlock_all()")
```

```python
# src/supportkit/core/tenancy/lock.py
LOCK_KEY_SQL = "hashtextextended(%s, 0)"

class ConversationBusy(Exception):
    """The conversation lock could not be acquired within the wait time."""

def lock_key_text(shop_id: str, thread_id: str) -> str:
    return f"conv:{shop_id}:{thread_id}"

@asynccontextmanager
async def conversation_lock(
    lock_pool: AsyncConnectionPool, shop_id: str, thread_id: str, *, wait_seconds: float = 30.0
) -> AsyncIterator[None]: ...
```

```python
# src/supportkit/bootstrap.py
@dataclass(frozen=True)
class SupportRuntime:
    pool: AsyncConnectionPool
    checkpointer: AsyncPostgresSaver
    graph: CompiledStateGraph
    model_spec: str
    lock_pool: AsyncConnectionPool
```
`open_runtime` becomes `async with create_pool(url) as pool, create_lock_pool(url) as lock_pool:`.

`api/chat.py`: module constant `LOCK_WAIT_SECONDS = 30.0`.

## Behaviour
`conversation_lock`:
1. Validate `shop_id` with `SHOP_ID_RE` and require `thread_id` to be a non-empty `str` of at most 256 characters; otherwise `ValueError` before any database work.
2. `async with lock_pool.connection() as conn:` — everything below uses this one connection. A `psycopg_pool.PoolTimeout` here propagates unchanged.
3. Acquire:
   ```python
   key = lock_key_text(shop_id, thread_id)
   try:
       async with conn.transaction():
           await conn.execute("SELECT set_config('lock_timeout', %s, true)", (f"{int(wait_seconds * 1000)}ms",))
           await conn.execute(f"SELECT pg_advisory_lock({LOCK_KEY_SQL})", (key,))
   except psycopg.errors.LockNotAvailable:
       raise ConversationBusy(thread_id) from None
   ```
4. From here on the lock is held, so wrap the rest in `try/finally`:
   a. Upsert the row: `INSERT INTO conversations (shop_id, thread_id) VALUES (%s, %s) ON CONFLICT (shop_id, thread_id) DO UPDATE SET updated_at = now()`.
   b. `yield`.
   c. `finally`: `await conn.execute(f"SELECT pg_advisory_unlock({LOCK_KEY_SQL})", (key,))`; if that raises `psycopg.Error`, `await conn.close()` (the pool discards a closed connection and the server releases the lock). Catch only `psycopg.Error`.
5. The caller's work inside the `with` block must use the main pool. The lock connection is not exposed.
6. The helper is not re-entrant: acquiring the same conversation twice in one task waits and then raises `ConversationBusy`. Do not add re-entrancy.
7. No logging of `thread_id` at INFO; one `logger.warning("conversation_busy shop_id=%s", shop_id)` when raising `ConversationBusy`.

`POST /chat`:
8. Replace the `asyncio.Lock` block with
   ```python
   rt = request.app.state.runtime
   try:
       async with conversation_lock(rt.lock_pool, ctx.shop_id, thread_id, wait_seconds=LOCK_WAIT_SECONDS):
           result = await run_turn(rt.graph, ctx, text)
   except ConversationBusy:
       raise HTTPException(409, "conversation_busy") from None
   except psycopg.OperationalError:
       raise HTTPException(503, "database_unavailable") from None
   except Exception:
       logger.exception("chat turn failed")
       raise HTTPException(502, "agent_error") from None
   ```
   (`PoolTimeout` is a `psycopg.OperationalError`, so an exhausted lock pool is a 503.)
9. `GET /chat/history` takes no lock.
10. `app.state.thread_locks` is removed from `create_app`; nothing else may hold per-thread state in process memory.
11. `run_turn` itself does not lock: unit tests keep running it without a database, and the Phase 3 worker must hold the lock around more than the graph call.

## Tests
`tests/integration/test_lock.py` (fixtures: `database_url`; each test opens its own
`create_lock_pool(database_url, max_size=2)`; shop ids `t-lock-<hex>`; delete the shop's `conversations`
rows in `finally`).

| # | Steps | Expected |
|---|---|---|
| 1 | acquire `(shop, "th-1")`, inside the block read `conversations` on a plain connection | the row exists with `mode = 'bot'` |
| 2 | acquire and release twice | still exactly one row; `updated_at` of the second read ≥ the first |
| 3 | two **separate** lock pools (stand-ins for two processes). Pool A holds `(shop, "th-1")`; pool B tries with `wait_seconds=0.3` | `ConversationBusy` after 0.25–2 s; afterwards A releases and B acquires with `wait_seconds=1` |
| 4 | A holds for 0.3 s (`asyncio.sleep`), B starts 0.05 s later with `wait_seconds=5`; both append `("enter"/"exit", name)` to a list | list is `A enter, A exit, B enter, B exit` |
| 5 | A holds `(shop, "th-1")`; B acquires `(shop, "th-2")` with `wait_seconds=0.3` | succeeds immediately |
| 6 | A holds `(shop_a, "same")`; B acquires `(shop_b, "same")` | succeeds (the key includes the shop) |
| 7 | body raises `RuntimeError` inside the block | the error propagates; a new acquire with `wait_seconds=0.3` succeeds |
| 8 | safety net: take a raw `lock_pool.connection()`, run `SELECT pg_advisory_lock(hashtextextended(%s, 0))` with `lock_key_text(shop, "th-1")` by hand, and leave the `with` block without unlocking | a following `conversation_lock(pool, shop, "th-1", wait_seconds=0.3)` succeeds (the pool's `reset` callback released it) |
| 9 | `conversation_lock(pool, "Bad Shop", "t")`, `(pool, shop, "")` | `ValueError`, and `SELECT count(*) FROM conversations WHERE shop_id = shop` is 0 |
| 10 | after a `ConversationBusy`, `SHOW lock_timeout` on a fresh lock-pool connection | `'0'` (the timeout did not leak into the session) |
| 11 | `max_size=1` pool: hold one conversation, try another conversation on the same pool with the pool's `timeout` patched to 0.3 (`create_lock_pool` result has `.timeout`; set it before opening) | `psycopg_pool.PoolTimeout` |

`tests/integration/test_api_chat.py`:
- `test_concurrent_turns_serialised` is unchanged and must still pass (now through the database lock).
- New `test_busy_conversation_409(env, two_shops, monkeypatch)`: `monkeypatch.setattr(chat, "LOCK_WAIT_SECONDS", 0.3)`; hold `conversation_lock(env.app.state.runtime.lock_pool, shop_a, thread_id)` for the thread `f"{shop_a}:web:demo-C-1-{s}"` in the test body and post to `/chat` meanwhile → `409`, body `{"detail": "conversation_busy"}`; after the block exits the same post returns `200`.
- New `test_no_in_process_locks(env)`: `not hasattr(env.app.state, "thread_locks")`.
- `Env` fixture teardown: for every thread it recorded, `DELETE FROM conversations WHERE thread_id = %s` (via `app.state.runtime.pool`); the same in the `finally` blocks of `test_restart_persists_history` and `test_agent_failure_502`.

## Acceptance
```powershell
.\.venv\Scripts\ruff.exe check src tests db seed evals ui
$env:LANGGRAPH_STRICT_MSGPACK='true'; .\.venv\Scripts\python.exe -m pytest -q tests/integration/test_lock.py tests/integration/test_api_chat.py   # pass, none skipped
$env:LANGGRAPH_STRICT_MSGPACK='true'; .\.venv\Scripts\python.exe -m pytest -q        # whole suite green
.\.venv\Scripts\supportkit.exe eval --require-all                                   # 10/10
```
`rg -n "thread_locks|asyncio.Lock" src` returns nothing.
`rg -n "FOR UPDATE" src` returns nothing.

## Out of scope
- `conversations.mode` gate, `current_turn_id` / `last_extracted_turn_id` updates (Phase 3 / 4).
- Locking inside `run_turn`, `evals/runner.py` (sequential, single process), `get_history`.
- Worker, inbox queue, `FOR UPDATE SKIP LOCKED` (Phase 3).
- Identity changes (spec 06). Do not touch `demo_identity.py`.
