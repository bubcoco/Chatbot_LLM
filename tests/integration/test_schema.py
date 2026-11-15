"""Phase 1 spec 02: business schema constraints on real Postgres.

Each test uses its own pair of shop ids and deletes its rows in a finally block.
"""

import uuid

import psycopg
import pytest

TABLES = [
    "customers",
    "customer_identities",
    "products",
    "orders",
    "order_items",
    "shipments",
    "refund_requests",
    "conversations",
    "verification_failures",
]


@pytest.fixture
def ctx(database_url):
    suffix = uuid.uuid4().hex[:8]
    shop_a = f"t-schema-a-{suffix}"
    shop_b = f"t-schema-b-{suffix}"
    conn = psycopg.connect(database_url, autocommit=True)
    try:
        yield conn, shop_a, shop_b
    finally:
        try:
            shops = [shop_a, shop_b]
            conn.execute("DELETE FROM orders WHERE shop_id = ANY(%s)", (shops,))
            conn.execute("DELETE FROM refund_requests WHERE shop_id = ANY(%s)", (shops,))
            conn.execute("DELETE FROM conversations WHERE shop_id = ANY(%s)", (shops,))
            conn.execute("DELETE FROM verification_failures WHERE shop_id = ANY(%s)", (shops,))
            conn.execute("DELETE FROM customers WHERE shop_id = ANY(%s)", (shops,))
            conn.execute("DELETE FROM products WHERE shop_id = ANY(%s)", (shops,))
        finally:
            conn.close()


def _customer(conn, shop, customer_id="C-1"):
    conn.execute(
        "INSERT INTO customers (shop_id, customer_id, full_name) VALUES (%s, %s, %s)",
        (shop, customer_id, "Test Customer"),
    )


def _order(conn, shop, order_id, order_no, customer_id="C-1", status="pending_payment"):
    conn.execute(
        """
        INSERT INTO orders (
            shop_id, order_id, order_no, customer_id, status,
            subtotal_thb, total_thb, payment_method, payment_status, ordered_at
        ) VALUES (%s, %s, %s, %s, %s, 100, 100, 'cod', 'pending', now())
        """,
        (shop, order_id, order_no, customer_id, status),
    )


def test_all_business_tables_exist(ctx):
    conn, _, _ = ctx
    rows = conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = ANY(%s)",
        (TABLES,),
    ).fetchall()
    assert {r[0] for r in rows} == set(TABLES)


def test_shop_id_is_not_nullable_on_every_table(ctx):
    conn, _, _ = ctx
    rows = conn.execute(
        "SELECT table_name, is_nullable FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = ANY(%s) AND column_name = 'shop_id'",
        (TABLES,),
    ).fetchall()
    assert {r[0]: r[1] for r in rows} == {t: "NO" for t in TABLES}


def test_order_cannot_reference_another_shops_customer(ctx):
    conn, shop_a, shop_b = ctx
    _customer(conn, shop_a, "C-1")
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        _order(conn, shop_b, "O-1", "BC-0001", customer_id="C-1")


def test_order_numbers_may_collide_across_shops(ctx):
    conn, shop_a, shop_b = ctx
    _customer(conn, shop_a, "C-1")
    _customer(conn, shop_b, "C-1")
    _order(conn, shop_a, "O-1", "BC-1042")
    _order(conn, shop_b, "O-1", "BC-1042")
    count = conn.execute(
        "SELECT count(*) FROM orders WHERE order_no = 'BC-1042' AND shop_id = ANY(%s)",
        ([shop_a, shop_b],),
    ).fetchone()[0]
    assert count == 2


def test_order_no_is_unique_within_a_shop(ctx):
    conn, shop_a, _ = ctx
    _customer(conn, shop_a, "C-1")
    _order(conn, shop_a, "O-1", "BC-1042")
    with pytest.raises(psycopg.errors.UniqueViolation):
        _order(conn, shop_a, "O-2", "BC-1042")


