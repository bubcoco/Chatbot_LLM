"""Business tables: customers, customer_identities, products, orders, order_items, shipments, refund_requests.

Every primary key, unique key, foreign key and index leads with shop_id so a row can
never reference another shop's row.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-15
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


UPGRADE_STATEMENTS = [
    """
    CREATE TABLE customers (
        shop_id      TEXT NOT NULL,
        customer_id  TEXT NOT NULL,
        full_name    TEXT NOT NULL,
        phone        TEXT,
        email        TEXT,
        created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY (shop_id, customer_id)
    )
    """,
    "CREATE INDEX customers_shop_phone_idx ON customers (shop_id, phone)",
    """
    CREATE TABLE customer_identities (
        shop_id          TEXT NOT NULL,
        channel          TEXT NOT NULL CHECK (channel IN ('line', 'web')),
        channel_user_id  TEXT NOT NULL,
        customer_id      TEXT NOT NULL,
        verified_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY (shop_id, channel, channel_user_id),
        FOREIGN KEY (shop_id, customer_id) REFERENCES customers (shop_id, customer_id) ON DELETE CASCADE
    )
    """,
    """
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
    )
    """,
    """
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
    )
    """,
    "CREATE INDEX orders_shop_customer_idx ON orders (shop_id, customer_id, ordered_at DESC)",
    """
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
    )
    """,
    """
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
    )
    """,
    "CREATE INDEX shipments_shop_order_idx ON shipments (shop_id, order_id)",
    """
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
    )
    """,
]

# Reverse creation order so dependent tables go first.
DOWNGRADE_TABLES = [
    "refund_requests",
    "shipments",
    "order_items",
    "orders",
    "products",
    "customer_identities",
    "customers",
]


def upgrade() -> None:
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for table in DOWNGRADE_TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table}")
