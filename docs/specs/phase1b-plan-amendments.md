# Phase 1b — PLAN.md amendments

PLAN.md was rewritten after Phase 1 closed. This file lists the nine places where the new plan is
contradictory, under-specified or stale, the decision the Phase 1b specs are built on, and the exact
replacement text for PLAN.md. **PLAN.md itself has not been edited**; apply these once the user has
answered the two open decisions (issues 2 and 3).

Library behaviour quoted here was checked on the installed `.venv` (langgraph 1.2.22,
langgraph-prebuilt 1.1.2, langgraph-checkpoint-postgres 3.2.1, psycopg 3.3.9) with throwaway spikes on
the real Postgres, not from memory.

| # | Issue | Status |
|---|---|---|
| 1 | Order-number normalization | decided |
| 2 | Full phone vs last 4 digits | **AWAITING USER DECISION** (default specced: last 4) |
| 3 | What a successful verification unlocks | **AWAITING USER DECISION** (default specced: that order only) |
| 4 | Who writes identity into state, revalidation, rate limit, error message | decided |
| 5 | FAQ cache placement | decided |
| 6 | Per-conversation lock design | decided (session-level advisory lock) |
| 7 | Schema fixes for later phases | noted, not built in 1b |
| 8 | Phone normalization rules | decided |
| 9 | Stale version table | decided |

---

## 1. Order-number normalization (§2.6 step 3)

**Problem.** "Strip spaces and hyphens, convert to uppercase (`bc-1042` / `BC 1042` → `BC-1042`)" is
self-contradictory: stripping hyphens gives `BC1042`, not `BC-1042`. Order and tracking numbers also need
different rules (tracking numbers have no hyphen in canonical form).

**Decision.** One canonical order-number form, `PREFIX-DIGITS`: 1–6 ASCII letters, one hyphen, 1–12
digits. Accepted on input: Thai digits, surrounding or inner whitespace, lower case, a missing hyphen, one
leading `#`. Anything else is invalid (`None`), never "best effort". Tracking numbers are normalized
separately: no spaces, no hyphens, upper case, 8–24 alphanumerics. A shop whose order numbers do not fit
`PREFIX-DIGITS` gets a per-shop `order_no_pattern` config key when such a client exists; not before.

**Replacement text for §2.6 step 3:**
> 3. **Order numbers:** canonical form is `PREFIX-DIGITS` (1–6 letters, hyphen, 1–12 digits, e.g.
>    `BC-1042`). Input is accepted with Thai digits, spaces, lower case, a missing hyphen or one leading
>    `#` (`bc-1042` / `BC 1042` / `bc1042` / `#BC-๑๐๔๒` → `BC-1042`); anything else is rejected.
>    **Tracking numbers:** remove spaces and hyphens, convert to upper case; valid when 8–24
>    alphanumerics (`kex 2611-1042 th` → `KEX26111042TH`).

---

## 2. Full phone vs last 4 digits — AWAITING USER DECISION

**Problem.** Q3 and §4's threat table say "order number + last 4 digits of phone"; §4 "Dynamic Chaining"
and the Phase 1 "done when" use a full number (`ออเดอร์ BC-1042 เบอร์ 0812345678`). They describe
different proofs.

**Options.**

| | A. Last 4 digits (default, specced) | B. Full phone required |
|---|---|---|
| What the customer types | 4 digits, or the full number (only its last 4 are compared) | the full number in any format |
| Guess space per order | 10⁴ | ~10⁸ |
| Friction | lowest; works when the sheet stores a mangled number, because last 4 survive a dropped `0` / `+66` | fails when the sheet's number is not normalizable |
| Safe to combine with | order-only grant (issue 3 option A) | either grant |

**Recommendation: A, but only together with issue 3 option A.** With last 4 digits and sequential order
numbers, the only real protection is the rate limit (issue 4), so the proof must unlock little: one
order's status, with no PII in the tool response. The two decisions are coupled, and the code enforces the
coupling: `IdentityPolicy(grant="account", phone_match="last4")` raises at start-up.

**Flip cost.** One setting: `SUPPORTKIT_IDENTITY_PHONE_MATCH=full` (Phase 2: `identity.verification`
in the shop config). No schema or graph change. Eval cases that verify with 4 digits (`p1b-012`,
`p1b-013`, `p1b-020`, `p1b-023`) then expect a failure and must be rewritten.

