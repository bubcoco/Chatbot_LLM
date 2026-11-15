# Phase 1 · Spec 01 — Foundation: deps, settings, context types, DB pool, CLI stubs

**Suggested implementer:** `implementer` (defines the tenancy/context types every later spec relies on)
**Depends on:** nothing · **Blocks:** every other Phase 1 spec

## Goal
Lay down the shared plumbing so the remaining Phase 1 specs can run in parallel without touching the same files: new dependencies, process settings, `TenantContext` / `SupportContext` / `SupportState`, one async Postgres pool factory, a Windows-safe event-loop helper, shared pytest fixtures, and thin CLI commands (`seed`, `serve`, `eval`) that lazily import modules written by later specs.

## Files
| Path | Action | Purpose |
|---|---|---|
| `pyproject.toml`, `uv.lock` | modify (via uv only) | new deps, pytest `pythonpath` |
| `src/supportkit/settings.py` | modify | `supportkit_model`, `supportkit_demo_mode` |
| `src/supportkit/db.py` | create | `create_pool()` |
| `src/supportkit/aio.py` | create | `run()`, `UVICORN_LOOP` |
| `src/supportkit/core/__init__.py`, `core/tenancy/__init__.py`, `core/graph/__init__.py` | create | empty packages |
| `src/supportkit/core/tenancy/context.py` | create | `TenantContext` |
| `src/supportkit/core/graph/state.py` | create | `SupportContext`, `SupportState`, `thread_id_for` |
| `src/supportkit/core/text.py` | create | `detect_language` |
| `src/supportkit/cli.py` | modify | add `seed`, `serve`, `eval` commands |
| `tests/conftest.py` | create | loop factory hook, `database_url`, `pool` fixtures |
| `tests/test_context.py`, `tests/test_text.py`, `tests/test_cli_stubs.py` | create | unit tests |
| `tests/test_settings.py` | modify | add cases below |
| `.env.example`, `.gitignore` | modify | new env vars; ignore `evals/reports/` |

## Interfaces

### Dependencies (run exactly these; never hand-edit `uv.lock`)
```
python -m uv add langchain-anthropic tzdata
python -m uv add --dev faker streamlit
```
In `pyproject.toml` `[tool.pytest.ini_options]` add `pythonpath = ["."]` (so tests can import the top-level `seed`, `evals`, `ui` packages).

### `settings.py` — add two fields to `Settings`
```python
supportkit_model: str = "fake:rules"      # env SUPPORTKIT_MODEL; "provider:model" or "fake:rules"
supportkit_demo_mode: bool = False        # env SUPPORTKIT_DEMO_MODE; enables the demo-only /chat endpoints
```

### `.env.example` — append
```
# LLM for the agent. "fake:rules" = built-in deterministic model (no API key, used by tests/CI).
# Real model example: SUPPORTKIT_MODEL=anthropic:<model-id>  (also set ANTHROPIC_API_KEY)
SUPPORTKIT_MODEL=fake:rules
# ANTHROPIC_API_KEY=

# DEMO ONLY: mounts /chat, which trusts X-Demo-* identity headers. Never enable on a real deployment.
SUPPORTKIT_DEMO_MODE=false
```
`.gitignore` — append `evals/reports/`.

### `db.py`
```python
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

def create_pool(database_url: str, *, min_size: int = 1, max_size: int = 10) -> AsyncConnectionPool:
    """Unopened pool shared by repositories and AsyncPostgresSaver. Use `async with pool:`."""
    return AsyncConnectionPool(
        database_url, min_size=min_size, max_size=max_size, open=False,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
    )
```
The three `kwargs` are what `AsyncPostgresSaver` requires of its connections (verified against `AsyncPostgresSaver.from_conn_string` in the installed 3.2.1).

### `aio.py`
```python
import asyncio, sys
from collections.abc import Coroutine
from typing import Any, TypeVar
T = TypeVar("T")

# psycopg async cannot run on Windows' default ProactorEventLoop.
UVICORN_LOOP: str = "asyncio:SelectorEventLoop" if sys.platform == "win32" else "auto"

def run(coro: Coroutine[Any, Any, T]) -> T:
    """asyncio.run() replacement that uses SelectorEventLoop on Windows."""
    factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    with asyncio.Runner(loop_factory=factory) as runner:
        return runner.run(coro)
```

