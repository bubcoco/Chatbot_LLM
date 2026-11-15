# Phase 1b · Spec 08 — Demo API and UI: unverified by default, pre-verify behind a flag

**Suggested implementer:** `implementer` for the API part (identity entry point), same run for the UI (small)
**Depends on:** 05, 06, 07 · **Blocks:** 10 · **Parallel with:** 09

## Goal
Make the demo show the real flow. A demo session starts **unverified**; the visitor proves an order with
`ออเดอร์ BC-1042 เบอร์ 0812345678` like a LINE customer would. The old "pick a customer" shortcut still
exists for demos and for tests of account-level behaviour, but only when a second flag is set. The demo
headers keep choosing the shop and the session; they no longer choose who the customer is unless that
flag is on. `SUPPORTKIT_DEMO_MODE` gating is unchanged.

## Files
| Path | Action | Purpose |
|---|---|---|
| `src/supportkit/settings.py` | modify | `supportkit_demo_preverify` |
| `src/supportkit/api/demo_identity.py` | modify | honour `X-Demo-Customer-Id` only with the flag |
| `src/supportkit/api/app.py` | modify | `/health` reports the flag; start-up warning text |
| `ui/demo_chat.py` | modify | persona selector only with the flag; demo-credentials hint |
| `ui/api_client.py` | — | unchanged |
| `tests/integration/test_api_chat.py` | modify | flag on for old tests; new unverified-flow tests |
| `tests/integration/test_serve_smoke.py` | modify | guest single-prompt flow |
| `tests/test_api_gating.py`, `tests/test_settings.py`, `tests/test_ui_demo_chat.py` | modify | new field / UI branches |

## Interfaces
```python
# settings.py
supportkit_demo_preverify: bool = False   # env SUPPORTKIT_DEMO_PREVERIFY; DEMO ONLY: lets X-Demo-Customer-Id create an account-level identity link
```
HTTP contract (all under `SUPPORTKIT_DEMO_MODE=true`; 404 otherwise, as today):

| Header | Required | Meaning |
|---|---|---|
| `X-Demo-Shop-Id` | yes | shop |
| `X-Demo-Session` | yes | `^[A-Za-z0-9]{8,32}$`; one session = one conversation |
| `X-Demo-Customer-Id` | no | only with `SUPPORTKIT_DEMO_PREVERIFY=true`: start the conversation account-verified as this customer |

| Situation | Response |
|---|---|
| missing/invalid shop, session or customer header format | 400 `invalid_demo_identity` (unchanged) |
| customer header present, pre-verify flag off | 400 `demo_preverify_disabled` |
| shop has no customers; or (flag on) customer not in that shop | 403 `unknown_demo_identity` (unchanged) |
| conversation locked by another request | 409 `conversation_busy` (spec 04) |

`GET /health` → `{"status", "model", "demo_mode", "demo_preverify"}` where
`demo_preverify = settings.supportkit_demo_mode and settings.supportkit_demo_preverify`.
Request and response bodies of `/chat` and `/chat/history` are unchanged.

`ui/demo_chat.py` constants:
```python
DEMO_HINTS = {   # fake seed data; shown so a visitor can try verification
    "baan-bai-cha": [
        ("BC-1042", "0812345678", "shipped, Kerry"),
        ("BC-1050", "6789", "delivered"),
        ("BC-1091", "0107", "shipped"),
        ("BC-1070", "0104", "shared phone (customer 1)"),
        ("BC-1071", "0104", "shared phone (customer 2)"),
    ],
    "shop-b": [
        ("BC-1042", "0201", "same order number, other shop"),
        ("BC-1050", "0202", "shipped"),
    ],
}
EXAMPLE_PROMPT = "ออเดอร์ BC-1042 เบอร์ 0812345678"
```
`PERSONAS` stays as it is.

