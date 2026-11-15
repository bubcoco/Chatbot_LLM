# Phase 1 · Spec 08 — Streamlit demo chat page

**Suggested implementer:** `quick-implementer`
**Depends on:** 01 (streamlit dep); the HTTP contract in spec 07 (frozen, so this can be written before 07 lands) · **Parallel with:** 02, 05, 07

## Goal
A single Streamlit page that chats with the FastAPI demo endpoints. It lets the viewer pick a demo shop and persona (this is the Phase 1 stand-in for identity, clearly labelled as demo-only), keeps a session id so a conversation survives an API or Streamlit restart, and shows the conversation history loaded from the server. The page holds no business logic and never talks to the database or the graph directly.

## Files
| Path | Action | Purpose |
|---|---|---|
| `ui/__init__.py` | create | empty |
| `ui/api_client.py` | create | tiny sync HTTP client for the demo API |
| `ui/demo_chat.py` | create | the Streamlit page |
| `tests/test_ui_api_client.py` | create | client tests with `httpx.MockTransport` |
| `tests/test_ui_demo_chat.py` | create | `AppTest` smoke test |

## Interfaces

### `ui/api_client.py`
```python
DEFAULT_API_URL = "http://127.0.0.1:8000"

@dataclass(frozen=True)
class DemoIdentity:
    shop_id: str
    customer_id: str | None      # None = guest (unverified)
    session: str                 # ^[A-Za-z0-9]{8,32}$

class ChatApiError(Exception):
    def __init__(self, status_code: int | None, detail: str): ...   # status_code None = could not connect

def new_session_id() -> str:                 # secrets.token_hex(8) → 16 hex chars
def is_valid_session(value: str) -> bool:    # re.fullmatch(r"[A-Za-z0-9]{8,32}", value)
def identity_headers(identity: DemoIdentity) -> dict[str, str]: ...
def send_message(base_url: str, identity: DemoIdentity, message: str,
                 *, client: httpx.Client | None = None) -> dict: ...        # {"reply","thread_id","turn_id"}
def fetch_history(base_url: str, identity: DemoIdentity,
                  *, client: httpx.Client | None = None) -> list[dict]: ...  # [{"role","text"}]
def fetch_health(base_url: str, *, client: httpx.Client | None = None) -> dict: ...
```
- `identity_headers` → `{"X-Demo-Shop-Id": shop_id, "X-Demo-Session": session}` plus `"X-Demo-Customer-Id": customer_id` only when not `None`.
- When `client` is `None`, each function creates `httpx.Client(timeout=60.0)` and closes it.
- Non-2xx → `ChatApiError(status, detail)` where `detail` is the JSON body's `"detail"` if it is a string, else `f"HTTP {status}"`. `httpx.HTTPError` (connect/timeout) → `ChatApiError(None, "cannot reach API")`.