### `core/tenancy/context.py`
```python
SHOP_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
CUSTOMER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

@dataclass(frozen=True, slots=True)
class TenantContext:
    shop_id: str
    customer_id: str | None          # None = identity not verified
    # __post_init__: raise ValueError if shop_id does not match SHOP_ID_RE,
    # or customer_id is not None and does not match CUSTOMER_ID_RE.
```

### `core/graph/state.py`
```python
CHANNEL_USER_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")   # no ":" → thread_id is unambiguous

@dataclass(frozen=True)
class SupportContext:                 # PLAN.md §2.7 — server-supplied only, never checkpointed
    shop_id: str
    channel: Literal["line", "web"]
    channel_user_id: str
    customer_id: str | None
    now: str                          # ISO datetime, Asia/Bangkok
    # __post_init__: build TenantContext(shop_id, customer_id) to validate both ids;
    # ValueError if channel not in ("line", "web") or channel_user_id fails CHANNEL_USER_ID_RE.

    @property
    def tenant(self) -> TenantContext: ...

def thread_id_for(ctx: SupportContext) -> str:
    return f"{ctx.shop_id}:{ctx.channel}:{ctx.channel_user_id}"

def bangkok_now() -> str:
    """datetime.now(ZoneInfo("Asia/Bangkok")).isoformat(timespec="seconds")"""

class SupportState(TypedDict):        # copy PLAN.md §2.7 exactly, same field names, types and comments
    messages: Annotated[list[AnyMessage], add_messages]
    summary: str
    turn_id: str
    language: Literal["th", "en"]
    triage: dict | None
    memory_context: str
    in_business_hours: bool
    tool_rounds: int
    tool_failures: int
    guard_attempts: int
    guard_violations: list[str]
    escalation_reasons: list[str]
    draft_reply: str | None
    staff_decision: dict | None
    handoff_mode: Literal["none", "human"]
    final_reply: str | None
    usage: list[dict]
```
Do not use `slots=True` on `SupportContext` (LangGraph introspects `context_schema`; plain frozen dataclass is what the Phase 1 spike verified).

### `core/text.py`
```python
def detect_language(text: str) -> Literal["th", "en"]:
    """thai = count of chars in U+0E00–U+0E7F; latin = count of ASCII letters.
    Return "th" if thai > 0 and thai >= 0.3 * (thai + latin), else "en"."""
```

### `cli.py` — three new commands (bodies exactly this thin; the imported modules arrive in specs 03, 07, 09)
```python
def _repo_on_path() -> None:
    root = str(PROJECT_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)

@app.command()
def seed() -> None:
    """Load the deterministic demo dataset (baan-bai-cha + shop-b). Replaces only those two shops' rows."""
    _repo_on_path()
    from seed.load import seed_database
    counts = seed_database(get_settings().database_url)
    for table, n in counts.items():
        typer.echo(f"{table}: {n}")

@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run the FastAPI app."""
    from supportkit.api.server import serve as _serve
    _serve(host, port)

@app.command("eval")
def eval_(
    dataset: Path = typer.Option(Path("evals/datasets/phase1.jsonl")),
    model: str | None = typer.Option(None, help="Overrides SUPPORTKIT_MODEL"),
    tag: str | None = typer.Option(None),
    case: str | None = typer.Option(None),
    report_dir: Path = typer.Option(Path("evals/reports")),
    require_all: bool = typer.Option(False, "--require-all"),
) -> None:
    """Run an eval dataset against the support graph."""
    _repo_on_path()
    from evals.runner import run_cli
    raise typer.Exit(run_cli(dataset=dataset, model=model, tag=tag, case=case,
                             report_dir=report_dir, require_all=require_all))
```

