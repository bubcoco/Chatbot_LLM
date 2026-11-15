"""Identities, conversations, refund index and verification failures.

Several customers per channel user (with a grant scope), one primary per channel user per shop,
at most one pending refund per order, a conversations row per thread, and a table for failed
verification attempts. Every key leads with shop_id.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-16
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


UPGRADE_STATEMENTS = [
    "ALTER TABLE customer_identities DROP CONSTRAINT customer_identities_pkey",
    """
    ALTER TABLE customer_identities
        ADD COLUMN is_primary BOOLEAN NOT NULL DEFAULT TRUE,
        ADD COLUMN grant_scope TEXT NOT NULL DEFAULT 'order' CHECK (grant_scope IN ('order', 'account'))
    """,
    "ALTER TABLE customer_identities ADD PRIMARY KEY (shop_id, channel, channel_user_id, customer_id)",
    """
    CREATE UNIQUE INDEX customer_identities_one_primary_idx
        ON customer_identities (shop_id, channel, channel_user_id) WHERE is_primary
    """,
    "ALTER TABLE refund_requests DROP CONSTRAINT refund_requests_status_check",
    "UPDATE refund_requests SET status = 'pending' WHERE status = 'requested'",
    "ALTER TABLE refund_requests ALTER COLUMN status SET DEFAULT 'pending'",
    """
    ALTER TABLE refund_requests
        ADD CONSTRAINT refund_requests_status_check CHECK (status IN ('pending', 'approved', 'rejected'))
    """,
    "CREATE UNIQUE INDEX uq_pending_refund ON refund_requests (shop_id, order_id) WHERE status = 'pending'",
    """
    CREATE TABLE conversations (
        shop_id                 TEXT NOT NULL,
        thread_id               TEXT NOT NULL,
        mode                    TEXT NOT NULL DEFAULT 'bot' CHECK (mode IN ('bot', 'pending', 'human')),
        current_turn_id         TEXT,
        last_extracted_turn_id  TEXT,
        created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY (shop_id, thread_id)
    )
    """,
    """
    CREATE TABLE verification_failures (
        shop_id          TEXT NOT NULL,
        failure_id       BIGINT GENERATED ALWAYS AS IDENTITY,
        channel          TEXT NOT NULL CHECK (channel IN ('line', 'web')),
        channel_user_id  TEXT NOT NULL,
        order_no         TEXT,
        created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY (shop_id, failure_id)
    )
    """,
    """
    CREATE INDEX verification_failures_user_idx
        ON verification_failures (shop_id, channel, channel_user_id, created_at)
    """,
    """
    CREATE INDEX verification_failures_order_idx
        ON verification_failures (shop_id, order_no, created_at) WHERE order_no IS NOT NULL
    """,
]

DOWNGRADE_STATEMENTS = [
    "DROP TABLE IF EXISTS verification_failures",
    "DROP TABLE IF EXISTS conversations",
    "DROP INDEX IF EXISTS uq_pending_refund",
    "ALTER TABLE refund_requests DROP CONSTRAINT refund_requests_status_check",
    "UPDATE refund_requests SET status = 'requested' WHERE status = 'pending'",
    "ALTER TABLE refund_requests ALTER COLUMN status SET DEFAULT 'requested'",
    """
    ALTER TABLE refund_requests
        ADD CONSTRAINT refund_requests_status_check CHECK (status IN ('requested', 'approved', 'rejected'))
    """,
    "DROP INDEX IF EXISTS customer_identities_one_primary_idx",
    "DELETE FROM customer_identities WHERE NOT is_primary",
    "ALTER TABLE customer_identities DROP CONSTRAINT customer_identities_pkey",
    "ALTER TABLE customer_identities DROP COLUMN grant_scope, DROP COLUMN is_primary",
    "ALTER TABLE customer_identities ADD PRIMARY KEY (shop_id, channel, channel_user_id)",
]


def upgrade() -> None:
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE_STATEMENTS:
        op.execute(statement)