def test_order_status_is_checked(ctx):
    conn, shop_a, _ = ctx
    _customer(conn, shop_a, "C-1")
    with pytest.raises(psycopg.errors.CheckViolation):
        _order(conn, shop_a, "O-1", "BC-1043", status="lost")


def test_shipment_cannot_reference_another_shops_order(ctx):
    conn, shop_a, shop_b = ctx
    _customer(conn, shop_a, "C-1")
    _order(conn, shop_a, "O-1", "BC-1044")
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        conn.execute(
            """
            INSERT INTO shipments (shop_id, shipment_id, order_id, carrier, tracking_no, status)
            VALUES (%s, 'S-1', 'O-1', 'kerry', 'TH0001', 'label_created')
            """,
            (shop_b,),
        )


def _identity(conn, shop, customer_id, channel_user_id="u1", **extra):
    columns = ["shop_id", "channel", "channel_user_id", "customer_id", *extra]
    placeholders = ", ".join(["%s"] * len(columns))
    conn.execute(
        f"INSERT INTO customer_identities ({', '.join(columns)}) VALUES ({placeholders})",
        (shop, "web", channel_user_id, customer_id, *extra.values()),
    )


def _refund(conn, shop, request_id, order_id, status=None):
    columns = ["shop_id", "request_id", "order_id", "reason", "amount_thb"]
    values = [shop, request_id, order_id, "damaged", 100]
    if status is not None:
        columns.append("status")
        values.append(status)
    placeholders = ", ".join(["%s"] * len(columns))
    conn.execute(
        f"INSERT INTO refund_requests ({', '.join(columns)}) VALUES ({placeholders})",
        values,
    )


def test_second_identity_for_same_channel_user_is_allowed_when_not_primary(ctx):
    conn, shop_a, _ = ctx
    _customer(conn, shop_a, "C-1")
    _customer(conn, shop_a, "C-2")
    _identity(conn, shop_a, "C-1")
    _identity(conn, shop_a, "C-2", is_primary=False)
    is_primary, grant_scope = conn.execute(
        "SELECT is_primary, grant_scope FROM customer_identities "
        "WHERE shop_id = %s AND customer_id = 'C-1'",
        (shop_a,),
    ).fetchone()
    assert is_primary is True
    assert grant_scope == "order"


def test_only_one_primary_identity_per_channel_user(ctx):
    conn, shop_a, _ = ctx
    _customer(conn, shop_a, "C-1")
    _customer(conn, shop_a, "C-2")
    _identity(conn, shop_a, "C-1")
    with pytest.raises(psycopg.errors.UniqueViolation):
        _identity(conn, shop_a, "C-2")


def test_same_customer_cannot_be_linked_twice_to_one_channel_user(ctx):
    conn, shop_a, _ = ctx
    _customer(conn, shop_a, "C-1")
    _identity(conn, shop_a, "C-1")
    with pytest.raises(psycopg.errors.UniqueViolation):
        _identity(conn, shop_a, "C-1")


def test_grant_scope_is_checked(ctx):
    conn, shop_a, _ = ctx
    _customer(conn, shop_a, "C-1")
    with pytest.raises(psycopg.errors.CheckViolation):
        _identity(conn, shop_a, "C-1", grant_scope="admin")


def test_primary_identity_is_per_shop(ctx):
    conn, shop_a, shop_b = ctx
    _customer(conn, shop_a, "C-1")
    _customer(conn, shop_b, "C-1")
    _identity(conn, shop_a, "C-1")
    _identity(conn, shop_b, "C-1")


def test_identity_cannot_reference_another_shops_customer(ctx):
    conn, shop_a, shop_b = ctx
    _customer(conn, shop_b, "C-2")
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        _identity(conn, shop_a, "C-2")


def test_refund_defaults_to_pending(ctx):
    conn, shop_a, _ = ctx
    _customer(conn, shop_a, "C-1")
    _order(conn, shop_a, "o-1", "BC-3001")
    _refund(conn, shop_a, "R-1", "o-1")
    status = conn.execute(
        "SELECT status FROM refund_requests WHERE shop_id = %s AND request_id = 'R-1'",
        (shop_a,),
    ).fetchone()[0]
    assert status == "pending"