## Behaviour
**API**
1. `demo_context` order of checks: format validation (400) → if a customer header is present and `request.app.state.settings.supportkit_demo_preverify` is false → 400 `demo_preverify_disabled`, before any database access → existence checks (403) → link (flag on, customer present) → return the context.
2. An empty `X-Demo-Customer-Id` counts as absent (unchanged), also with the flag off.
3. `channel_user_id` is `demo-<customer|guest>-<session>` (unchanged), so a pre-verified persona and the guest flow never share a thread.
4. With the flag on and a valid customer: `repositories.link_identity(conn, ChannelUser(shop, "web", channel_user_id), customer, "account")` (the interim behaviour from spec 06, now gated). This is the only place outside `verify_identity` that creates a link in `src/`, and the only one that grants `account`.
5. `create_app`: when demo mode is on, keep the existing warning; when the pre-verify flag is also on, log a second warning: `"DEMO PREVERIFY: X-Demo-Customer-Id grants account-level access without verification. Never enable outside a local demo."`. When demo mode is off the pre-verify flag has no effect at all (routes are not mounted).
6. Nothing in the request body or query string can carry identity (`extra="forbid"` stays).

**UI**
7. Fetch `/health` first. `preverify = bool(health.get("demo_preverify"))` (false when the API is unreachable).
8. `preverify` false (default): no customer selector is rendered; `identity = DemoIdentity(shop, None, session)`. The sidebar shows `st.sidebar.info` with the text `Not verified yet. Try: {EXAMPLE_PROMPT}` followed by the `DEMO_HINTS[shop]` rows as a small table (order, phone / last 4, note), captioned "Demo data (fake)".
9. `preverify` true: render the `Customer` selector exactly as today, plus the existing demo-only warning.
10. Error mapping gains: status 400 with detail `demo_preverify_disabled` → `"Pre-verified personas are disabled on this API. Set SUPPORTKIT_DEMO_PREVERIFY=true or use the verification flow."`; status 409 → `"This conversation is busy. Try again in a moment."`.
11. The session id stays the only value in the URL query string. The page still holds no business logic and never touches the database.

## Tests
`tests/integration/test_api_chat.py`
- `_app(database_url, model=None, *, preverify=True)` sets `supportkit_demo_preverify=preverify`; the existing `env` fixture uses the default, so every existing test keeps its meaning and passes unchanged.
- New fixture `env_guest` = same as `env` with `preverify=False`.
- `G(shop, session)` = headers without a customer. Fixture phones (spec 06): A/`C-1` `0812345678`.

