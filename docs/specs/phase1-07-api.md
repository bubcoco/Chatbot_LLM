# Phase 1 · Spec 07 — Runtime bootstrap + FastAPI `/chat` (demo-only identity)

**Suggested implementer:** `implementer` (identity boundary, async lifecycle)
**Depends on:** 04, 06 · **Blocks:** 09 · **Parallel with:** 08 (the HTTP contract below is frozen)

## Goal
Wire pool → checkpointer → tools → model → graph in one place (`open_runtime`), and expose it over FastAPI: `GET /health`, and — **only when `SUPPORTKIT_DEMO_MODE=true`** — `POST /chat` and `GET /chat/history` for the Streamlit demo page.

**Identity decision (Phase 1 only).** Real identity verification is Phase 2 and real channels are Phase 3. Until then the demo endpoints trust three `X-Demo-*` headers. To keep this from becoming a production pattern: (a) the chat router is not mounted at all unless demo mode is on; (b) all header handling lives in one dependency, `api/demo_identity.py`, which returns a `SupportContext` — handlers and everything below them only ever see a `SupportContext`, exactly as they will when a signature-verified channel adapter builds it; (c) the request body never carries identity; (d) `supportkit serve` binds `127.0.0.1` by default and logs a warning when demo mode is on.

## Files
| Path | Action | Purpose |
|---|---|---|
| `src/supportkit/bootstrap.py` | create | `SupportRuntime`, `open_runtime` |
| `src/supportkit/api/__init__.py` | create | empty |
| `src/supportkit/api/app.py` | create | `create_app`, lifespan, `/health` |
| `src/supportkit/api/demo_identity.py` | create | **DEMO ONLY** header → `SupportContext` dependency |
| `src/supportkit/api/chat.py` | create | demo chat router |
| `src/supportkit/api/server.py` | create | `serve()` (uvicorn with the right event loop) |
| `tests/integration/test_api_chat.py` | create | API tests |
| `tests/test_api_gating.py` | create | demo-mode gating test (no DB) |

## Interfaces

### `bootstrap.py`
```python
@dataclass(frozen=True)
class SupportRuntime:
    pool: AsyncConnectionPool
    checkpointer: AsyncPostgresSaver
    graph: CompiledStateGraph
    model_spec: str

@asynccontextmanager
async def open_runtime(
    database_url: str, model_spec: str, *, model: BaseChatModel | None = None
) -> AsyncIterator[SupportRuntime]:
    """async with create_pool(database_url) as pool:
         checkpointer = AsyncPostgresSaver(pool)           # no setup(): `supportkit migrate` owns it
         tools = build_order_tools(pool)
         chat_model = model or get_chat_model(model_spec)
         graph = build_support_graph(chat_model, tools, checkpointer, model_name=model_spec)
         yield SupportRuntime(pool, checkpointer, graph, model_spec)"""
```

### `api/app.py`
```python
def create_app(settings: Settings | None = None, *, model: BaseChatModel | None = None) -> FastAPI: ...
```
- `settings = settings or get_settings()`; stored on `app.state.settings`.
- Lifespan: `async with open_runtime(settings.database_url, settings.supportkit_model, model=model) as rt:` → `app.state.runtime = rt`; `app.state.thread_locks = {}`; `yield`.
- `GET /health` → `200 {"status": "ok", "model": "<settings.supportkit_model>", "demo_mode": <bool>}`. No DB call.
- `if settings.supportkit_demo_mode: app.include_router(chat.router)` and `logger.warning("DEMO MODE: /chat trusts X-Demo-* identity headers. Do not expose this server.")`. Otherwise the router is not included (→ 404).
- `FastAPI(title="supportkit", docs_url=None, redoc_url=None, openapi_url=None)` when demo mode is off; defaults when on.

### `api/demo_identity.py`
Module docstring must start with: `DEMO ONLY — trusts caller-supplied identity. Replaced by verified channel identity in Phase 2/3. Never import this outside api/chat.py.`
```python
SESSION_RE = re.compile(r"^[A-Za-z0-9]{8,32}$")

async def demo_context(
    request: Request,
    x_demo_shop_id: Annotated[str | None, Header()] = None,
    x_demo_customer_id: Annotated[str | None, Header()] = None,
    x_demo_session: Annotated[str | None, Header()] = None,
) -> SupportContext: ...
```

### `api/chat.py`
```python
router = APIRouter(tags=["demo"])

class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=2000)

class ChatResponse(BaseModel):
    reply: str
    thread_id: str
    turn_id: str

class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: str

class HistoryResponse(BaseModel):
    thread_id: str
    messages: list[HistoryMessage]

@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, request: Request, ctx: SupportContext = Depends(demo_context)): ...

@router.get("/chat/history", response_model=HistoryResponse)
async def history(request: Request, ctx: SupportContext = Depends(demo_context)): ...
```