### `tests/conftest.py`
```python
def pytest_asyncio_loop_factories(config, item):
    # Must always return a non-empty mapping (pytest-asyncio 1.5 raises UsageError on None).
    return {"selector": asyncio.SelectorEventLoop}

@pytest.fixture(scope="session")
def database_url() -> str:            # get_settings().database_url; pytest.skip("Postgres not reachable")
    ...                               # if psycopg.connect(url, connect_timeout=2) raises OperationalError

@pytest.fixture
async def pool(database_url):         # async with create_pool(database_url, max_size=4) as p: yield p
    ...
```
Also `os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK", "true")` at module top.

## Behaviour
1. Existing `migrate` and `db-status` commands and existing tests are unchanged and still pass.
2. `seed` / `serve` / `eval` import their targets inside the function body, so `supportkit --help` works before those modules exist.
3. `SupportContext` and `TenantContext` raise `ValueError` on invalid ids at construction; nothing downstream re-validates.
4. `Settings` keeps `extra="ignore"`. Tests must construct `Settings(...)` with explicit kwargs and never rely on the developer's `.env` values for the two new fields.
5. No module in this spec reads `shop_id`/`customer_id` from anywhere; it only defines the types.

## Tests
`tests/test_context.py`
- `TenantContext("baan-bai-cha", "C-0001")` → ok; `TenantContext("baan-bai-cha", None)` → ok.
- `TenantContext("", "C-0001")`, `TenantContext("Shop B", "C-1")`, `TenantContext("shop:b", None)`, `TenantContext("shop-b", "")`, `TenantContext("shop-b", "a b")` → each `ValueError`.
- `SupportContext("shop-b", "web", "demo-guest-abc12345", None, "2026-11-15T12:00:00+07:00")` → ok; `.tenant == TenantContext("shop-b", None)`.
- `SupportContext(..., channel="sms", ...)` → `ValueError`; `channel_user_id="a:b"` → `ValueError`.
- `thread_id_for(SupportContext("baan-bai-cha","web","u1","C-0001", now))` → `"baan-bai-cha:web:u1"`.
- `dataclasses.replace`/attribute assignment on either context raises `FrozenInstanceError`.
- `bangkok_now()` ends with `"+07:00"`.

`tests/test_text.py`
- `"ออเดอร์ BC-1042 ถึงไหนแล้วคะ"` → `"th"`; `"Where is my order BC-1042?"` → `"en"`; `""` → `"en"`; `"BC-1042 ค่ะ"` → `"th"`;
  `"ออเดอร์ BC-1042 สถานะ: จัดส่งแล้วค่ะ จัดส่งโดย Kerry Express เลขพัสดุ KEX26111042TH"` → `"th"`.

`tests/test_settings.py` (add)
- `Settings(database_url="postgresql://u:p@h/db").supportkit_model` when env has no `SUPPORTKIT_MODEL` (use `monkeypatch.delenv` and `Settings(_env_file=None)`) → `"fake:rules"`; `supportkit_demo_mode` → `False`.
- `monkeypatch.setenv("SUPPORTKIT_DEMO_MODE", "true")` → `Settings(_env_file=None).supportkit_demo_mode is True`.

`tests/test_cli_stubs.py` (typer `CliRunner`)
- `supportkit --help` exit 0 and output contains `seed`, `serve`, `eval`, `migrate`, `db-status`.

## Acceptance criteria
```powershell
.\.venv\Scripts\ruff.exe check src tests db                       # All checks passed
$env:LANGGRAPH_STRICT_MSGPACK='true'; .\.venv\Scripts\python.exe -m pytest -q   # all pass, 0 warnings about event_loop_policy
.\.venv\Scripts\python.exe -c "import langchain_anthropic, faker, streamlit, tzdata; from supportkit.db import create_pool; from supportkit.core.graph.state import SupportState"   # exit 0
.\.venv\Scripts\supportkit.exe --help                             # lists the 5 commands
```

## Out of scope
- Any table, query, graph node, tool, API route. No `seed/`, `evals/`, `ui/`, `src/supportkit/api/` files.
- Do not change the Dockerfile or docker-compose.yml.
- Do not add a `shop_id`/`customer_id` field to `Settings`.
