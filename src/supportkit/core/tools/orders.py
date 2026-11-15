"""Order tools. Tenant ids come from runtime.context only, never from tool arguments."""

import json
import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

import psycopg
from langchain_core.tools import BaseTool, tool
from langgraph.prebuilt import ToolRuntime
from psycopg_pool import AsyncConnectionPool

from supportkit.core.graph.state import SupportContext
from supportkit.core.tenancy import repositories
from supportkit.core.thai_text import normalize_order_no

logger = logging.getLogger(__name__)

_BANGKOK = ZoneInfo("Asia/Bangkok")
_UNAVAILABLE = json.dumps({"error": "temporarily_unavailable"})


def _day(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(_BANGKOK).date().isoformat()


def _date(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _not_found(raw: str) -> str:
    normalized = normalize_order_no(raw)
    echo = normalized if normalized is not None else raw.strip()[:32]
    return json.dumps({"found": False, "order_no": echo}, ensure_ascii=False)


def _found(record: repositories.OrderStatusRecord) -> str:
    sh = record.shipment
    shipment = (
        None
        if sh is None
        else {
            "carrier": sh.carrier,
            "tracking_no": sh.tracking_no,
            "status": sh.status,
            "shipped_at": _day(sh.shipped_at),
            "estimated_delivery_date": _date(sh.estimated_delivery_date),
            "delivered_at": _day(sh.delivered_at),
        }
    )
    payload = {
        "found": True,
        "order_no": record.order_no,
        "status": record.status,
        "payment_status": record.payment_status,
        "ordered_at": _day(record.ordered_at),
        "total_thb": f"{record.total_thb:.2f}",
        "item_count": record.item_count,
        "shipment": shipment,
        "as_of": record.synced_at.astimezone(_BANGKOK).isoformat(timespec="seconds"),
    }
    return json.dumps(payload, ensure_ascii=False)


def build_order_tools(pool: AsyncConnectionPool) -> list[BaseTool]:
    """Returns [get_order_status]. The tool closes over `pool`."""

    @tool
    async def get_order_status(order_no: str, runtime: ToolRuntime[SupportContext]) -> str:
        """Look up the current status and shipment tracking of ONE order that belongs to the customer
        you are talking to. Use it whenever the customer asks about an order and gives an order number.
        Returns JSON. If "found" is false, no such order exists for this customer: do not guess or
        invent any detail, and ask the customer to check the number.

        Args:
            order_no: The order number exactly as the customer wrote it, e.g. "BC-1042".
        """
        tenant = runtime.context.tenant
        normalized = normalize_order_no(order_no)
        if normalized is None:
            logger.info("order_lookup shop_id=%s found=%s", tenant.shop_id, False)
            return _not_found(order_no)
        try:
            async with pool.connection() as conn:
                record = await repositories.get_order_status(conn, tenant, normalized)
        except psycopg.Error:
            logger.exception("get_order_status failed")
            return _UNAVAILABLE
        logger.info("order_lookup shop_id=%s found=%s", tenant.shop_id, record is not None)
        if record is None:
            return _not_found(order_no)
        return _found(record)

    return [get_order_status]
