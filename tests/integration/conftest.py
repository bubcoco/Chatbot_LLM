"""Shared integration fixtures. Fixtures only ever touch rows under their own random t-* shop ids."""

import uuid
from dataclasses import dataclass

import pytest


@dataclass(frozen=True)
class TwoShops:
    shop_a: str
    shop_b: str


_ORDER_SQL = """
INSERT INTO orders (
    shop_id, order_id, order_no, customer_id, status, subtotal_thb, total_thb,
    payment_method, payment_status, ordered_at, synced_at
) VALUES (%s, %s, %s, %s, %s, %s, %s, 'promptpay', %s, %s, %s)
"""

_SHIPMENT_SQL = """
INSERT INTO shipments (
    shop_id, shipment_id, order_id, carrier, tracking_no, status,
    shipped_at, estimated_delivery_date
) VALUES (%s, %s, %s, 'Kerry Express', %s, %s, %s, %s)
"""


@pytest.fixture
async def two_shops(pool):
    shop_a = f"t-a-{uuid.uuid4().hex[:8]}"
    shop_b = f"t-b-{uuid.uuid4().hex[:8]}"
    shops = [shop_a, shop_b]
    synced = "2026-11-15 12:00+07"
    async with pool.connection() as conn:
        try:
            for shop, cust in ((shop_a, "C-1"), (shop_a, "C-2"), (shop_b, "C-1")):
                await conn.execute(
                    "INSERT INTO customers (shop_id, customer_id, full_name, phone) "
                    "VALUES (%s, %s, %s, %s)",
                    (shop, cust, f"Name {cust}", "0800000000"),
                )
            for shop in shops:
                await conn.execute(
                    "INSERT INTO products (shop_id, sku, name_th, name_en, price_thb, stock_qty) "
                    "VALUES (%s, 'SKU-1', 'สินค้า', 'Item', 100, 10)",
                    (shop,),
                )
            orders = [
                (shop_a, "o-1042", "BC-1042", "C-1", "shipped", 1230, "paid", "2026-11-12 10:15+07"),
                (shop_a, "o-1050", "BC-1050", "C-2", "delivered", 1830, "paid", "2026-11-01 09:00+07"),
                (shop_a, "o-1043", "BC-1043", "C-1", "pending_payment", 500, "pending", "2026-11-14 09:00+07"),
                (shop_b, "o-1042", "BC-1042", "C-1", "delivered", 3200, "paid", "2026-10-20 09:00+07"),
            ]
            for shop, oid, no, cust, status, total, pay, ordered in orders:
                await conn.execute(
                    _ORDER_SQL, (shop, oid, no, cust, status, total, total, pay, ordered, synced)
                )
            await conn.execute(
                "INSERT INTO order_items (shop_id, order_id, line_no, sku, qty, unit_price_thb) "
                "VALUES (%s, 'o-1042', 1, 'SKU-1', 3, 100)",
                (shop_a,),
            )
            shipments = [
                (shop_a, "s-1042", "o-1042", "TRACK-A-1042", "in_transit",
                 "2026-11-13 14:00+07", "2026-11-16"),
                (shop_a, "s-1050", "o-1050", "TRACK-A-1050", "delivered",
                 "2026-11-02 14:00+07", "2026-11-04"),
                (shop_b, "s-1042", "o-1042", "TRACK-B-1042", "delivered",
                 "2026-10-21 14:00+07", "2026-10-23"),
            ]
            for row in shipments:
                await conn.execute(_SHIPMENT_SQL, row)
            yield TwoShops(shop_a, shop_b)
        finally:
            for table in ("shipments", "order_items", "orders", "products", "customers"):
                await conn.execute(f"DELETE FROM {table} WHERE shop_id = ANY(%s)", (shops,))
