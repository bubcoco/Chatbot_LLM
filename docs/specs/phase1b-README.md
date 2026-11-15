# Phase 1b — Dynamic identity verification: spec index

Source: the rewritten PLAN.md (§2.3, §2.6, §2.7, §4, §7, §9 Phase 0/1). Phase 1 was built and closed
against the old plan; Phase 1b closes the gap to the new Phase 1 "done when":

> user can verify identity and retrieve order status in a single prompt
> ("ออเดอร์ BC-1042 เบอร์ 0812345678"); isolation between `baan-bai-cha` and `shop-b` verified.

Plan contradictions and the decisions taken are in [phase1b-plan-amendments.md](phase1b-plan-amendments.md).
**Two of them wait for the user** (issue 2: last 4 digits vs full phone; issue 3: order-only vs
account-wide grant). The specs implement the defaults and keep both flips to a settings change.

Library behaviour used by these specs was checked with throwaway spikes on the installed `.venv`
(langgraph 1.2.22, langgraph-prebuilt 1.1.2, langgraph-checkpoint-postgres 3.2.1, psycopg 3.3.9) against
the real Postgres: a tool returning `Command(update=…)` with its own `ToolMessage`; `ToolRuntime.state`
seeing that update in the next tool round of the same turn; reducers merging parallel tool writes;
`Overwrite` from `prepare` round-tripping through `AsyncPostgresSaver` under strict msgpack; session-level
`pg_advisory_lock` with `lock_timeout` set by `set_config(..., true)`, `LockNotAvailable` on timeout, and
release through a pool `reset` callback. The `thai_text` rule tables and the fake model's phone regex were
run against a reference implementation.

## Specs

| # | Spec | Summary | Implementer | Depends on | Est. |
|---|---|---|---|---|---|
| 01 | [thai-text](phase1b-01-thai-text.md) | `core/thai_text.py`: Thai digits, phone, order/tracking numbers, B.E. dates; 100% line+branch coverage; order tool uses it | implementer | — | 2.5 h |
| 02 | [migration](phase1b-02-migration.md) | Alembic `0003`: `customer_identities` composite key + `is_primary` + `grant_scope`, pending-refund unique index, `conversations`, `verification_failures` | quick-implementer | — | 1 h |
| 03 | [seed](phase1b-03-seed.md) | golden phones in every format (`C-0001` = `0812345678`), raw sheet rows with Thai numerals / B.E. dates | quick-implementer | 01, 02 | 1 h |
| 04 | [conversation-lock](phase1b-04-conversation-lock.md) | session-level advisory lock on a dedicated pool; replaces `thread_locks` in the API; 409 when busy | implementer | 02 | 2.5 h |
| 05 | [fake-model](phase1b-05-fake-model.md) | deterministic rules: order + phone → `verify_identity` → `get_order_status`; phone-only follow-up; failure and lock-out templates | implementer | 01 | 2 h |
| 06 | [identity-state](phase1b-06-identity-state.md) | `SupportContext` loses `customer_id`; identity fields + reducers in state; `prepare` revalidation; order authorization by link + scope | implementer | 02, 04 | 3 h |
| 07 | [verify-identity](phase1b-07-verify-identity.md) | `verify_identity` tool (`Command` update), failure rate limit, `IdentityPolicy`, prompt | implementer | 01, 02, 05, 06 | 3 h |
| 08 | [demo-api-ui](phase1b-08-demo-api-ui.md) | demo starts unverified; customer header only with `SUPPORTKIT_DEMO_PREVERIFY`; UI hint instead of persona picker | implementer | 05, 06, 07 | 2.5 h |
| 09 | [evals](phase1b-09-evals.md) | 14 new cases (24 total): single-prompt verify, wrong phone, other shop, enumeration lock-out, scope, shared phone, step G | implementer | 03, 05, 06, 07 | 2.5 h |
| 10 | [docs](phase1b-10-docs.md) | README, `.env.example`, coverage command | quick-implementer | 01–09 | 0.5 h |

## Waves (specs in one wave share no files)

```
Wave 1:  01 ‖ 02
Wave 2:  03 ‖ 04 ‖ 05
Wave 3:  06
Wave 4:  07
Wave 5:  08 ‖ 09
Wave 6:  10
```