**Replacement text (Q3 assumption cell):**
> First-time verification by **order number + the phone number used for the order**. By default only the
> last 4 digits are compared (the customer may type 4 digits or the whole number); a shop can require the
> full number (`identity.verification: order_and_phone_full`). The proof links
> `(shop_id, channel, channel_user_id)` to the order's `customer_id` in `customer_identities` and, by
> default, unlocks **that order only** (see §4). Verification resolves in graph state so a same-turn
> lookup works.

**Replacement text (§9 Phase 1 "Done when")** — unchanged wording, plus one clause:
> … in a single prompt ("ออเดอร์ BC-1042 เบอร์ 0812345678" — the full number is accepted, its last 4 digits
> are what is compared); isolation between `baan-bai-cha` and `shop-b` verified.

---

## 3. Verification scope — AWAITING USER DECISION

**Problem.** §4 has `verify_identity` set both `verified_customer_id` and `verified_order_scopes` after an
order-number + phone check, which makes one weak proof unlock the whole account (every order, and from
Phase 4 the customer's long-term memory). §4 "Shared Family Phones" then says verification may instead be
bound "specifically to the verified `order_no` scope". The plan never picks.

**Options.**

| | A. Order-only grant (default, specced) | B. Account-wide grant |
|---|---|---|
| After verifying `BC-1042` | `BC-1042` is readable in this conversation. `BC-1043` (same customer) needs its own verification | all orders of that customer are readable; `verified_customer_id` is set |
| `verified_customer_id` | stays `None` until a stronger proof exists (today: only the demo pre-verify flag) | set by `verify_identity` |
| Memory key (§3 `user_key`) | stays `channel:channel_user_id` | becomes the customer id |
| Shared family phone | no special case: each order identifies its own customer | needs the "confirm recipient name" flow the plan mentions, or the second person sees the first person's orders |
| Damage from one guessed proof | one order's status | the whole order history |

**Recommendation: A.** It removes the shared-phone problem instead of managing it, and it keeps the blast
radius of a guessed proof to one order. `list_my_orders` (Phase 2) then lists only verified orders unless
the account is verified by something stronger (OTP, LINE Login linking, a staff action) — to be designed
when that tool is specced.

**How the design keeps the flip small.** The grant is a column, not a code path:
- `customer_identities.grant_scope` is `'order'` or `'account'`.
- The one authorization predicate (below) already handles both values.
- `verify_identity` writes the value from `IdentityPolicy.grant`. Flipping to B is
  `SUPPORTKIT_IDENTITY_GRANT=account` plus `SUPPORTKIT_IDENTITY_PHONE_MATCH=full` (issue 2 coupling).
  No migration, no graph change, no tool change. Eval case `p1b-021-scope-does-not-widen` encodes option
  A and must be inverted.

**Replacement text for §4 "Dynamic In-Turn Identity Verification & Shared Phones":**
> 1. **Dynamic chaining.** When an unverified customer writes "ออเดอร์ BC-1042 เบอร์ 081-234-5678", `agent`
>    calls `verify_identity(order_no, phone)`. On a match the tool upserts
>    `customer_identities (shop_id, channel, channel_user_id, customer_id, grant_scope)` and returns
>    `Command(update={"verified_order_scopes": [order_no], ...})`. The next tool round **in the same turn**
>    (`get_order_status`) runs with the new permission.
> 2. **What a proof unlocks.** `identity.grant: order` (default): only the verified order, for this
>    conversation; `verified_customer_id` stays unset. `identity.grant: account` (requires
>    `identity.verification: order_and_phone_full`): every order of that customer, and
>    `verified_customer_id` is set.
> 3. **Shared family phones.** An order identifies exactly one customer, so two people sharing a phone
>    each verify their own order; one channel user may hold links to several customers (composite key
>    `(shop_id, channel, channel_user_id, customer_id)`, one `is_primary`). "Switching order" is simply
>    verifying another order.
> 4. **Authorization predicate (the only one).** An order is readable by a channel user iff a
>    `customer_identities` row links that channel user to the order's customer in the same shop **and**
>    (that row has `grant_scope = 'account'` **or** the order number is in this conversation's
>    `verified_order_scopes`). Graph state alone never authorizes; a link row with `grant_scope = 'order'`
>    alone never authorizes.

**Replacement in §7 DDL (`customer_identities`):** add
`grant_scope TEXT NOT NULL DEFAULT 'order' CHECK (grant_scope IN ('order','account'))` and
`CREATE UNIQUE INDEX customer_identities_one_primary_idx ON customer_identities (shop_id, channel, channel_user_id) WHERE is_primary;`

**Replacement in §5 config:**
```yaml
identity:
  verification: order_and_phone_last4   # order_and_phone_last4 | order_and_phone_full
  grant: order                          # order | account (account requires order_and_phone_full)
  max_failed_lookups_per_hour: 5
```

---

## 4. Who writes identity into state

**Problem.** The plan moves identity from server context into checkpointed graph state without saying who
may write it, whether it is trusted on the next turn, or where the 5/hour limit lives.

**Decisions.**
1. **Writers.** Exactly two code paths write `verified_customer_id` / `verified_order_scopes`:
   `verify_identity` (after a server-side DB check, via `Command(update=...)`) and `prepare`
   (revalidation). `run_turn` passes only `messages` as graph input. No other node, tool or API field
   touches them.
2. **Revalidation.** `prepare` recomputes both fields from the database at the start of every turn and
   overwrites state: `verified_customer_id` = the channel user's account-level link (or `None`);
   `verified_order_scopes` = the stored scopes that still belong to a customer this channel user is linked
   to in this shop. A deleted link, a "forget me", a re-seed or an order re-assigned by sync therefore
   revokes access on the next turn. `get_order_status` additionally re-checks the link in its own SQL, so
   a stale or tampered checkpoint cannot authorize a read even within a turn.
3. **Tool schemas** never contain `shop_id`, `customer_id` or `channel_user_id`. `verify_identity` takes
   `order_no` and `phone`; `get_order_status` takes `order_no`.
4. **Rate limit: built in Phase 1b, not deferred.** Justification: with last-4 verification the rate
   limit is the only thing between a sequential order number and its status; shipping `verify_identity`
   without it would ship an enumeration oracle, and the plan's own eval category "Security: order
   enumeration" could not pass. Cost is one small table and two queries. Failures are counted over the
   last 60 minutes (database clock) on two keys: per channel user (`shop_id, channel, channel_user_id`) and
   per target order (`shop_id, order_no`). The second key exists because a web/demo attacker gets a new
   channel user for free. At 5 failures on either key, `verify_identity` answers `too_many_attempts`
   without looking anything up — also when the next guess would have been right. The "→ ticket" half of
   §4 waits for `handoff_tickets` (Phase 3).
5. **Error message.** Wrong phone, unknown order, order in another shop, malformed order number,
   malformed phone, customer without a phone: the tool result is the byte-identical string
   `{"verified": false}`. The lookup is a single statement and the comparison uses
   `hmac.compare_digest`. `too_many_attempts` is a distinct response, which is safe because it depends
   only on the count of previous attempts, never on whether the order exists.
6. **Parallel tool calls.** If a model emits `verify_identity` and `get_order_status` in one step, both
   run against the pre-verification state: the lookup returns not-found and the model must call it again.
   That costs one tool round and leaks nothing. Two parallel `verify_identity` calls are merged by state
   reducers (verified on langgraph 1.2.22: `Overwrite` from `prepare`, reducer-merge from tools, Postgres
   checkpointer, strict msgpack).

**New tenancy invariant (replaces "`shop_id` and `customer_id` come from server-side context" in
`.claude/agents/architect.md` and the "Principle" line of §4):**
> - `shop_id`, `channel` and `channel_user_id` come only from server-side context (`runtime.context`),
>   never from LLM tool arguments, message text or graph state.
> - A customer identity is never supplied by the caller or the model. It exists only as a
>   `customer_identities` row written by server code after a database check (`verify_identity`, or a
>   trusted server-side linker such as the demo pre-verify flag).
> - `verified_customer_id` and `verified_order_scopes` in graph state are a per-conversation cache of that
>   fact. Only `verify_identity` and `prepare` write them; `prepare` re-derives them from the database
>   every turn.
> - An order read always filters on `shop_id` **and** on the order's customer being linked to the
>   server-supplied channel user, **and** on (`grant_scope = 'account'` or the order number being in the
>   conversation's verified scopes). "Not found", "not yours", "not verified" and "other shop" return the
>   identical response.

**Replacement text for §2.4 table rows:**
> | `prepare` | No | Reset per-turn fields; **re-derive `verified_customer_id` and `verified_order_scopes` from `customer_identities` + `orders`**; load profile + memory; compute `in_business_hours`; check quota | Always → `triage` |
> | `tools` | No | `ToolNode`. Tools read server invariants from `SupportContext` and order scopes from `SupportState`; every order read re-checks the identity link in SQL. `verify_identity` (rate-limited) writes `customer_identities` and returns a state update | → `agent` |

**Replacement text for the §4 "Order enumeration" row:**
> Lookups require an identity link plus account grant or verified order scope; verification needs
> `order_no` + phone; one identical failure message; failures limited to 5/hour per channel user **and**
> per target order → `too_many_attempts` (ticket from Phase 3).

**Addition to §7 DDL:** the `verification_failures` table from spec `phase1b-02`.

---

## 5. FAQ cache placement

**Problem.** §2.3 draws the FAQ cache in the worker, before the graph (`GATE → FAQ → GRAPH`); §2.4 has it
as graph node `check_faq_cache` after `triage`. The worker position cannot work: the cache is only valid
for `policy_faq` intent with no customer/order identifiers, and that is known only after `triage`.

**Decision.** The graph node only. The worker never answers from the cache.

**Replacement for §2.3:** delete the `FAQ[...]` node and its three edges; replace with
`GATE -->|mode=bot| GRAPH`. Add one line under the diagram:
> The FAQ cache is the graph node `check_faq_cache` (§2.4), reached only after `triage`; a cache hit still
> passes through `finalize`, so usage, turn id and checkpoint history are recorded for every turn.

---

## 6. Per-conversation lock

**Problem.** The plan names `SELECT ... FOR UPDATE` on `conversations` "or" an advisory lock and does not
say how a lock survives a multi-second LLM call, which pool it uses, what happens when the row does not
exist yet, or how checkpoint writes relate to it.

**Comparison.**

| | Row lock (`SELECT … FOR UPDATE`) | Session-level `pg_advisory_lock` (chosen) |
|---|---|---|
| Held by | an open transaction on one connection | one connection, no transaction |
| During the LLM call | connection sits **idle in transaction** for seconds: pins the xmin horizon (vacuum bloat on the busy checkpoint tables), and is killed by any `idle_in_transaction_session_timeout` | connection sits plain idle |
| Other writes to the `conversations` row during the turn (`finalize` updating `current_turn_id`, gate flipping `mode`) | **self-deadlock** unless they run on the lock connection: the node uses a pooled connection, blocks on the row lock its own turn holds, and Postgres cannot detect it | no interaction; any connection may write the row |
| Row must exist first | yes: upsert, commit, then lock, in two steps | no; the row is upserted after the lock is held |
| Released on crash | yes (connection drops) | yes (connection drops) |
| Timeout | `lock_timeout` | `lock_timeout` (verified: raises `LockNotAvailable`) |
| Works behind PgBouncer transaction pooling | yes | no — acceptable: v1 is one process with direct connections (§1 out of scope: multi-instance) |

Both need one pinned connection per in-flight turn, so the connection cost is the same. The self-deadlock
and idle-in-transaction rows decide it.

**Decision.**
1. **Primitive:** `pg_advisory_lock(hashtextextended('conv:' || shop_id || ':' || thread_id, 0))`,
   session level. A 64-bit hash collision only makes two unrelated conversations wait for each other.
2. **Dedicated pool:** `lock_pool` (max 8 connections) used for nothing else. If locks shared the main
   pool (max 10), ten concurrent turns would each hold one connection and then wait forever for a
   connection to run their tools and checkpoint writes. `lock_pool.max_size` is therefore also the cap on
   concurrent turns per process.
3. **Acquire:** on a `lock_pool` connection, `BEGIN; set_config('lock_timeout', '<n>ms', true);
   SELECT pg_advisory_lock(key); COMMIT`. The session lock outlives the commit; the timeout setting does
   not (verified).
4. **Upsert after locking:** `INSERT INTO conversations (shop_id, thread_id) … ON CONFLICT DO UPDATE SET
   updated_at = now()` on the lock connection (autocommit).
5. **Timeout behaviour:** wait up to 30 s, then `ConversationBusy` → HTTP 409 `conversation_busy` in the
   demo API. The Phase 3 worker will instead leave the inbox row unprocessed and retry. Waiting for a free
   `lock_pool` connection times out after 5 s → `PoolTimeout` → HTTP 503.
6. **Checkpoint writes** happen on main-pool autocommit connections, inside the locked window: the lock
   is taken before `graph.ainvoke` and released after it returns, and `ainvoke` returns only after the
   last checkpoint is written. The lock connection is never used for graph or tool work.
7. **Release:** `pg_advisory_unlock(key)` in `finally`; if that fails the connection is closed. The pool
   also runs `pg_advisory_unlock_all()` whenever a connection is returned, so a missed unlock cannot
   strand a conversation.
8. The API's in-process `app.state.thread_locks` is removed. `GET /chat/history` takes no lock (a
   read-only snapshot).

**Replacement text for §2.3 "Concurrency & Locking Architecture", "Mutual exclusion" bullet:**
> - **Mutual exclusion:** every critical path touching a conversation holds a session-level advisory lock
>   on a connection from a dedicated `lock_pool`:
>   `SELECT pg_advisory_lock(hashtextextended('conv:' || :shop_id || ':' || :thread_id, 0))`, acquired
>   with a 30 s `lock_timeout`. The `conversations` row is upserted after the lock is held and is read and
>   written with ordinary statements. A row lock is not used: it would keep a transaction open across LLM
>   calls and deadlock against the turn's own updates to the row.

Also replace "`SELECT ... FOR UPDATE` on `conversations` or advisory lock" in §1, §4 and §10, and
"`SELECT ... FOR UPDATE`" in the Phase 1 task list, with "session-level advisory lock"; and the diagram
label `SELECT FOR UPDATE on conversations` with `pg_advisory_lock (dedicated pool)`.
`inbox_events … FOR UPDATE SKIP LOCKED` stays as is: short transactions, correct tool for a queue.

---

## 7. Schema fixes for later phases (noted only — not built in Phase 1b)

Phase 1b's migration `0003` creates only `conversations`, the `customer_identities` change, the
`refund_requests` pending index and `verification_failures`. The following are amendments to §7 for the
phase that first creates each object.

| Object | Problem | Replacement |
|---|---|---|
| `handoff_tickets` | `open_ticket` is "an idempotent upsert keyed on `(thread_id, turn_id)`" but no unique key exists; without `shop_id` it also breaks the tenancy rule | add `UNIQUE (shop_id, thread_id, turn_id)` |
| `inbox_events` | `webhook_event_id TEXT NOT NULL UNIQUE` is global: two shops' channels can collide, and the key does not lead with `shop_id`. The worker scans unprocessed rows with no index | replace with `UNIQUE (shop_id, webhook_event_id)`; add `CREATE INDEX inbox_events_unprocessed_idx ON inbox_events (shop_id, thread_id, received_at) WHERE processed_at IS NULL` |
| `kb_chunks` | no `kb_version`, though the FAQ cache key and "per document version" lifetime need it; `ivfflat` built on an empty table has no useful lists and needs re-training, and a shop has a few hundred chunks; `vector(1536)` hard-codes one embedding model while the model is config | add `kb_version TEXT NOT NULL` and `UNIQUE (shop_id, doc_path, kb_version, chunk_no)` with `chunk_no INT NOT NULL`; `CREATE INDEX … USING hnsw (embedding vector_cosine_ops)`; the dimension comes from one setting (`knowledge.embedding_dimensions`, default 1536) read by the migration, and ingest refuses a model whose dimension differs |
| `refund_requests.status` | plan says `pending`, the Phase 1 table says `requested` | Phase 1b renames the value to `pending` (spec 02) |
| `customers.phone` | plan says `NOT NULL`; real sheets have blanks | keep nullable; a customer without a phone can never be verified by phone |
| `pg_trgm` | listed under Phase 0 Docker/migrations | created by the Phase 2 migration that adds `kb_chunks` |

**RRF formula (§2.6).** `pg_trgm` similarity is not BM25. Replacement:
> $$RRF(d) = \frac{w_{vec}}{k + rank_{vec}(d)} + \frac{w_{kw}}{k + rank_{kw}(d)}$$
> where $rank_{kw}$ orders chunks by `pg_trgm` word similarity to the query (trigram keyword match, not
> BM25). $w_{vec}$, $w_{kw}$ and $k$ are `knowledge.hybrid_search.vector_weight`, `keyword_weight` and
> `rrf_k`.

---

## 8. Phone normalization (§2.6 step 2)

**Problem.** "`812345678` → `0812345678`" as a blanket rule would also prefix a zero to numbers that are
not mobiles and would accept garbage. Thai mobiles are `0` + `6/8/9` + 8 digits (10 digits); landlines
are 9 digits (`02` + 7 digits for Bangkok, `0` + `3/4/5/7` + 7 digits elsewhere).

**Decision — exact rules** (`normalize_phone`, spec `phase1b-01`):
1. Convert Thai digits; trim. Allowed characters: digits, space, `-`, `.`, `(`, `)`, and `+` only as the
   first character. Anything else → invalid.
2. Keep the digits `d`.
3. Country code: leading `+` → `d` must start with `66`, which is removed; `0066…` → remove `0066`;
   no `+` and `d` starts with `66` and has 10 or 11 digits → remove `66`. After removing a country code,
   drop one leading `0` if present (the `+66 (0)81…` form), then prefix `0`.
4. Otherwise, if `d` does not start with `0` and has 8 or 9 digits (Excel dropped the zero) → prefix `0`.
5. The result is valid only if it matches a mobile `^0[689]\d{8}$` or a landline `^0[2-57]\d{7}$`.
   So a 9-digit number gains a zero only when it starts with 6, 8 or 9; an 8-digit number only when it
   starts with 2, 3, 4, 5 or 7; everything else is invalid, not guessed.

`phone_last4`: exactly four digits → those digits; otherwise the last four digits of `normalize_phone`,
or invalid.

**Replacement text for §2.6 step 2:**
> 2. **Phone numbers:** strip spaces, hyphens, dots and brackets. `+66` / `0066` / a bare `66` prefix
>    becomes domestic `0`. A missing leading zero (Excel) is restored only for a 9-digit number starting
>    with 6, 8 or 9 (mobile) or an 8-digit number starting with 2, 3, 4, 5 or 7 (landline). The result
>    must be a 10-digit mobile `0[689]xxxxxxxx` or a 9-digit landline `0[2-57]xxxxxxx`; anything else is
>    invalid and is never matched.

---

## 9. Stale version table (§2.1)

**Problem.** "pydantic 2.12.5 — **LangGraph/LangChain are not installed**, so we start from the latest
releases" describes the machine before Phase 0.

**Replacement for the first paragraph of §2.1:**
> This machine: Python 3.13.1, Docker 26.1.4. Installed and pinned in `uv.lock`: pydantic 2.14.3,
> langgraph 1.2.22, langgraph-prebuilt 1.1.2, langgraph-checkpoint-postgres 3.2.1, langchain 1.5.x,
> langchain-core 1.8.0, psycopg 3.3.9. The table below is the PyPI state on 2026-11-14; `uv.lock` is
> authoritative.

Add to "Version-specific decisions":
> 9. Tools that change identity return `Command(update=...)` including their own `ToolMessage`
>    (`runtime.tool_call_id`); tools read state through `ToolRuntime.state`. State keys written by tools
>    need a reducer, because parallel tool calls write the same key in one step; `prepare` replaces such a
>    key with `langgraph.types.Overwrite`.

---

## Smaller corrections found while speccing

| Where | Problem | Replacement |
|---|---|---|
| §6 repo tree | `core/rag/thai_text.py`: the module is used by tools, sync, guardrails, seed and the fake model; nothing about it is RAG | `core/thai_text.py` (top of `core/`, stdlib only) |
| §2.7 `SupportState` | identity fields need reducers (issue 4.6) | `verified_customer_id: Annotated[str \| None, replace_value]`, `verified_order_scopes: Annotated[list[str], add_order_scopes]` |
| §2.4 `agent` row | "system prompt = … + `verified_customer_id`": the model has no use for an internal id | "… + the list of verified order numbers and whether the account is verified (never an internal id)" |
| §7 seed plan | "Test orders testing Buddhist Era dates and Thai numerals": the canonical tables store `TIMESTAMPTZ` and normalized text, so B.E. dates cannot live in them | "Raw sheet-style rows (`seed.golden.GOLDEN_RAW_SHEET_ROWS`) with Thai numerals, B.E. dates and un-normalized order/phone values that must normalize to the golden records" |
| §9 Phase 0 | `thai_text.py` and its 100% coverage are delivered in Phase 1b (spec 01) | move the bullet, or note "delivered in Phase 1b" |