| # | Test | Steps | Expected |
|---|---|---|---|
| 1 | `test_single_prompt_verify_and_status` | `env_guest`; A guest: `"ออเดอร์ BC-1042 เบอร์ 0812345678"` | 200; reply contains `TRACK-A-1042`; `thread_id` ends with `demo-guest-<session>` |
| 2 | `test_unverified_guest_is_asked_to_verify` | A guest: `ASK_1042` | 200; no `TRACK-`; reply equals `compose_order_reply({"found": False, "order_no": "BC-1042"}, "th")` |
| 3 | `test_two_step_verify` | A guest: `ASK_1042`, then `"เบอร์ 5678 ค่ะ"` | second reply contains `TRACK-A-1042` |
| 4 | `test_wrong_phone` | A guest: `"ออเดอร์ BC-1042 เบอร์ 0899999999"` then `ASK_1042` | neither reply contains `TRACK-`; first reply equals `VERIFY_FAILED["th"]` |
| 5 | `test_verify_is_per_shop` | **B** guest: `"ออเดอร์ BC-1042 เบอร์ 0812345678"` (A's phone); B guest (new session): `"ออเดอร์ BC-1050 เบอร์ 6789"` (order only in A) | both replies equal `VERIFY_FAILED["th"]`; no `TRACK-` |
| 6 | `test_identical_failure_replies` | fresh guest sessions: A, `BC-1042` with a wrong phone / A, unknown order `BC-7777` with the right phone / **B**, `"ออเดอร์ BC-1050 เบอร์ 6789"` (order and phone exist only in A) | the three replies are equal strings |
| 7 | `test_verification_is_per_session` | session 1 verifies `BC-1042`; session 2 (same shop) sends `ASK_1042` | session 2 reply has no `TRACK-` |
| 8 | `test_verified_scope_does_not_widen` | verify `BC-1042`, then `"ออเดอร์ BC-1043 ถึงไหนแล้วคะ"` (same customer), then `"ออเดอร์ BC-1050 ถึงไหนแล้วคะ"` (`C-2`) | second and third replies are the not-found replies; no `TRACK-A-1050` |
| 9 | `test_verification_survives_restart` | app 1 (`preverify=False`): guest verifies `BC-1042`; app 2, same headers: `ASK_1042` | app 2 reply contains `TRACK-A-1042` |
| 10 | `test_lockout_after_five_failures` | one guest: five wrong phones for `BC-1042`, then the right one | sixth reply equals `VERIFY_LOCKED["th"]`; no `TRACK-` |
| 11 | `test_customer_header_rejected_without_flag` | `env_guest`; `H(shop_a, "C-1", s)` on `POST /chat` and `GET /chat/history` | 400 `{"detail": "demo_preverify_disabled"}`; no `customer_identities` row for `demo-C-1-<s>`; no checkpoint for that thread |
| 12 | `test_empty_customer_header_is_guest` | `env_guest`; `X-Demo-Customer-Id: ""` | 200; thread ends with `demo-guest-<s>` |
| 13 | `test_preverified_persona_with_flag` | `env` (flag on): `H(shop_a, "C-1", s)`, `ASK_1042` | reply contains `TRACK-A-1042` (already covered by `test_happy_path`; assert additionally that the identity row has `grant_scope='account'`) |
| 14 | `test_body_cannot_carry_identity` | `env_guest`; body `{"message": "ออเดอร์ BC-1042", "customer_id": "C-1", "verified_order_scopes": ["BC-1042"]}` | 422 |

`tests/integration/test_serve_smoke.py`: drop the customer header; message `"ออเดอร์ BC-1042 เบอร์ 0812345678"`; assert `KEX26111042TH` in the reply; skip condition unchanged plus `customers.phone = '0812345678'` for `C-0001`; cleanup thread id is `baan-bai-cha:web:demo-guest-<session>`, and also delete `customer_identities`, `verification_failures` (by `channel_user_id = 'demo-guest-<session>'`) and `conversations` (by `thread_id`) rows.

`tests/test_api_gating.py`: `/health` with demo off → `demo_preverify is False` even when `supportkit_demo_preverify=True`; demo on + flag on → `True`; route list with demo off is still `["/health"]`.

`tests/test_settings.py`: default `supportkit_demo_preverify is False`; env `SUPPORTKIT_DEMO_PREVERIFY=true` → `True`.

`tests/test_ui_demo_chat.py`:
| Test | Setup | Expected |
|---|---|---|
| default page | `HEALTH` without `demo_preverify` (or `False`) | no selectbox labelled `Customer`; an info element containing `EXAMPLE_PROMPT`; sending a message calls `send_message` with `identity.customer_id is None` |
| pre-verify page | `HEALTH = {..., "demo_preverify": True}` | `Customer` selectbox present; the existing persona test (`identity.customer_id == "C-0001"`) runs in this mode |
| error mapping | `send_message` raises `ChatApiError(400, "demo_preverify_disabled")` / `ChatApiError(409, "conversation_busy")` | the two messages from rule 10 |
| API unreachable | `fetch_health` raises | page renders, no `Customer` selectbox |

## Acceptance
```powershell
.\.venv\Scripts\ruff.exe check src tests db seed evals ui
$env:LANGGRAPH_STRICT_MSGPACK='true'; .\.venv\Scripts\python.exe -m pytest -q        # whole suite green, none skipped
.\.venv\Scripts\supportkit.exe eval --require-all                                   # all pass
```
Manual: `$env:SUPPORTKIT_DEMO_MODE='true'; .\.venv\Scripts\supportkit.exe serve` and
`.\.venv\Scripts\streamlit.exe run ui/demo_chat.py` → no customer selector; typing the example prompt
returns the Kerry tracking number. Restart the API with `$env:SUPPORTKIT_DEMO_PREVERIFY='true'` → the
selector is back.
`rg -n "link_identity" src` → definition, `core/tools/identity.py`, `api/demo_identity.py` only.

## Out of scope
- Real channel authentication, LINE (Phase 3). Any staff page.
- `evals/` (spec 09), README and `.env.example` (spec 10).
- Streaming, new endpoints, changes to `ui/api_client.py`.
