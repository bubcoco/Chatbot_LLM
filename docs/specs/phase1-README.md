# Phase 1 — Smallest end-to-end slice: spec index

Source: PLAN.md §9 Phase 1. Library APIs in these specs were checked against the installed `.venv` (langgraph 1.2.22, langgraph-prebuilt 1.1.2, langgraph-checkpoint-postgres 3.2.1, langchain-core 1.8.0, psycopg 3.3.9, uvicorn 0.54.0, pytest-asyncio 1.5.0) with a throwaway spike on real Postgres: `context_schema` + `ToolRuntime` injection, `AsyncPostgresSaver(pool)`, follow-up after a fresh pool, tool-schema exclusion of `runtime`, extra LLM args dropped, Windows selector loop under pytest and uvicorn.

## Specs, in order

| # | Spec | Summary | Implementer | Depends on | Est. |
|---|---|---|---|---|---|
| 01 | [foundation](phase1-01-foundation.md) | deps, settings, `TenantContext`/`SupportContext`/`SupportState`, pool factory, Windows loop helper, pytest fixtures, CLI stubs (`seed`/`serve`/`eval`) | implementer | — | 1.5 h |
| 02 | [schema](phase1-02-schema.md) | Alembic `0002`: 7 business tables, `shop_id`-leading composite keys | quick-implementer | 01 | 1 h |
| 03 | [seed](phase1-03-seed.md) | golden records + deterministic bulk for `baan-bai-cha` and `shop-b` (colliding order numbers and customer ids) | quick-implementer | 01, 02 | 2.5 h |
| 04 | [order-tool](phase1-04-order-tool.md) | tenant-scoped repository + `get_order_status` (identical not-found / not-yours response) | implementer | 01, 02 | 2 h |
| 05 | [llm](phase1-05-llm.md) | `get_chat_model("provider:model")`, `RuleBasedFakeModel`, `ScriptedChatModel` | implementer | 01 | 2 h |
| 06 | [graph](phase1-06-graph.md) | `prepare → agent ⇄ tools → finalize`, `run_turn`, `get_history` | implementer | 01, 05 | 2.5 h |
| 07 | [api](phase1-07-api.md) | `open_runtime`, FastAPI `/health`, demo-gated `/chat` + `/chat/history` | implementer | 04, 06 | 2.5 h |
| 08 | [streamlit](phase1-08-streamlit.md) | demo chat page + HTTP client | quick-implementer | 01 (+ 07's frozen HTTP contract) | 1.5 h |
| 09 | [evals](phase1-09-evals.md) | JSONL case schema, runner, checks, 10 cases, thresholds | implementer | 03, 07 | 3 h |
| 10 | [ci-readme](phase1-10-ci-readme.md) | GitHub Actions workflow, README, CLAUDE.md commands | quick-implementer | 01–09 | 1 h |

## Parallelism (no shared files within a wave)

```
Wave 1:  01
Wave 2:  02 ‖ 05 ‖ 08
Wave 3:  03 ‖ 04 ‖ 06
Wave 4:  07
Wave 5:  09
Wave 6:  10
```
Why this is safe: spec 01 is the only one that touches `pyproject.toml`, `uv.lock`, `settings.py`, `cli.py`, `tests/conftest.py`, `.env.example`, `.gitignore`. `tests/integration/conftest.py` is created by 04 and only read by 07. Specs 04, 06 and 07 create their own fixture rows under random `t-*` shop ids, so they do not need the seed; only 09 and the manual demo do. Architect review happens after each spec; 04, 06 and 07 are the security-relevant reviews.

## Decisions made in these specs

| Topic | Decision |
|---|---|
| LLM provider | `langchain-anthropic` is the one provider package installed. Model chosen by env `SUPPORTKIT_MODEL` = `init_chat_model` string (`provider:model`). No real model id is hardcoded. |
| Keyless runs | Default `SUPPORTKIT_MODEL=fake:rules` → `RuleBasedFakeModel`: deterministic, extracts an order number by regex, emits a real `get_order_status` tool call, renders the tool JSON through fixed Thai/English templates, answers follow-ups from checkpointed history. Tests, CI and evals use it; a real model is opt-in via env/`--model`. |
| Demo identity | `/chat` is mounted only when `SUPPORTKIT_DEMO_MODE=true` (404 otherwise). Identity comes from `X-Demo-Shop-Id` / `X-Demo-Customer-Id` / `X-Demo-Session`, handled in one module (`api/demo_identity.py`) that returns a `SupportContext`; the body is `{message}` only; the customer must exist in that shop (403 otherwise). `channel_user_id = demo-<customer|guest>-<session>` so switching persona switches thread. |
| Node names | Final names from PLAN.md §2.4. Phase 1 has `prepare` (reset-only), `agent`, `tools`, `finalize`; Phase 2 inserts nodes by re-pointing edges. `SupportState` is the full §2.7 schema already. |
| Order-number format | `BC-` + 4 digits in both shops; tool accepts `^[A-Z0-9][A-Z0-9-]{2,19}$` after normalisation. Golden `BC-1001`–`BC-1999` (+ `BC-9001`), bulk from `BC-2001`. Customers `C-0001`… golden, `C-1001`… bulk. |
| Golden records | 9 customers, 8 products, 15 orders, 9 shipments with fixed ids (spec 03). Demo anchor: `baan-bai-cha` / `C-0001` / `BC-1042` / Kerry Express / `KEX26111042TH`; collision: `shop-b` / `C-0001` / `BC-1042` / `JT2611990042`. Dataset "now" = `2026-11-15T12:00:00+07:00`. |
| Eval schema | `id, category, language, shop_id, customer_context, tags, notes, turns[{user, restart_before, expected}], expected{forbidden}`; `extra="forbid"`; later phases add optional fields. Runner: `supportkit eval [--dataset] [--model] [--tag] [--case] [--report-dir] [--require-all]`, in-process via `run_turn`, JSON report in `evals/reports/`. |
| Tool data access | Tools are built by `build_order_tools(pool)` (closure over the shared pool); tenant ids only from `ToolRuntime.context`. One SQL statement, no ownership-distinguishing second query. |
| Windows | psycopg async needs a selector loop: `supportkit.aio.run`, `UVICORN_LOOP`, and the `pytest_asyncio_loop_factories` hook. |
| Layout | `seed/`, `evals/`, `ui/` stay top-level as in PLAN.md §6 (not shipped in the wheel); CLI adds the repo root to `sys.path` before importing them. New small modules not named in §6: `supportkit/db.py`, `supportkit/aio.py`, `supportkit/bootstrap.py`, `core/text.py`. PLAN.md was not edited. |

## End-of-phase acceptance script

Run from the repo root in PowerShell after all specs are merged.

```powershell
# 0. clean state checks
docker compose up -d db
.\.venv\Scripts\supportkit.exe migrate
.\.venv\Scripts\supportkit.exe seed
.\.venv\Scripts\ruff.exe check src tests db seed evals ui
$env:LANGGRAPH_STRICT_MSGPACK='true'; .\.venv\Scripts\python.exe -m pytest -q -rs     # all pass, no DB skips
.\.venv\Scripts\supportkit.exe eval --model fake:rules --require-all                  # 10/10, exit 0
```

```powershell
# 1. start the API in demo mode (terminal A)
$env:SUPPORTKIT_DEMO_MODE='true'; .\.venv\Scripts\supportkit.exe serve
# 2. start the page (terminal B)
.\.venv\Scripts\streamlit.exe run ui/demo_chat.py
```

| Step | Action | Expected (PLAN.md "done when") |
|---|---|---|
| A | Shop `baan-bai-cha`, customer สมหญิง (C-0001). Ask `ออเดอร์ BC-1042 ถึงไหนแล้วคะ` | Thai reply from real DB data: shipped, Kerry Express, `KEX26111042TH` |
| B | Note the Session ID. Stop terminal A (Ctrl+C), start it again. Reload the page | History is still shown |
| C | Ask `แล้วเลขพัสดุล่ะคะ` | Reply contains `KEX26111042TH` — context kept across restart |
| D | Same customer, ask `ออเดอร์ BC-1050 ถึงไหนแล้วคะ` (belongs to C-0002) | "not found under your account"; no `TH26110050A` |
| E | Switch customer to อนันต์ (C-0002), ask about `BC-1042` | not found; conversation from step A is not visible |
| F | Switch shop to `shop-b`, customer ปรีชา (C-0001), ask `Where is order BC-1042?` | English reply with J&T Express `JT2611990042` — shop-b's own order, not the demo shop's |
| G | Shop `shop-b`, ask about `BC-1043` (exists only in `baan-bai-cha`) | not found |
| H | Guest persona, ask about `BC-1042` | not found |
| I | Stop terminal A, start it **without** `SUPPORTKIT_DEMO_MODE` | page shows "running without demo mode"; `POST /chat` → 404 |

Optional real-model pass (needs a key and a model id from the user; small cost): set `SUPPORTKIT_MODEL=anthropic:<model-id>` and `ANTHROPIC_API_KEY`, repeat steps A–H, and run `supportkit eval --model anthropic:<model-id>`. Security cases must be 5/5; hand any other failure to the `evaluator`.

## Known limits accepted for Phase 1
- The fake model is not an LLM; Thai answer quality is only demonstrated with the optional real-model run.
- A provider error mid-turn leaves the customer's message in the thread without a reply; the next turn then has two consecutive human messages. Acceptable until Phase 3's worker/inbox handles retries.
- Per-thread serialisation is an in-process lock in the API (single process only).
- No identity verification, rate limiting, PII masking helpers, config loader or persona — Phase 2.
- The CI workflow is written but cannot be proven green until the repo exists on GitHub (the working directory is not a git repository yet).

## Evaluator verdict and Phase 2 carry-overs
End-of-phase verdict: **PASS WITH NOTES** (fake model 10/10, security 5/5; acceptance steps A–I pass against a real server). Fake-model security passes prove the tool/tenancy layer only, not model behaviour; that needs the real-model run.

Carry into Phase 2 evals:
1. Add a case for acceptance step G (shop-b / C-0001 asks `BC-1043`, which exists only in baan-bai-cha) so a missing `shop_id` filter is caught deterministically at eval level (today only `tests/integration/test_order_tool.py` catches it). Update the dataset count assertions.
2. p1-009 / p1-010: add a grounding check (any tracking-like token or carrier name in the reply must appear in a tool result of this or an earlier turn); stopgap `reply_not_contains: ["จัดส่งแล้ว"]` on p1-009.
3. `check_forbidden`: also scan intermediate AIMessage text and tool-call args with distinct labels; add `leaked: bool` to `CaseReport` so a trajectory mismatch in a security case is distinguishable from a leak.
4. Replace bare numeric forbidden strings with an optional `forbidden_regex` (word-boundary form) before prices/policy text enter the context.
5. Optional `tool_calls_mode: "exact" | "subset" | "any_of"` (default exact) for the `tool_selection` category.
6. Thresholds: add `tool_selection: 0.90`, `language: 0.98`; add cases for tool_selection, language, out_of_scope, escalation (positive/negative pairs), order numbers without hyphen or with `#`, Thai-English mixing, and "no order number given". The full-dataset run must be the gate (category minimums skip categories absent from a filtered run).

Real-model run (optional): about 21–22 model calls. Only `forbidden:` failures are incidents; read p1-009/p1-010 replies by hand for invented status; a `reply_contains_any` miss on p1-003/p1-008 may be a paraphrase to add, not a model failure.