def test_only_one_pending_refund_per_order(ctx):
    conn, shop_a, _ = ctx
    _customer(conn, shop_a, "C-1")
    _order(conn, shop_a, "o-1", "BC-3002")
    _refund(conn, shop_a, "R-1", "o-1")
    with pytest.raises(psycopg.errors.UniqueViolation):
        _refund(conn, shop_a, "R-2", "o-1")


def test_new_pending_refund_allowed_after_previous_is_decided(ctx):
    conn, shop_a, _ = ctx
    _customer(conn, shop_a, "C-1")
    _order(conn, shop_a, "o-1", "BC-3003")
    _refund(conn, shop_a, "R-1", "o-1")
    conn.execute(
        "UPDATE refund_requests SET status = 'approved' WHERE shop_id = %s AND request_id = 'R-1'",
        (shop_a,),
    )
    _refund(conn, shop_a, "R-2", "o-1")


def test_refund_status_rejects_legacy_requested_value(ctx):
    conn, shop_a, _ = ctx
    _customer(conn, shop_a, "C-1")
    _order(conn, shop_a, "o-1", "BC-3004")
    with pytest.raises(psycopg.errors.CheckViolation):
        _refund(conn, shop_a, "R-1", "o-1", status="requested")


def test_pending_refund_uniqueness_is_per_shop(ctx):
    conn, shop_a, shop_b = ctx
    _customer(conn, shop_a, "C-1")
    _customer(conn, shop_b, "C-1")
    _order(conn, shop_a, "o-1", "BC-3005")
    _order(conn, shop_b, "o-1", "BC-3006")
    _refund(conn, shop_a, "R-1", "o-1")
    _refund(conn, shop_b, "R-1", "o-1")


def test_conversation_defaults_and_uniqueness_per_shop(ctx):
    conn, shop_a, shop_b = ctx
    conn.execute(
        "INSERT INTO conversations (shop_id, thread_id) VALUES (%s, 'T-1')",
        (shop_a,),
    )
    mode, current_turn_id = conn.execute(
        "SELECT mode, current_turn_id FROM conversations WHERE shop_id = %s AND thread_id = 'T-1'",
        (shop_a,),
    ).fetchone()
    assert mode == "bot"
    assert current_turn_id is None
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute(
            "INSERT INTO conversations (shop_id, thread_id) VALUES (%s, 'T-1')",
            (shop_a,),
        )
    conn.execute(
        "INSERT INTO conversations (shop_id, thread_id) VALUES (%s, 'T-1')",
        (shop_b,),
    )


def test_conversation_mode_is_checked(ctx):
    conn, shop_a, _ = ctx
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            "INSERT INTO conversations (shop_id, thread_id, mode) VALUES (%s, 'T-2', 'paused')",
            (shop_a,),
        )


def test_verification_failure_allows_null_order_no(ctx):
    conn, shop_a, _ = ctx
    conn.execute(
        "INSERT INTO verification_failures (shop_id, channel, channel_user_id) "
        "VALUES (%s, 'line', 'u1')",
        (shop_a,),
    )
    order_no = conn.execute(
        "SELECT order_no FROM verification_failures WHERE shop_id = %s",
        (shop_a,),
    ).fetchone()[0]
    assert order_no is None


def test_verification_failure_channel_is_checked(ctx):
    conn, shop_a, _ = ctx
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            "INSERT INTO verification_failures (shop_id, channel, channel_user_id) "
            "VALUES (%s, 'sms', 'u1')",
            (shop_a,),
        )


def test_verification_failures_store_no_phone_or_customer_id(ctx):
    conn, _, _ = ctx
    columns = [
        r[0]
        for r in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'verification_failures' "
            "ORDER BY ordinal_position",
        ).fetchall()
    ]
    assert columns == [
        "shop_id",
        "failure_id",
        "channel",
        "channel_user_id",
        "order_no",
        "created_at",
    ]
