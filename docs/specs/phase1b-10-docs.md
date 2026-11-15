# Phase 1b · Spec 10 — README, env example, commands

**Suggested implementer:** `quick-implementer` (text is given)
**Depends on:** 01–09 · **Blocks:** — · **Parallel with:** —

## Goal
Bring the user-facing docs in line with Phase 1b: the demo starts unverified, verification is by order
number + phone, there are new environment variables, and there is a coverage command. No code changes.

## Files
| Path | Action | Purpose |
|---|---|---|
| `README.md` | modify | demo walkthrough, env table, identity section |
| `.env.example` | modify | four new variables |
| `CLAUDE.md` | modify | one command line added |

## Interfaces
`.env.example` — append:
```
# DEMO ONLY: lets the X-Demo-Customer-Id header start a conversation account-verified. Needs SUPPORTKIT_DEMO_MODE=true.
SUPPORTKIT_DEMO_PREVERIFY=false

# Identity verification (Phase 2 moves these into the shop config).
# What a successful order+phone check unlocks: "order" (that order only) or "account" (all of that customer's orders).
SUPPORTKIT_IDENTITY_GRANT=order
# What is compared: "last4" (last 4 digits; a full number is accepted too) or "full". "account" requires "full".
SUPPORTKIT_IDENTITY_PHONE_MATCH=last4
# Failed verifications allowed per hour, per chat user and per order number.
SUPPORTKIT_IDENTITY_MAX_FAILED_PER_HOUR=5
```

`CLAUDE.md` — under "Commands", after the Tests line, add:
```
- Coverage gate: `.\.venv\Scripts\python.exe -m pytest -q tests/test_thai_text.py --cov=supportkit.core.thai_text --cov-branch --cov-fail-under=100`
```
Change nothing else in `CLAUDE.md`.

`README.md`:
1. In "Quick start (dev)", after the two demo commands, add:
   > Open the page and type `ออเดอร์ BC-1042 เบอร์ 0812345678`. The assistant verifies the order against the phone number and answers with the shipment status in the same reply. The sidebar lists more demo orders and phone endings (all data is fake).
2. Replace the body of "Demo mode" with:
   > `/chat` exists only with `SUPPORTKIT_DEMO_MODE=true`. The `X-Demo-Shop-Id` and `X-Demo-Session` headers choose the shop and the conversation; they do not say who the customer is. A conversation starts unverified, and the only way to see an order is to verify it with its order number and phone number. With `SUPPORTKIT_DEMO_PREVERIFY=true` the optional `X-Demo-Customer-Id` header starts a conversation already verified as that customer; this is a shortcut for demos and tests and must never be enabled on an exposed server. Real channels (LINE) arrive in Phase 3.
3. Add a section "Identity verification" after "Demo mode":
   > - A customer proves an order with the order number plus the phone number used for it. By default the last 4 digits are compared, and a successful check unlocks that one order for the conversation.
   > - Order numbers are accepted as `BC-1042`, `bc1042`, `BC 1042`, `#BC-1042` or with Thai digits; phone numbers with or without the leading 0, with `+66`, with spaces, hyphens or Thai digits.
   > - Wrong phone, unknown order and an order from another shop all get the same answer.
   > - After 5 failed attempts in an hour (per chat user, and per order number) verification is locked for that hour. `supportkit seed` clears the lock for the demo shops.
   > - Settings: `SUPPORTKIT_IDENTITY_GRANT`, `SUPPORTKIT_IDENTITY_PHONE_MATCH`, `SUPPORTKIT_IDENTITY_MAX_FAILED_PER_HOUR` (see `.env.example`).
4. If the README has a test command block, add the coverage command from `CLAUDE.md` below it.

## Behaviour
1. Keep the README's existing structure, headings and tone; touch only the places listed.
2. Do not document anything that is not implemented (no LINE, no staff page, no OTP).
3. Do not edit `PLAN.md`, `.claude/agents/*.md` or anything under `docs/specs/`.

## Tests
None (documentation). The suite must still pass.

## Acceptance
```powershell
.\.venv\Scripts\ruff.exe check src tests db seed evals ui
$env:LANGGRAPH_STRICT_MSGPACK='true'; .\.venv\Scripts\python.exe -m pytest -q
rg -n "SUPPORTKIT_DEMO_PREVERIFY|SUPPORTKIT_IDENTITY_" .env.example README.md      # 4 variables in .env.example, each mentioned in README
rg -n "persona|X-Demo-Customer-Id" README.md                                       # only inside the pre-verify sentence
```
Then run the end-of-phase acceptance script in `phase1b-README.md`.

## Out of scope
- `docs/architecture.md`, `docs/adding-a-client.md` (Phase 6).
- The tenancy invariants in `.claude/agents/architect.md`: the new wording is in `phase1b-plan-amendments.md` issue 4 and is applied by the user/orchestrator together with the PLAN.md amendments, not by an implementer.
