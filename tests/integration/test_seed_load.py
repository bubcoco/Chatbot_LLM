"""DB tests for the demo seed. Skipped when Postgres is not reachable (database_url fixture)."""

import uuid

import psycopg

from seed.load import seed_database


def test_reseed_is_idempotent_and_leaves_other_shops_alone(database_url):
    extra_shop = f"t-seed-{uuid.uuid4().hex[:8]}"
    with psycopg.connect(database_url) as conn:
        conn.execute(
            "INSERT INTO customers (shop_id, customer_id, full_name) VALUES (%s, 'C-9999', 'Extra')",
            (extra_shop,),
        )
    try:
        first = seed_database(database_url)
        second = seed_database(database_url)
        assert first == second

        with psycopg.connect(database_url) as conn:
            (demo_orders,) = conn.execute(
                "SELECT count(*) FROM orders WHERE shop_id = 'baan-bai-cha'"
            ).fetchone()
            assert demo_orders == 200
            (extra_customers,) = conn.execute(
                "SELECT count(*) FROM customers WHERE shop_id = %s", (extra_shop,)
            ).fetchone()
            assert extra_customers == 1
    finally:
        with psycopg.connect(database_url) as conn:
            conn.execute("DELETE FROM customers WHERE shop_id = %s", (extra_shop,))


def test_demo_order_bc_1042_shipment_tracking_after_seed(database_url):
    seed_database(database_url)
    with psycopg.connect(database_url) as conn:
        (tracking_no,) = conn.execute(
            "SELECT s.tracking_no FROM orders o "
            "JOIN shipments s USING (shop_id, order_id) "
            "WHERE o.shop_id = 'baan-bai-cha' AND o.order_no = 'BC-1042'"
        ).fetchone()
    assert tracking_no == "KEX26111042TH"
