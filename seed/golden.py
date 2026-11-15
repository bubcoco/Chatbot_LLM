"""Golden records for the demo seed.

Ids, values and dates are fixed: evals and the demo script reference them. Do not change them.
All data is fake.
"""

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

DEMO_SHOP_ID = "baan-bai-cha"
SECOND_SHOP_ID = "shop-b"
SEED_SHOP_IDS = (DEMO_SHOP_ID, SECOND_SHOP_ID)
BANGKOK = ZoneInfo("Asia/Bangkok")  # +07:00, no DST
ANCHOR = datetime(2026, 11, 15, 12, 0, tzinfo=BANGKOK)  # the dataset's "now"
RANDOM_SEED = 20261115

GOLDEN_SHIPPING_ADDRESS = {
    "district": "เมืองเชียงใหม่",
    "province": "เชียงใหม่",
    "postal_code": "50000",
}


def _at(month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(2026, month, day, hour, minute, tzinfo=BANGKOK)


def payment_status_for(status: str) -> str:
    if status in ("pending_payment", "cancelled"):
        return "pending"
    if status == "returned":
        return "refunded"
    return "paid"


def make_customer(
    shop_id: str,
    customer_id: str,
    full_name: str,
    phone: str,
    email: str | None,
    created_at: datetime,
) -> dict:
    return {
        "shop_id": shop_id,
        "customer_id": customer_id,
        "full_name": full_name,
        "phone": phone,
        "email": email,
        "created_at": created_at,
    }


def make_product(
    shop_id: str,
    sku: str,
    name_th: str,
    name_en: str,
    price_thb: Decimal,
    stock_qty: int,
) -> dict:
    return {
        "shop_id": shop_id,
        "sku": sku,
        "name_th": name_th,
        "name_en": name_en,
        "description": "",
        "price_thb": price_thb,
        "stock_qty": stock_qty,
        "is_active": True,
        "updated_at": ANCHOR,
    }


def make_order(
    shop_id: str,
    order_no: str,
    customer_id: str,
    status: str,
    ordered_at: datetime,
    subtotal_thb: Decimal,
    shipping_fee_thb: Decimal,
    discount_thb: Decimal,
    total_thb: Decimal,
    payment_method: str,
    shipping_address: dict,
) -> dict:
    return {
        "shop_id": shop_id,
        "order_id": "O-" + order_no[3:],
        "order_no": order_no,
        "customer_id": customer_id,
        "status": status,
        "subtotal_thb": subtotal_thb,
        "shipping_fee_thb": shipping_fee_thb,
        "discount_thb": discount_thb,
        "total_thb": total_thb,
        "payment_method": payment_method,
        "payment_status": payment_status_for(status),
        "ordered_at": ordered_at,
        "shipping_address": shipping_address,
        "synced_at": ANCHOR,
    }


def make_order_item(
    shop_id: str,
    order_no: str,
    line_no: int,
    sku: str,
    qty: int,
    unit_price_thb: Decimal,
) -> dict:
    return {
        "shop_id": shop_id,
        "order_id": "O-" + order_no[3:],
        "line_no": line_no,
        "sku": sku,
        "qty": qty,
        "unit_price_thb": unit_price_thb,
    }


def make_shipment(
    shop_id: str,
    order_no: str,
    carrier: str,
    tracking_no: str,
    status: str,
    shipped_at: datetime | None,
    estimated_delivery_date: date | None,
    delivered_at: datetime | None,
) -> dict:
    return {
        "shop_id": shop_id,
        "shipment_id": "S-" + order_no[3:],
        "order_id": "O-" + order_no[3:],
        "carrier": carrier,
        "tracking_no": tracking_no,
        "status": status,
        "shipped_at": shipped_at,
        "estimated_delivery_date": estimated_delivery_date,
        "delivered_at": delivered_at,
        "synced_at": ANCHOR,
    }


DEMO = DEMO_SHOP_ID
SECOND = SECOND_SHOP_ID

GOLDEN_CUSTOMERS = [
    make_customer(DEMO, "C-0001", "สมหญิง ใจดี", "081-555-0101", "somying@example.com", _at(9, 1, 9, 0)),
    make_customer(DEMO, "C-0002", "อนันต์ ศรีสุข", "082-555-0102", None, _at(9, 1, 9, 0)),
    make_customer(DEMO, "C-0003", "พิมพ์ชนก แก้วมณี", "083-555-0103", None, _at(9, 1, 9, 0)),
    make_customer(DEMO, "C-0004", "วิชัย ทองดี", "084-555-0104", None, _at(9, 1, 9, 0)),
    make_customer(DEMO, "C-0005", "มาลี ทองดี", "084-555-0104", None, _at(9, 1, 9, 0)),
    make_customer(DEMO, "C-0006", "ธนพล รุ่งเรือง", "086-555-0106", None, _at(9, 1, 9, 0)),
    make_customer(DEMO, "C-0007", "Emma Wilson", "087-555-0107", "emma@example.com", _at(9, 1, 9, 0)),
    make_customer(SECOND, "C-0001", "ปรีชา มั่นคง", "091-555-0201", None, _at(9, 1, 9, 0)),
    make_customer(SECOND, "C-0002", "Sarah Chen", "092-555-0202", "sarah@example.com", _at(9, 1, 9, 0)),
]

GOLDEN_PRODUCTS = [
    make_product(DEMO, "TEA-OOL-050", "ชาอู่หลงก้านอ่อน 50 กรัม", "Soft-stem Oolong 50 g", Decimal("290.00"), 40),
    make_product(DEMO, "TEA-JAS-100", "ชามะลิ 100 กรัม", "Jasmine Tea 100 g", Decimal("240.00"), 25),
    make_product(DEMO, "TEA-MAT-100", "มัทฉะเกรดพิธี 100 กรัม", "Ceremonial Matcha 100 g", Decimal("890.00"), 0),
    make_product(DEMO, "TEA-THA-200", "ชาไทยสูตรโบราณ 200 กรัม", "Classic Thai Tea 200 g", Decimal("180.00"), 60),
    make_product(DEMO, "WARE-POT-01", "กาชาเซรามิก", "Ceramic Teapot", Decimal("1250.00"), 8),
    make_product(DEMO, "WARE-CUP-04", "ชุดถ้วยชา 4 ใบ", "Tea Cup Set (4)", Decimal("650.00"), 12),
    make_product(SECOND, "CER-VASE-01", "แจกันเซรามิก", "Ceramic Vase", Decimal("1600.00"), 5),
    make_product(SECOND, "CER-PLATE-02", "จานเซรามิก", "Ceramic Plate", Decimal("450.00"), 30),
]

_PRICE_BY_KEY = {(p["shop_id"], p["sku"]): p["price_thb"] for p in GOLDEN_PRODUCTS}

# shop_id, order_no, customer_id, status, ordered_at, [(sku, qty)], subtotal, shipping, discount, total
_GOLDEN_ORDER_SPECS = [
    (DEMO, "BC-1042", "C-0001", "shipped", _at(11, 12, 10, 15),
     [("TEA-OOL-050", 2), ("WARE-CUP-04", 1)], 1230, 0, 0, 1230),
    (DEMO, "BC-1043", "C-0001", "pending_payment", _at(11, 14, 20, 40),
     [("TEA-JAS-100", 1), ("TEA-THA-200", 1)], 420, 50, 0, 470),
    (DEMO, "BC-1050", "C-0002", "delivered", _at(11, 4, 9, 5),
     [("WARE-POT-01", 1), ("TEA-OOL-050", 2)], 1830, 0, 0, 1830),
    (DEMO, "BC-1051", "C-0002", "cancelled", _at(11, 6, 13, 30),
     [("WARE-CUP-04", 1)], 650, 50, 0, 700),
    (DEMO, "BC-1060", "C-0003", "shipped", _at(11, 4, 16, 20),
     [("TEA-THA-200", 3)], 540, 50, 0, 590),
    (DEMO, "BC-1061", "C-0003", "paid", _at(11, 14, 11, 0),
     [("WARE-POT-01", 3), ("WARE-CUP-04", 2)], 5050, 0, 200, 4850),
    (DEMO, "BC-1070", "C-0004", "packed", _at(11, 13, 8, 45),
     [("TEA-JAS-100", 3)], 720, 50, 0, 770),
    (DEMO, "BC-1071", "C-0005", "shipped", _at(11, 12, 19, 10),
     [("TEA-OOL-050", 1)], 290, 50, 0, 340),
    (DEMO, "BC-1080", "C-0006", "delivered", _at(10, 16, 14, 0),
     [("TEA-MAT-100", 1)], 890, 50, 0, 940),
    (DEMO, "BC-1081", "C-0006", "packed", _at(11, 14, 9, 30),
     [("TEA-THA-200", 2)], 360, 50, 0, 410),
    (DEMO, "BC-1090", "C-0007", "returned", _at(10, 24, 12, 0),
     [("WARE-CUP-04", 1)], 650, 50, 0, 700),
    (DEMO, "BC-1091", "C-0007", "shipped", _at(11, 13, 15, 25),
     [("TEA-OOL-050", 3), ("TEA-JAS-100", 1)], 1110, 0, 0, 1110),
    (SECOND, "BC-1042", "C-0001", "delivered", _at(11, 8, 10, 0),
     [("CER-VASE-01", 2)], 3200, 0, 0, 3200),
    (SECOND, "BC-1050", "C-0002", "shipped", _at(11, 12, 17, 45),
     [("CER-PLATE-02", 2)], 900, 60, 0, 960),
    (SECOND, "BC-9001", "C-0001", "paid", _at(11, 14, 21, 5),
     [("CER-PLATE-02", 1)], 450, 60, 0, 510),
]

GOLDEN_ORDERS = []
GOLDEN_ORDER_ITEMS = []
for _shop, _order_no, _customer, _status, _ordered_at, _items, _subtotal, _shipping, _discount, _total in (
    _GOLDEN_ORDER_SPECS
):
    GOLDEN_ORDERS.append(
        make_order(
            _shop,
            _order_no,
            _customer,
            _status,
            _ordered_at,
            Decimal(_subtotal),
            Decimal(_shipping),
            Decimal(_discount),
            Decimal(_total),
            "promptpay",
            dict(GOLDEN_SHIPPING_ADDRESS),
        )
    )
    for _line_no, (_sku, _qty) in enumerate(_items, start=1):
        GOLDEN_ORDER_ITEMS.append(
            make_order_item(_shop, _order_no, _line_no, _sku, _qty, _PRICE_BY_KEY[(_shop, _sku)])
        )

GOLDEN_SHIPMENTS = [
    make_shipment(DEMO, "BC-1042", "Kerry Express", "KEX26111042TH", "in_transit",
                  _at(11, 13, 14, 0), date(2026, 11, 16), None),
    make_shipment(DEMO, "BC-1050", "Flash Express", "TH26110050A", "delivered",
                  _at(11, 5, 10, 0), date(2026, 11, 7), _at(11, 8, 13, 20)),
    make_shipment(DEMO, "BC-1060", "Thailand Post", "EB261100060TH", "in_transit",
                  _at(11, 5, 9, 0), date(2026, 11, 9), None),
    make_shipment(DEMO, "BC-1071", "J&T Express", "JT2611007100", "in_transit",
                  _at(11, 13, 16, 30), date(2026, 11, 17), None),
    make_shipment(DEMO, "BC-1080", "Kerry Express", "KEX26101080TH", "delivered",
                  _at(10, 17, 10, 0), date(2026, 10, 19), _at(10, 20, 11, 0)),
    make_shipment(DEMO, "BC-1090", "Flash Express", "TH26100090B", "delivered",
                  _at(10, 25, 10, 0), date(2026, 10, 27), _at(10, 28, 15, 0)),
    make_shipment(DEMO, "BC-1091", "Kerry Express", "KEX26111091TH", "in_transit",
                  _at(11, 14, 10, 0), date(2026, 11, 16), None),
    make_shipment(SECOND, "BC-1042", "J&T Express", "JT2611990042", "delivered",
                  _at(11, 9, 9, 0), date(2026, 11, 11), _at(11, 12, 15, 0)),
    make_shipment(SECOND, "BC-1050", "Flash Express", "TH26119950B", "in_transit",
                  _at(11, 13, 11, 0), date(2026, 11, 16), None),
]