| Wave | Why it is safe |
|---|---|
| 1 | 01: `core/thai_text.py`, `core/tools/orders.py`, `tests/test_thai_text.py`, `tests/test_order_no.py`, `pyproject.toml`, `uv.lock`, `ci.yml`. 02: one migration file, `tests/integration/test_schema.py` |
| 2 | 03: `seed/*`, `tests/test_seed_dataset.py`, `tests/integration/test_seed_load.py`. 04: `core/tenancy/lock.py`, `db.py`, `bootstrap.py`, `api/app.py`, `api/chat.py`, `tests/integration/test_lock.py`, `test_api_chat.py`, `integration/conftest.py`. 05: `core/llm/fake.py`, `tests/test_fake_model.py` |
| 3, 4 | 06 and 07 both edit `repositories.py`, `bootstrap.py`, `integration/conftest.py`, `tests/test_graph.py`; they follow 04 because of `bootstrap.py` and `conftest.py`. Strictly sequential |
| 5 | 08: `settings.py`, `api/demo_identity.py`, `api/app.py`, `ui/*`, API/UI/gating/settings tests, smoke test. 09: `evals/*`, `tests/test_eval_dataset.py`, `tests/integration/test_eval_runner.py` |
| 6 | docs only |

The suite and `supportkit eval --require-all` are green after every spec (10/10 until spec 09, then 24/24).
Architect review after each spec; 04, 06, 07 and 08 are the security-relevant reviews. 06 and 07 are the
two that change the tenancy invariant and should be reviewed with the acceptance greps in the specs.

## Decisions taken