### `ui/demo_chat.py`
Top of file (so both `streamlit run ui/demo_chat.py` and `AppTest.from_file` find the client):
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import api_client          # always call as api_client.<fn>(...) so tests can monkeypatch the module
```
Constants:
```python
API_URL = os.environ.get("SUPPORTKIT_API_URL", api_client.DEFAULT_API_URL)
PERSONAS = {   # golden records from spec 03; label → customer_id
    "baan-bai-cha": {
        "สมหญิง (C-0001) — BC-1042, BC-1043": "C-0001",
        "อนันต์ (C-0002) — BC-1050, BC-1051": "C-0002",
        "Emma (C-0007) — BC-1090, BC-1091": "C-0007",
        "Guest (not verified)": None,
    },
    "shop-b": {
        "ปรีชา (C-0001) — BC-1042, BC-9001": "C-0001",
        "Sarah (C-0002) — BC-1050": "C-0002",
        "Guest (not verified)": None,
    },
}
```

## Behaviour
1. `st.set_page_config(page_title="supportkit demo", page_icon="🍵")`; title `supportkit — demo chat`.
2. **Sidebar**, in order:
   - `st.warning("Demo only: the persona selector stands in for customer identity. Real channels verify identity server-side.")`
   - `st.selectbox("Shop", list(PERSONAS))` (key `shop`), `st.selectbox("Customer", list(PERSONAS[shop]))` (key `persona`).
   - `st.text_input("Session ID", value=<current session>)` (key `session_input`) with help text "Keep this ID to continue the same conversation after a restart."
   - `st.button("New conversation")` → sets a new session id.
   - `st.caption` showing the API URL and, from `fetch_health`, the model name (or "API not reachable").
3. **Session id**: on first run take `st.query_params.get("session")` if `is_valid_session`, else `new_session_id()`; store in `st.session_state["session"]` and write it back to `st.query_params["session"]`. If the text input holds a different valid value, adopt it; if it is invalid, show `st.sidebar.error("Session ID must be 8–32 letters or digits.")` and keep the previous one. The session id is the only thing placed in the URL — never shop or customer.
4. `identity = DemoIdentity(shop, PERSONAS[shop][persona], session)`.
5. **History**: every run calls `api_client.fetch_history(API_URL, identity)` and renders each entry with `st.chat_message(role).write(text)`. The server is the source of truth; do not cache messages in `st.session_state`. Changing shop, persona or session therefore shows that thread's own history (the server keys threads by all three).
6. **Input**: `prompt = st.chat_input("พิมพ์ข้อความ… / Type a message…", max_chars=2000)`. When set: render it as a user message, then inside `st.chat_message("assistant")` with `st.spinner("…")` call `api_client.send_message(API_URL, identity, prompt)` and write `["reply"]`.
7. **Errors**: any `ChatApiError` → `st.error(...)`: status `None` → "Cannot reach the API at {API_URL}. Start it with: supportkit serve (SUPPORTKIT_DEMO_MODE=true)."; `404` → "The API is running without demo mode. Set SUPPORTKIT_DEMO_MODE=true."; `403` → "This demo persona does not exist. Run: supportkit seed."; otherwise "Request failed ({status}: {detail})." A history error shows the message and renders no history; the page must not raise.
8. No streaming, no tool-call display, no DB access, no import from `supportkit` or `seed`.

## Tests
`tests/test_ui_api_client.py` — import `from ui import api_client`; build `httpx.Client(transport=httpx.MockTransport(handler), base_url=...)` and pass it as `client`.
| # | Input | Expected |
|---|---|---|
| 1 | `identity_headers(DemoIdentity("baan-bai-cha", "C-0001", "abcd1234"))` | exactly the 3 headers |
| 2 | `identity_headers(DemoIdentity("shop-b", None, "abcd1234"))` | exactly 2 headers, no `X-Demo-Customer-Id` |
| 3 | `send_message(...)`, handler returns `200 {"reply":"ok","thread_id":"t","turn_id":"u"}` | returns that dict; captured request is `POST /chat`, JSON body exactly `{"message": "<text>"}`, headers as #1 |
| 4 | `fetch_history(...)`, handler returns `200 {"thread_id":"t","messages":[{"role":"user","text":"hi"}]}` | `[{"role":"user","text":"hi"}]`; request is `GET /chat/history` |
| 5 | handler returns `403 {"detail":"unknown_demo_identity"}` | `ChatApiError` with `status_code == 403`, `detail == "unknown_demo_identity"` |
| 6 | handler returns `422 {"detail":[{"msg":"x"}]}` | `ChatApiError(422, "HTTP 422")` |
| 7 | handler raises `httpx.ConnectError("boom")` | `ChatApiError` with `status_code is None` |
| 8 | `new_session_id()` twice | two different strings, each passing `is_valid_session` |
| 9 | `is_valid_session` on `"abc"`, `"abcd-1234"`, `"a"*33`, `"abcd1234"` | `False, False, False, True` |

`tests/test_ui_demo_chat.py` — `from streamlit.testing.v1 import AppTest`. Insert the `ui` directory at the front of `sys.path`, `import api_client`, and `monkeypatch.setattr` its functions before `AppTest.from_file("ui/demo_chat.py").run()`.
| # | Patches | Expected |
|---|---|---|
| 1 | `fetch_history` → `[{"role":"user","text":"สวัสดี"},{"role":"assistant","text":"สวัสดีค่ะ"}]`; `fetch_health` → `{"status":"ok","model":"fake:rules","demo_mode":True}` | `not at.exception`; `len(at.chat_message) == 2`; sidebar has 2 selectboxes and 1 warning |
| 2 | `fetch_history` raises `ChatApiError(None, "cannot reach API")`; `fetch_health` raises the same | `not at.exception`; `len(at.error) >= 1` |
| 3 | as #1, then `at.chat_input[0].set_value("ออเดอร์ BC-1042").run()` with `send_message` patched to a recorder returning `{"reply":"ตอบแล้วค่ะ","thread_id":"t","turn_id":"u"}` | recorder called once with message `"ออเดอร์ BC-1042"` and an identity whose `shop_id == "baan-bai-cha"` and `customer_id == "C-0001"`; `not at.exception` |

## Acceptance criteria
```powershell
.\.venv\Scripts\ruff.exe check src tests db ui
$env:LANGGRAPH_STRICT_MSGPACK='true'; .\.venv\Scripts\python.exe -m pytest -q tests/test_ui_api_client.py tests/test_ui_demo_chat.py
$env:LANGGRAPH_STRICT_MSGPACK='true'; .\.venv\Scripts\python.exe -m pytest -q
```
Manual (after specs 03 and 07): with the API running in demo mode, `.\.venv\Scripts\streamlit.exe run ui/demo_chat.py` → ask "ออเดอร์ BC-1042 ถึงไหนแล้วคะ" as สมหญิง → reply with Kerry Express / `KEX26111042TH`.

## Out of scope
- The staff page (Phase 3), streaming, authentication, showing tool calls or token usage.
- Anything under `src/`. The page must work purely against the HTTP contract.
- If an `AppTest` assertion in this spec cannot be satisfied because of a Streamlit API difference, stop and report rather than changing page behaviour.
