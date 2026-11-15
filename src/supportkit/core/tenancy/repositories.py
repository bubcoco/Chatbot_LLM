"""Tenant-scoped SQL. Every function filters on shop_id taken from the TenantContext/argument."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

import psycopg
from psycopg.rows import dict_row

from supportkit.core.tenancy.context import TenantContext


@dataclass(frozen=True, slots=True)
class ShipmentSummary:
    carrier: str
    tracking_no: str
    status: str
    shipped_at: datetime | None
    estimated_delivery_date: date | None
    delivered_at: datetime | None


@dataclass(frozen=True, slots=True)
class OrderStatusRecord:
    order_no: str
    status: str
    payment_status: str
    ordered_at: datetime
    total_thb: Decimal
    item_count: int
    synced_at: datetime
    shipment: ShipmentSummary | None


_ORDER_STATUS_SQL = """
SELECT o.order_no, o.status, o.payment_status, o.ordered_at, o.total_thb, o.synced_at,
       (SELECT COALESCE(SUM(i.qty), 0) FROM order_items i
         WHERE i.shop_id = o.shop_id AND i.order_id = o.order_id) AS item_count,
       s.carrier, s.tracking_no, s.status AS shipment_status,
       s.shipped_at, s.estimated_delivery_date, s.delivered_at
FROM orders o
LEFT JOIN LATERAL (
    SELECT sh.carrier, sh.tracking_no, sh.status, sh.shipped_at,
           sh.estimated_delivery_date, sh.delivered_at
    FROM shipments sh
    WHERE sh.shop_id = o.shop_id AND sh.order_id = o.order_id
    ORDER BY sh.shipped_at DESC NULLS LAST, sh.shipment_id DESC
    LIMIT 1
) s ON TRUE
WHERE o.shop_id = %(shop_id)s AND o.customer_id = %(customer_id)s AND o.order_no = %(order_no)s
"""


async def get_order_status(
    conn: psycopg.AsyncConnection, tenant: TenantContext, order_no: str
) -> OrderStatusRecord | None:
    if tenant.customer_id is None:
        return None
    params = {
        "shop_id": tenant.shop_id,
        "customer_id": tenant.customer_id,
        "order_no": order_no,
    }
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(_ORDER_STATUS_SQL, params)
        row = await cur.fetchone()
    if row is None:
        return None
    shipment = None
    if row["tracking_no"] is not None:
        shipment = ShipmentSummary(
            carrier=row["carrier"],
            tracking_no=row["tracking_no"],
            status=row["shipment_status"],
            shipped_at=row["shipped_at"],
            estimated_delivery_date=row["estimated_delivery_date"],
            delivered_at=row["delivered_at"],
        )
    return OrderStatusRecord(
        order_no=row["order_no"],
        status=row["status"],
        payment_status=row["payment_status"],
        ordered_at=row["ordered_at"],
        total_thb=row["total_thb"],
        item_count=int(row["item_count"]),
        synced_at=row["synced_at"],
        shipment=shipment,
    )


async def customer_exists(conn: psycopg.AsyncConnection, tenant: TenantContext) -> bool:
    """True iff tenant.customer_id is not None and that customer row exists in tenant.shop_id."""
    if tenant.customer_id is None:
        return False
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT 1 FROM customers WHERE shop_id = %s AND customer_id = %s",
            (tenant.shop_id, tenant.customer_id),
        )
        return await cur.fetchone() is not None


async def shop_has_customers(conn: psycopg.AsyncConnection, shop_id: str) -> bool:
    """True iff at least one customers row has this shop_id (Phase 1 stand-in for 'shop exists')."""
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("SELECT 1 FROM customers WHERE shop_id = %s LIMIT 1", (shop_id,))
        return await cur.fetchone() is not None