| Topic | Decision |
|---|---|
| Identity source | `SupportContext` = `shop_id, channel, channel_user_id, now`. Customer identity exists only as a `customer_identities` row written by server code after a DB check. State fields `verified_customer_id` / `verified_order_scopes` are a per-conversation cache, written only by `verify_identity` and `prepare`, and re-derived from the DB by `prepare` every turn |
| Authorization predicate | one SQL predicate in `get_order_status`: link row (context's channel user ↔ order's customer, same shop) AND (`grant_scope = 'account'` OR order number in the conversation's scopes). State alone never authorizes; an order-grant link alone never authorizes |
| What a proof unlocks (**user decision 3**, default) | that order only (`grant_scope = 'order'`); `verified_customer_id` stays `None`. Flip: `SUPPORTKIT_IDENTITY_GRANT=account` |
| What is compared (**user decision 2**, default) | last 4 digits; a full number is accepted and its last 4 compared. Flip: `SUPPORTKIT_IDENTITY_PHONE_MATCH=full`. `account` + `last4` is rejected at start-up |
| Failure response | wrong phone / unknown order / other shop / malformed input → the identical `{"verified": false}`. `get_order_status` keeps Phase 1's identical `{"found": false, "order_no": …}` for every unauthorized case, now including "not verified" |
| Rate limit | built now: 5 failures per hour per channel user and per target order, DB clock, table `verification_failures`; over the limit → `too_many_attempts` without any lookup. Ticket on lock-out waits for Phase 3 |
| Lock | session-level `pg_advisory_lock` keyed on `conv:<shop_id>:<thread_id>`, dedicated `lock_pool` (8), 30 s wait → 409, `conversations` row upserted after the lock is held, checkpoint writes on the main pool inside the locked window. Row lock rejected: idle-in-transaction across LLM calls and self-deadlock against the turn's own row updates |
| Same-turn chaining | `verify_identity` returns `Command(update={"verified_order_scopes": [order_no], "messages": [ToolMessage]})`; the next tool round reads `runtime.state`. A model that issues both calls in one step gets not-found for the lookup and repeats it (one extra round, no leak) |
| Shared phones | no special flow: an order identifies its customer; a channel user can hold several links (`is_primary` on the first); "switch order" = verify another order |
| Order numbers | canonical `PREFIX-DIGITS`; accepts spaces, lower case, missing hyphen, Thai digits, one `#`. `BC1042` now normalizes to `BC-1042` (Phase 1 left it as `BC1042`) |
| Phone rules | 10-digit mobile `0[689]…` or 9-digit landline `0[2-57]…`; a zero is restored only for 9 digits starting 6/8/9 or 8 digits starting 2/3/4/5/7; `+66`/`0066`/`66` handled; everything else invalid |
| `thai_text.py` home | `src/supportkit/core/thai_text.py` (not `core/rag/`): used by tools, sync, guard, seed tests and the fake model. `core/text.py` stays |
| Demo identity | shop + session headers only; `X-Demo-Customer-Id` works only with `SUPPORTKIT_DEMO_PREVERIFY=true` (400 otherwise) and creates an account-level link server-side. `SUPPORTKIT_DEMO_MODE` gating unchanged |
| Settings, not shop config | identity policy lives in three env settings until the Phase 2 config loader exists |
| Evals | one dataset file, 24 cases; cases with `customer_id` are pre-linked server-side; verification state is deleted per case |
| Not built | `current_turn_id` updates, conversation `mode` gate, ticket on lock-out, `inbox_events` / `handoff_tickets` / `kb_chunks` / `pg_trgm`, PII masking helper, number parsing |

## End-of-phase acceptance script

Run from the repo root in PowerShell after all specs are merged.

```powershell
# 0. clean state
docker compose up -d db
.\.venv\Scripts\supportkit.exe migrate
.\.venv\Scripts\supportkit.exe seed
.\.venv\Scripts\ruff.exe check src tests db seed evals ui
$env:LANGGRAPH_STRICT_MSGPACK='true'; .\.venv\Scripts\python.exe -m pytest -q -rs      # all pass, no DB skips
.\.venv\Scripts\python.exe -m pytest -q tests/test_thai_text.py --cov=supportkit.core.thai_text --cov-branch --cov-fail-under=100
.\.venv\Scripts\supportkit.exe eval --model fake:rules --require-all                   # 24/24, security 14/14
```
```powershell
# 1. API in demo mode, pre-verify OFF (terminal A)
$env:SUPPORTKIT_DEMO_MODE='true'; Remove-Item Env:SUPPORTKIT_DEMO_PREVERIFY -ErrorAction SilentlyContinue; .\.venv\Scripts\supportkit.exe serve
# 2. page (terminal B)
.\.venv\Scripts\streamlit.exe run ui/demo_chat.py
```

| Step | Action | Expected |
|---|---|---|
| A | Page loads | no customer selector; sidebar says "Not verified yet" with the example prompt |
| B | Shop `baan-bai-cha`. Type `ออเดอร์ BC-1042 เบอร์ 0812345678` | **one reply** with shipped, Kerry Express, `KEX26111042TH` (PLAN "done when") |
| C | Note the Session ID. Stop terminal A, start it again, reload the page. Ask `แล้วเลขพัสดุล่ะคะ`, then `ออเดอร์ BC-1042 ถึงไหนแล้วคะ` | history shown; both replies contain `KEX26111042TH` without asking for the phone again |
| D | Same session: `ออเดอร์ BC-1043 ถึงไหนแล้วคะ` (same customer's other order) | not found among verified orders, asks for the phone; no status (order grant; flips if the user chooses account grant) |
| E | Same session: `ออเดอร์ BC-1050 ถึงไหนแล้วคะ` (another customer's) | same not-found wording; no `TH26110050A` |
| F | "New conversation". `ออเดอร์ BC-1042 ถึงไหนแล้วคะ` then `เบอร์ 5678 ค่ะ` | first reply asks for the phone; second gives `KEX26111042TH` |
| G | New conversation. `ออเดอร์ bc1042 เบอร์ ๐๘๑๒๓๔๕๖๗๘` | verified; `KEX26111042TH` |
| H | New conversation. `ออเดอร์ BC-1042 เบอร์ 0899999999`; new conversation, `ออเดอร์ BC-9999 เบอร์ 0812345678` | the two replies are the same text; no order data |
| I | **Shop `shop-b`**, new conversation. `ออเดอร์ BC-1042 เบอร์ 0812345678` | same failure text as H: the demo shop's phone opens nothing in `shop-b` |
| J | `shop-b`: `ออเดอร์ BC-1043 เบอร์ 0812345678` (order exists only in `baan-bai-cha`) | same failure text |
| K | `shop-b`, new conversation: `Where is order BC-1042? Phone 0201` | English reply with J&T Express `JT2611990042` — `shop-b`'s own order, no `KEX…` |
| L | `baan-bai-cha`, new conversation: `ออเดอร์ BC-1070 เบอร์ 0104`, then `ออเดอร์ BC-1071 เบอร์ 0104` | first: packed; second: shipped, `JT2611007100` (shared phone, two customers) |
| M | `baan-bai-cha`, new conversation: `ออเดอร์ BC-1061 เบอร์ 0001` … five times with different wrong endings, then `ออเดอร์ BC-1061 เบอร์ 7890` | five failure replies, then "temporarily locked" although `7890` is correct. In a **new** conversation `ออเดอร์ BC-1061 เบอร์ 7890` is also locked (per-order limit). `supportkit seed` clears it |
| N | Two browser tabs on the same Session ID, send a message in both at once | both get replies; history is strictly user/assistant alternating (database lock) |
| O | `curl -X POST http://127.0.0.1:8000/chat -H "X-Demo-Shop-Id: baan-bai-cha" -H "X-Demo-Session: accept1b0001" -H "X-Demo-Customer-Id: C-0001" -H "Content-Type: application/json" -d '{\"message\":\"hi\"}'` | 400 `demo_preverify_disabled` |
| P | Restart terminal A with `$env:SUPPORTKIT_DEMO_PREVERIFY='true'`; reload the page | customer selector is back; สมหญิง (C-0001) asking `ออเดอร์ BC-1043 ถึงไหนแล้วคะ` gets the pending-payment status without verifying (account-level link) |
| Q | Restart terminal A without `SUPPORTKIT_DEMO_MODE` | page reports no demo mode; `POST /chat` → 404 |

Database checks after the script:
```sql
select grant_scope, is_primary, count(*) from customer_identities group by 1, 2;   -- order links from B–L, account links from P
select count(*) from verification_failures where order_no = 'BC-1061';              -- 5
select count(*) from conversations;                                                -- one per conversation used
select count(*) from pg_locks where locktype = 'advisory';                         -- 0 while idle
```

Optional real-model pass (needs a key and model id from the user; small cost): set
`SUPPORTKIT_MODEL=anthropic:<model-id>`, repeat steps B–M, and run
`supportkit eval --model anthropic:<model-id>`. Only `forbidden:` failures are incidents. Expect exact
`tool_calls` mismatches where the model passes a differently formatted phone or issues both tool calls in
one step; hand those to the `evaluator`.

## Phase 1 carry-overs absorbed here

| From | Item | Where |
|---|---|---|
| Phase 1 "known limits" | per-thread serialisation was an in-process lock | spec 04 |
| Phase 1 "known limits" | no identity verification, no rate limiting | specs 06, 07 |
| Evaluator carry-over 1 | deterministic eval case for acceptance step G (order exists only in the other shop) | spec 09, `p1b-018` |
| Evaluator carry-over 2 (stopgap only) | `reply_not_contains: ["จัดส่งแล้ว"]` on `p1-009` | spec 09 |
| Evaluator carry-over 6 (part) | `tool_selection` threshold 0.90; cases for an order number without a hyphen / with Thai digits | spec 09, `p1b-011`, `p1b-012`, `p1b-014` |
| New plan, Phase 0 | `thai_text.py` with 100% coverage | spec 01 |
| New plan, §7 | pending-refund partial unique index; composite identity key; `conversations` | spec 02 |
| New plan, §7 seed plan | phone variants, shared phone, B.E. / Thai-numeral inputs | spec 03 |

Still open for Phase 2 evals: carry-overs 2 (grounding check), 3 (`leaked` flag, intermediate-message
scan), 4 (`forbidden_regex`), 5 (`tool_calls_mode` — now more pressing, see risks), 6 (remaining
categories).

## Known limits accepted for Phase 1b
- Last-4 verification is weak by design (10⁴ guesses, sequential order numbers). The rate limit and the order-only grant bound the damage to one order's status; nothing with PII is returned by any tool.
- The per-order lock-out lets anyone who knows an order number block its verification for an hour (already-verified conversations are unaffected). Phase 3 turns the lock-out into a staff ticket.
- A real model may call `verify_identity` and `get_order_status` in one step; that costs a tool round. Whether to force sequential tool calls per provider is a Phase 5 model-selection question.
- The lock is per process-and-database, not PgBouncer-transaction-pool safe; `lock_pool` size (8) caps concurrent turns.
- Identity policy is process-wide (env), not per shop, until the Phase 2 config loader.
- A provider error mid-turn still leaves a human message without a reply (unchanged from Phase 1).
- CI still cannot be proven green until the repository exists on GitHub.
