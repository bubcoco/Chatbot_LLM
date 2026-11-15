# Phase 1 · Spec 02 — Business schema migration

**Suggested implementer:** `quick-implementer` (DDL below is verbatim; no decisions. Escalate to `implementer` if anything does not apply cleanly.)
**Depends on:** 01 · **Blocks:** 03, 04

## Goal
Create the seven business tables from PLAN.md §7 as Alembic migration `0002`, with `shop_id` leading every primary key, unique key, foreign key and index, so that a row can never reference another shop's row.

## Files
| Path | Action | Purpose |
|---|---|---|
| `db/migrations/versions/0002_business_tables.py` | create | DDL below via `op.execute` (plain SQL, same style as `0001`) |
| `tests/integration/test_schema.py` | create | constraint tests |

## Interfaces
Header: `revision = "0002"`, `down_revision = "0001"`. `upgrade()` executes the statements below in order. `downgrade()` drops the tables in reverse order (`DROP TABLE IF EXISTS ...`).

```sql
CREATE TABLE customers (
    shop_id      TEXT NOT NULL,
    customer_id  TEXT NOT NULL,
    full_name    TEXT NOT NULL,
    phone        TEXT,
    email        TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (shop_id, customer_id)
);
CREATE INDEX customers_shop_phone_idx ON customers (shop_id, phone);

CREATE TABLE customer_identities (
    shop_id          TEXT NOT NULL,
    channel          TEXT NOT NULL CHECK (channel IN ('line', 'web')),
    channel_user_id  TEXT NOT NULL,
    customer_id      TEXT NOT NULL,
    verified_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (shop_id, channel, channel_user_id),
    FOREIGN KEY (shop_id, customer_id) REFERENCES customers (shop_id, customer_id) ON DELETE CASCADE
);

CREATE TABLE products (
    shop_id      TEXT NOT NULL,
    sku          TEXT NOT NULL,
    name_th      TEXT NOT NULL,
    name_en      TEXT NOT NULL,
    description  TEXT NOT NULL DEFAULT '',
    price_thb    NUMERIC(12,2) NOT NULL CHECK (price_thb >= 0),
    stock_qty    INTEGER NOT NULL CHECK (stock_qty >= 0),
    is_active    BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (shop_id, sku)
);

CREATE TABLE orders (
    shop_id           TEXT NOT NULL,
    order_id          TEXT NOT NULL,
    order_no          TEXT NOT NULL,
    customer_id       TEXT NOT NULL,
    status            TEXT NOT NULL CHECK (status IN
        ('pending_payment','paid','packed','shipped','delivered','cancelled','returned')),
    subtotal_thb      NUMERIC(12,2) NOT NULL CHECK (subtotal_thb >= 0),
    shipping_fee_thb  NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (shipping_fee_thb >= 0),
    discount_thb      NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (discount_thb >= 0),
    total_thb         NUMERIC(12,2) NOT NULL CHECK (total_thb >= 0),
    payment_method    TEXT NOT NULL CHECK (payment_method IN ('promptpay','bank_transfer','cod','card')),
    payment_status    TEXT NOT NULL CHECK (payment_status IN ('pending','paid','refunded')),
    ordered_at        TIMESTAMPTZ NOT NULL,
    shipping_address  JSONB NOT NULL DEFAULT '{}'::jsonb,
    synced_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (shop_id, order_id),
    UNIQUE (shop_id, order_no),
    FOREIGN KEY (shop_id, customer_id) REFERENCES customers (shop_id, customer_id)
);
CREATE INDEX orders_shop_customer_idx ON orders (shop_id, customer_id, ordered_at DESC);

CREATE TABLE order_items (
    shop_id         TEXT NOT NULL,
    order_id        TEXT NOT NULL,
    line_no         INTEGER NOT NULL,
    sku             TEXT NOT NULL,
    qty             INTEGER NOT NULL CHECK (qty > 0),
    unit_price_thb  NUMERIC(12,2) NOT NULL CHECK (unit_price_thb >= 0),
    PRIMARY KEY (shop_id, order_id, line_no),
    FOREIGN KEY (shop_id, order_id) REFERENCES orders (shop_id, order_id) ON DELETE CASCADE,
    FOREIGN KEY (shop_id, sku) REFERENCES products (shop_id, sku)
);

CREATE TABLE shipments (
    shop_id                  TEXT NOT NULL,
    shipment_id              TEXT NOT NULL,
    order_id                 TEXT NOT NULL,
    carrier                  TEXT NOT NULL,
    tracking_no              TEXT NOT NULL,
    status                   TEXT NOT NULL CHECK (status IN
        ('label_created','in_transit','out_for_delivery','delivered','returned')),
    shipped_at               TIMESTAMPTZ,
    estimated_delivery_date  DATE,
    delivered_at             TIMESTAMPTZ,
    synced_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (shop_id, shipment_id),
    FOREIGN KEY (shop_id, order_id) REFERENCES orders (shop_id, order_id) ON DELETE CASCADE
);
CREATE INDEX shipments_shop_order_idx ON shipments (shop_id, order_id);

CREATE TABLE refund_requests (
    shop_id     TEXT NOT NULL,
    request_id  TEXT NOT NULL,
    order_id    TEXT NOT NULL,
    reason      TEXT NOT NULL,
    amount_thb  NUMERIC(12,2) NOT NULL CHECK (amount_thb >= 0),
    status      TEXT NOT NULL DEFAULT 'requested' CHECK (status IN ('requested','approved','rejected')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (shop_id, request_id),
    FOREIGN KEY (shop_id, order_id) REFERENCES orders (shop_id, order_id) ON DELETE CASCADE
);
```