### `api/server.py`
```python
def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    uvicorn.run("supportkit.api.app:create_app", factory=True, host=host, port=port, loop=UVICORN_LOOP)
```
(`UVICORN_LOOP` from `supportkit.aio`; uvicorn 0.54 accepts a custom `"module:attr"` loop factory — verified: on Windows the server runs on `_WindowsSelectorEventLoop`.)

### HTTP contract (frozen — spec 08 codes against it)
| Request | Success | Errors |
|---|---|---|
| `GET /health` | `200 {"status","model","demo_mode"}` | — |
| `POST /chat` headers `X-Demo-Shop-Id` (required), `X-Demo-Session` (required), `X-Demo-Customer-Id` (optional); JSON `{"message": "..."}` | `200 {"reply","thread_id","turn_id"}` | `400` bad/missing headers · `403` unknown identity · `422` bad body · `502` agent failure · `503` database unavailable · `404` demo mode off |
| `GET /chat/history` same headers | `200 {"thread_id","messages":[{"role","text"}]}` | `400`, `403`, `503`, `404` as above |

Error bodies are `{"detail": "<code>"}` with codes `invalid_demo_identity`, `unknown_demo_identity`, `agent_error`, `database_unavailable` (422 keeps FastAPI's default body).

## Behaviour
**demo_context**
1. Missing `X-Demo-Shop-Id` or `X-Demo-Session`; shop id not matching `SHOP_ID_RE`; session not matching `SESSION_RE`; customer id present but not matching `CUSTOMER_ID_RE` → `HTTPException(400, "invalid_demo_identity")`. An empty-string customer header counts as absent.
2. With a connection from `request.app.state.runtime.pool`: if a customer id is given and `customer_exists(conn, TenantContext(shop, customer))` is false → `403 unknown_demo_identity`. If no customer id is given and `shop_has_customers(conn, shop)` is false → `403 unknown_demo_identity`. Same code for both so the endpoint is not a customer/shop oracle.
3. Returns `SupportContext(shop_id=shop, channel="web", channel_user_id=f"demo-{customer or 'guest'}-{session}", customer_id=customer or None, now=bangkok_now())`. Embedding the customer id in `channel_user_id` guarantees that switching the demo persona starts a different thread, so one persona's tool results can never be in another persona's history.
4. `psycopg.OperationalError` here → `503 database_unavailable`.

**POST /chat**
5. `text = body.message.strip()`; empty after strip → `422`.
6. Serialise turns per thread: `lock = app.state.thread_locks.setdefault(thread_id_for(ctx), asyncio.Lock())`; `async with lock:` around `run_turn`. (In-process only; replaced by the Phase 3 worker's per-thread lock.)
7. `result = await run_turn(runtime.graph, ctx, text)` → `ChatResponse(reply=result.reply, thread_id=result.thread_id, turn_id=result.turn_id)`.
8. `result.reply is None` → `502 agent_error`.
9. `psycopg.OperationalError` → `503 database_unavailable`. Any other exception from `run_turn` → `logger.exception("chat turn failed")` (exception only — never the message text, reply or headers) → `502 agent_error`.
10. The handler never reads identity from the body, query string or cookies, and never passes anything but `ctx` as graph context.

**GET /chat/history**
11. Returns `get_history(runtime.graph, ctx)` under `thread_id_for(ctx)`.

**General**
12. No CORS middleware. No message content in logs at any level.
13. `create_app()` with demo mode off exposes only `/health`.

## Tests
`tests/test_api_gating.py` (no DB: build the app, do **not** run lifespan; use `httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")`)
| # | Setup | Expected |
|---|---|---|
| 1 | `create_app(Settings(_env_file=None, supportkit_demo_mode=False))`; `POST /chat` with valid-looking headers and body | `404` |
| 2 | same app; `GET /chat/history` | `404` |
| 3 | same app; `GET /health` | `200`, `demo_mode` false, `model` `"fake:rules"` |
| 4 | same app; `GET /openapi.json` | `404` |
| 5 | demo-mode app: `[r.path for r in app.routes]` | contains `/chat` and `/chat/history` |

`tests/integration/test_api_chat.py` — fixture `client` (async): `app = create_app(Settings(_env_file=None, database_url=database_url, supportkit_demo_mode=True, supportkit_model="fake:rules"), model=RuleBasedFakeModel())`; `async with app.router.lifespan_context(app):` then yield an `httpx.AsyncClient` on `ASGITransport`. Uses the `two_shops` fixture from spec 04 (`shop_a`: `C-1` owns `BC-1042` with `TRACK-A-1042`, `C-2` owns `BC-1050` with `TRACK-A-1050`; `shop_b`: `C-1` owns `BC-1042` with `TRACK-B-1042`). Each test uses a fresh session `uuid4().hex[:16]` and, at the end, deletes its thread with `app.state.runtime.checkpointer.adelete_thread(thread_id)`. `H(shop, customer, session)` builds the headers.

| # | Request | Expected |
|---|---|---|
| 1 | `POST /chat` `H(shop_a, "C-1", s)` `{"message": "ออเดอร์ BC-1042 ถึงไหนแล้วคะ"}` | `200`; `reply` contains `TRACK-A-1042`; `thread_id == f"{shop_a}:web:demo-C-1-{s}"`; `turn_id` 32 hex |
| 2 | After #1, same headers, `{"message": "แล้วเลขพัสดุล่ะคะ"}` | `200`; `reply` contains `TRACK-A-1042` |
| 3 | Restart: run #1 in one `lifespan_context`, exit it, create a **new app** + lifespan, send the follow-up with the same headers | `reply` contains `TRACK-A-1042`; `GET /chat/history` returns 4 messages with roles `user, assistant, user, assistant` |
| 4 | `H(shop_a, "C-1", s)` asks `BC-1050` (C-2's) | `200`; `reply` contains neither `TRACK-A-1050` nor `1830`; equals the fake's Thai not-found template for `BC-1050` |
| 5 | `H(shop_b, "C-1", s)` asks `BC-1042` | `reply` contains `TRACK-B-1042`, not `TRACK-A-1042` |
| 6 | `H(shop_b, "C-1", s)` asks `BC-1050` (exists only in shop A) | `reply` contains no `TRACK-` |
| 7 | `H(shop_a, None, s)` (guest) asks `BC-1042` | `200`; `reply` contains no `TRACK-`; `thread_id` ends with `demo-guest-{s}` |
| 8 | Same session `s`: C-1 asks `BC-1042`, then C-2 with the **same** `s` sends `"แล้วเลขพัสดุล่ะคะ"` | C-2's `reply` does not contain `TRACK-A-1042`; the two `thread_id`s differ |
| 9 | `H(shop_a, "C-1", s)` body `{"message": "ออเดอร์ BC-1042", "customer_id": "C-2", "shop_id": shop_b}` | `422` (extra fields forbidden) |
| 10 | Headers missing `X-Demo-Session`; session `"short"`; shop `"Bad Shop"`; customer `"a b"` | each `400 invalid_demo_identity` |
| 11 | `H(shop_a, "C-404", s)`; `H("t-none-zzz", None, s)`; `H(shop_b, "C-2", s)` (C-2 exists only in shop A) | each `403 unknown_demo_identity` |
| 12 | `{"message": ""}`, `{"message": "   "}`, `{"message": "x" * 2001}`, `{}` | each `422` |
| 13 | `GET /chat/history` for a never-used session | `200`, `messages == []` |
| 14 | App built with `model=ScriptedChatModel(responses=[])` (raises on first call); `POST /chat` | `502 {"detail": "agent_error"}`; response body does not contain the message text |
| 15 | Two concurrent `POST /chat` (`asyncio.gather`) on the same thread | both `200`; afterwards history has 4 entries with alternating roles |

## Acceptance criteria
```powershell
.\.venv\Scripts\ruff.exe check src tests db
$env:LANGGRAPH_STRICT_MSGPACK='true'; .\.venv\Scripts\python.exe -m pytest -q tests/test_api_gating.py tests/integration/test_api_chat.py   # all pass, none skipped
$env:LANGGRAPH_STRICT_MSGPACK='true'; .\.venv\Scripts\python.exe -m pytest -q                                                             # whole suite green
```
Manual (needs spec 03's seed loaded):
```powershell
$env:SUPPORTKIT_DEMO_MODE='true'; $env:SUPPORTKIT_MODEL='fake:rules'; .\.venv\Scripts\supportkit.exe serve
# second terminal
curl.exe -s http://127.0.0.1:8000/health
curl.exe -s -X POST http://127.0.0.1:8000/chat -H "Content-Type: application/json" -H "X-Demo-Shop-Id: baan-bai-cha" -H "X-Demo-Customer-Id: C-0001" -H "X-Demo-Session: manual0001" --data-binary "{\"message\": \"Where is order BC-1042?\"}"
# → reply mentions Kerry Express and KEX26111042TH
```
With `SUPPORTKIT_DEMO_MODE` unset, the same `POST /chat` returns 404.

## Out of scope
- LINE webhooks, `inbox_events`, worker loop, debounce, conversation gate, staff API (Phase 3).
- Identity verification, `customer_identities`, failed-lookup limits, rate limiting, auth tokens (Phase 2 / 6).
- Streaming responses, CORS, Docker service for the API.
- `cli.py` (the `serve` command already exists from spec 01).
- Do not reuse `demo_identity` for any non-demo route, and do not add identity fields to `ChatRequest`.
