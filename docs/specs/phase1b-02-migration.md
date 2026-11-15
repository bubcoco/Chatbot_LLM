# Phase 1b · Spec 02 — Migration `0003`: identities, conversations, refund index, verification failures

**Suggested implementer:** `quick-implementer` (DDL is given verbatim)
**Depends on:** — · **Blocks:** 03, 04, 06, 07 · **Parallel with:** 01

## Goal
One Alembic revision that makes the schema match what Phase 1b code needs: several customers per channel
user with a grant scope, a `conversations` row per thread, at most one pending refund per order, and a
table for failed verification attempts. Nothing for later phases (`inbox_events`, `handoff_tickets`,
`kb_chunks`, `faq_cache`, `pg_trgm`) is created.

## Files
| Path | Action | Purpose |
|---|---|---|
| `db/migrations/versions/0003_identity_conversations.py` | create | revision `0003`, `down_revision = "0002"` |
| `tests/integration/test_schema.py` | modify | add tables to `TABLES`, add the tests below, extend fixture cleanup |

## Interfaces
Same file layout as `0002` (`UPGRADE_STATEMENTS` list, one `op.execute` per statement).

`UPGRADE_STATEMENTS`, in this order:
```sql
ALTER TABLE customer_identities DROP CONSTRAINT customer_identities_pkey;
ALTER TABLE customer_identities
    ADD COLUMN is_primary BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN grant_scope TEXT NOT NULL DEFAULT 'order' CHECK (grant_scope IN ('order', 'account'));
ALTER TABLE customer_identities ADD PRIMARY KEY (shop_id, channel, channel_user_id, customer_id);
CREATE UNIQUE INDEX customer_identities_one_primary_idx
    ON customer_identities (shop_id, channel, channel_user_id) WHERE is_primary;

ALTER TABLE refund_requests DROP CONSTRAINT refund_requests_status_check;
UPDATE refund_requests SET status = 'pending' WHERE status = 'requested';
ALTER TABLE refund_requests ALTER COLUMN status SET DEFAULT 'pending';
ALTER TABLE refund_requests
    ADD CONSTRAINT refund_requests_status_check CHECK (status IN ('pending', 'approved', 'rejected'));
CREATE UNIQUE INDEX uq_pending_refund ON refund_requests (shop_id, order_id) WHERE status = 'pending';

CREATE TABLE conversations (
    shop_id                 TEXT NOT NULL,
    thread_id               TEXT NOT NULL,
    mode                    TEXT NOT NULL DEFAULT 'bot' CHECK (mode IN ('bot', 'pending', 'human')),
    current_turn_id         TEXT,
    last_extracted_turn_id  TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (shop_id, thread_id)
);

CREATE TABLE verification_failures (
    shop_id          TEXT NOT NULL,
    failure_id       BIGINT GENERATED ALWAYS AS IDENTITY,
    channel          TEXT NOT NULL CHECK (channel IN ('line', 'web')),
    channel_user_id  TEXT NOT NULL,
    order_no         TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (shop_id, failure_id)
);
CREATE INDEX verification_failures_user_idx
    ON verification_failures (shop_id, channel, channel_user_id, created_at);
CREATE INDEX verification_failures_order_idx
    ON verification_failures (shop_id, order_no, created_at) WHERE order_no IS NOT NULL;
```
`verification_failures.order_no` is the normalized target order number, or `NULL` when the input was
malformed. The table never stores a phone number or a customer id.

`downgrade()`, in this order:
```sql
DROP TABLE IF EXISTS verification_failures;
DROP TABLE IF EXISTS conversations;
DROP INDEX IF EXISTS uq_pending_refund;
ALTER TABLE refund_requests DROP CONSTRAINT refund_requests_status_check;
UPDATE refund_requests SET status = 'requested' WHERE status = 'pending';
ALTER TABLE refund_requests ALTER COLUMN status SET DEFAULT 'requested';
ALTER TABLE refund_requests
    ADD CONSTRAINT refund_requests_status_check CHECK (status IN ('requested', 'approved', 'rejected'));
DROP INDEX IF EXISTS customer_identities_one_primary_idx;
DELETE FROM customer_identities WHERE NOT is_primary;
ALTER TABLE customer_identities DROP CONSTRAINT customer_identities_pkey;
ALTER TABLE customer_identities DROP COLUMN grant_scope, DROP COLUMN is_primary;
ALTER TABLE customer_identities ADD PRIMARY KEY (shop_id, channel, channel_user_id);
```