## Behaviour
1. Migration is transactional and idempotent through Alembic's version table (running `supportkit migrate` twice changes nothing the second time).
2. No `shops` table: shops are defined by config (Phase 2). No system tables (`conversations`, `inbox_events`, ...) — they arrive with the phases that use them.
3. No RLS (Phase 6).

## Tests
`tests/integration/test_schema.py` — sync `psycopg` tests using the `database_url` fixture from `tests/conftest.py` (skips when Postgres is unreachable). Each test uses shop ids `t-schema-a-<8 hex>` / `t-schema-b-<8 hex>` and deletes its rows in a `finally` (orders before customers; products last).

| # | Input | Expected |
|---|---|---|
| 1 | Query `information_schema.tables` | all 7 table names present |
| 2 | Query `information_schema.columns` for the 7 tables | each has `shop_id` with `is_nullable = 'NO'` |
| 3 | Insert customer `C-1` in shop A only, then an order in shop **B** with `customer_id='C-1'` | `psycopg.errors.ForeignKeyViolation` |
| 4 | Insert customer `C-1` in both shops and an order `order_no='BC-1042'` in each shop | both inserts succeed (order numbers collide across shops) |
| 5 | Insert a second order with `order_no='BC-1042'` in shop A | `psycopg.errors.UniqueViolation` |
| 6 | Insert an order with `status='lost'` | `psycopg.errors.CheckViolation` |
| 7 | Insert a shipment in shop B pointing at shop A's `order_id` | `ForeignKeyViolation` |

## Acceptance criteria
```powershell
docker compose up -d db
.\.venv\Scripts\supportkit.exe migrate        # "alembic: upgraded to head", exit 0; second run also exit 0
.\.venv\Scripts\supportkit.exe db-status      # lists customers, customer_identities, products, orders, order_items, shipments, refund_requests
.\.venv\Scripts\ruff.exe check src tests db
$env:LANGGRAPH_STRICT_MSGPACK='true'; .\.venv\Scripts\python.exe -m pytest -q    # all pass (7 new tests run, not skipped)
```

## Out of scope
- Editing migration `0001`, `env.py`, or `cli.py`.
- Seed data, repositories, ORM models.
- Never run `alembic downgrade` against the dev database, drop the database, or delete the Docker volume.