## Behaviour
1. The revision is applied by the existing `supportkit migrate`; no CLI change.
2. No code writes `refund_requests` or `customer_identities` before this phase, so the `UPDATE` and the
   re-keying operate on empty tables in every known environment. Do not add de-duplication logic.
3. Every new table has `shop_id TEXT NOT NULL` and a primary key that leads with `shop_id`.
4. `conversations` and `verification_failures` have no foreign keys (a conversation exists before any
   customer is known; a failure may name an order that does not exist).

## Tests
`tests/integration/test_schema.py`:
- `TABLES` gains `"conversations"` and `"verification_failures"` (the two existing table tests then cover them).
- Fixture cleanup: before deleting `customers`, also
  `DELETE FROM refund_requests / conversations / verification_failures WHERE shop_id = ANY(shops)`
  (`customer_identities` and `refund_requests` rows also go with their parents via `ON DELETE CASCADE`).

Add (each in its own test; `psycopg.errors` class in brackets):
| # | Steps | Expected |
|---|---|---|
| 1 | customers `C-1`, `C-2` in shop A; insert identities `(A,'web','u1','C-1')` default columns, then `(A,'web','u1','C-2', is_primary=false)` | both succeed; row 1 has `is_primary` true and `grant_scope` `'order'` |
| 2 | as 1, but the second row leaves `is_primary` at its default | `UniqueViolation` |
| 3 | insert `(A,'web','u1','C-1')` twice | `UniqueViolation` |
| 4 | identity with `grant_scope='admin'` | `CheckViolation` |
| 5 | identities `(A,'web','u1','C-1')` and `(B,'web','u1','C-1')` (customer `C-1` exists in both shops) | both succeed (primary is per shop) |
| 6 | identity in shop A for a customer that exists only in shop B | `ForeignKeyViolation` |
| 7 | order `o-1` in shop A; insert a refund without `status` | row has `status = 'pending'` |
| 8 | second refund for `o-1` with default status | `UniqueViolation` |
| 9 | set the first refund to `'approved'`, insert another pending one for `o-1` | succeeds |
| 10 | refund with `status='requested'` | `CheckViolation` |
| 11 | pending refunds for `o-1` in shop A and `o-1` in shop B | both succeed |
| 12 | `INSERT INTO conversations (shop_id, thread_id)` | `mode = 'bot'`, `current_turn_id IS NULL`; a second identical insert → `UniqueViolation`; same `thread_id` in shop B succeeds |
| 13 | conversation with `mode='paused'` | `CheckViolation` |
| 14 | `INSERT INTO verification_failures (shop_id, channel, channel_user_id)` | succeeds with `order_no IS NULL`; `channel='sms'` → `CheckViolation` |
| 15 | columns of `verification_failures` from `information_schema.columns` | exactly `shop_id, failure_id, channel, channel_user_id, order_no, created_at` (no phone, no customer id) |

## Acceptance
```powershell
.\.venv\Scripts\supportkit.exe migrate          # "alembic: upgraded to head"
.\.venv\Scripts\supportkit.exe db-status        # lists conversations and verification_failures
.\.venv\Scripts\ruff.exe check src tests db seed evals ui
$env:LANGGRAPH_STRICT_MSGPACK='true'; .\.venv\Scripts\python.exe -m pytest -q     # whole suite green, none skipped
.\.venv\Scripts\supportkit.exe eval --require-all                                # still 10/10
```
Downgrade round trip, once by hand on the dev database (there is no CLI command for it; report the output):
```powershell
.\.venv\Scripts\python.exe -c "from alembic import command; from alembic.config import Config; from supportkit.settings import get_settings; c=Config('alembic.ini'); c.set_main_option('script_location','db/migrations'); c.set_main_option('sqlalchemy.url', get_settings().sqlalchemy_url); command.downgrade(c,'0002'); command.upgrade(c,'head')"
```
Both steps finish without error and the test suite is still green afterwards.

## Out of scope
- `inbox_events`, `handoff_tickets`, `kb_chunks`, `faq_cache`, `usage_events`, `audit_log`, `pg_trgm` (later phases; see amendments issue 7).
- Any change to `0001`/`0002`, to `seed/` (spec 03) or to `src/`.
- Making `customers.phone` `NOT NULL`.
