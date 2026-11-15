"""Deterministic generator for the non-golden seed rows.

Generation order is part of the contract: the same RNG sequence must yield the same data.
"""

import random
from datetime import timedelta
from decimal import Decimal

from faker import Faker

from seed.golden import (
    ANCHOR,
    DEMO_SHOP_ID,
    GOLDEN_PRODUCTS,
    SECOND_SHOP_ID,
    make_customer,
    make_order,
    make_order_item,
    make_product,
    make_shipment,
)

ADDRESSES = [
    {"district": "เมืองเชียงใหม่", "province": "เชียงใหม่", "postal_code": "50000"},
    {"district": "บางรัก", "province": "กรุงเทพมหานคร", "postal_code": "10500"},
    {"district": "เมืองขอนแก่น", "province": "ขอนแก่น", "postal_code": "40000"},
    {"district": "หาดใหญ่", "province": "สงขลา", "postal_code": "90110"},
    {"district": "เมืองภูเก็ต", "province": "ภูเก็ต", "postal_code": "83000"},
]

TEA_CODES = [
    ("GRN", "ชาเขียว", "Green Tea", 150),
    ("BLK", "ชาดำอัสสัม", "Assam Black Tea", 140),
    ("ROS", "ชากุหลาบ", "Rose Tea", 190),
    ("CHA", "ชาคาโมมายล์", "Chamomile Tea", 210),
    ("PUE", "ชาผู่เอ๋อร์", "Pu-erh Tea", 320),
    ("LEM", "ชาตะไคร้", "Lemongrass Tea", 120),
    ("BUT", "ชาอัญชัน", "Butterfly Pea Tea", 130),
    ("HOJ", "ชาโฮจิฉะ", "Hojicha", 260),
]
TEA_SIZES = [(50, 1.0), (100, 1.8), (200, 3.2)]

TEAWARE = [
    ("WARE-STR-01", "ที่กรองชาสแตนเลส", "Stainless Tea Strainer", 180),
    ("WARE-TIN-01", "กระปุกเก็บใบชา", "Tea Tin", 220),
    ("WARE-WSK-01", "แปรงตีมัทฉะ", "Matcha Whisk", 390),
    ("WARE-BWL-01", "ถ้วยมัทฉะ", "Matcha Bowl", 520),
    ("WARE-GLS-02", "แก้วชาใส 2 ใบ", "Glass Tea Cups (2)", 340),
    ("WARE-TRY-01", "ถาดชาไม้ไผ่", "Bamboo Tea Tray", 780),
    ("WARE-KET-01", "กาต้มน้ำไฟฟ้า", "Electric Kettle", 1490),
    ("WARE-SPN-01", "ช้อนตักชาไม้", "Wooden Tea Scoop", 90),
    ("WARE-INF-01", "ขวดชงชาเย็น", "Cold Brew Bottle", 450),
    ("WARE-GFT-01", "ชุดของขวัญชา", "Tea Gift Set", 990),
]

ORDER_STATUSES = [
    "pending_payment",
    "paid",
    "packed",
    "shipped",
    "delivered",
    "cancelled",
    "returned",
]
ORDER_STATUS_WEIGHTS = [8, 8, 8, 22, 40, 8, 6]
SHIPPED_STATUSES = ("shipped", "delivered", "returned")
PAYMENT_METHODS = ["promptpay", "bank_transfer", "cod", "card"]
CARRIERS = ["Kerry Express", "Flash Express", "Thailand Post", "J&T Express"]

DEMO_CUSTOMER_COUNT = 53
SECOND_CUSTOMER_COUNT = 5
DEMO_ORDER_COUNT = 188
SECOND_ORDER_COUNT = 15


def generate_bulk(rng: random.Random, fake: Faker) -> dict[str, list[dict]]:
    """Keys: customers, products, orders, order_items, shipments. Non-golden rows for both shops."""
    demo_products = _demo_products(rng)
    demo_customers = _customers(rng, fake, DEMO_SHOP_ID, DEMO_CUSTOMER_COUNT)
    demo_orders, demo_items, demo_shipments = _orders(
        rng,
        DEMO_SHOP_ID,
        demo_customers,
        demo_products,
        DEMO_ORDER_COUNT,
        free_shipping_over=1000,
        shipping_fee=50,
    )
    second_customers = _customers(rng, fake, SECOND_SHOP_ID, SECOND_CUSTOMER_COUNT)
    second_orders, second_items, second_shipments = _orders(
        rng,
        SECOND_SHOP_ID,
        second_customers,
        [],
        SECOND_ORDER_COUNT,
        free_shipping_over=2000,
        shipping_fee=60,
    )
    return {
        "customers": demo_customers + second_customers,
        "products": demo_products,
        "orders": demo_orders + second_orders,
        "order_items": demo_items + second_items,
        "shipments": demo_shipments + second_shipments,
    }


def _demo_products(rng: random.Random) -> list[dict]:
    products = []
    for code, th, en, base in TEA_CODES:
        for size, mult in TEA_SIZES:
            products.append(
                make_product(
                    DEMO_SHOP_ID,
                    f"TEA-{code}-{size:03d}",
                    f"{th} {size} กรัม",
                    f"{en} {size} g",
                    Decimal(round(base * mult / 10) * 10),
                    rng.randint(0, 80),
                )
            )
    for sku, th, en, price in TEAWARE:
        products.append(
            make_product(DEMO_SHOP_ID, sku, th, en, Decimal(price), rng.randint(0, 20))
        )
    return products


def _customers(rng: random.Random, fake: Faker, shop_id: str, count: int) -> list[dict]:
    customers = []
    for i in range(1, count + 1):
        full_name = fake.name()
        phone = f"0{rng.randint(80, 99)}-555-{rng.randint(0, 9999):04d}"
        created_at = ANCHOR - timedelta(days=rng.randint(30, 365))
        customers.append(
            make_customer(shop_id, f"C-{1000 + i}", full_name, phone, None, created_at)
        )
    return customers


def _orders(
    rng: random.Random,
    shop_id: str,
    customers: list[dict],
    bulk_products: list[dict],
    count: int,
    *,
    free_shipping_over: int,
    shipping_fee: int,
) -> tuple[list[dict], list[dict], list[dict]]:
    # Golden products of this shop come first, then the bulk products.
    pool = [p for p in GOLDEN_PRODUCTS if p["shop_id"] == shop_id] + bulk_products
    orders: list[dict] = []
    items: list[dict] = []
    shipments: list[dict] = []
    for i in range(count):
        order_no = f"BC-{2001 + i}"
        customer_id = rng.choice(customers)["customer_id"]
        status = rng.choices(ORDER_STATUSES, weights=ORDER_STATUS_WEIGHTS)[0]
        ordered_at = ANCHOR - timedelta(
            days=rng.randint(1, 90), minutes=rng.randint(0, 1439)
        )
        # The second shop has only two products, so n is capped at the pool size.
        n = min(rng.randint(1, 3), len(pool))
        chosen = rng.sample(pool, n)
        lines = [(product, rng.randint(1, 3)) for product in chosen]
        subtotal = sum(
            (Decimal(qty) * product["price_thb"] for product, qty in lines), Decimal(0)
        )
        shipping = Decimal(0) if subtotal >= free_shipping_over else Decimal(shipping_fee)
        discount = Decimal(0)
        total = subtotal + shipping - discount
        payment_method = rng.choice(PAYMENT_METHODS)
        address = dict(rng.choice(ADDRESSES))
        orders.append(
            make_order(
                shop_id,
                order_no,
                customer_id,
                status,
                ordered_at,
                subtotal,
                shipping,
                discount,
                total,
                payment_method,
                address,
            )
        )
        for line_no, (product, qty) in enumerate(lines, start=1):
            items.append(
                make_order_item(
                    shop_id,
                    order_no,
                    line_no,
                    product["sku"],
                    qty,
                    product["price_thb"],
                )
            )
        if status in SHIPPED_STATUSES:
            shipments.append(_shipment(rng, shop_id, order_no, ordered_at, status))
    return orders, items, shipments


def _shipment(
    rng: random.Random, shop_id: str, order_no: str, ordered_at, status: str
) -> dict:
    carrier = rng.choice(CARRIERS)
    tracking_no = f"BULK{rng.randint(0, 10**10 - 1):010d}"
    shipped_at = ordered_at + timedelta(days=1)
    estimated = (shipped_at + timedelta(days=3)).date()
    if status == "shipped":
        return make_shipment(
            shop_id, order_no, carrier, tracking_no, "in_transit", shipped_at, estimated, None
        )
    return make_shipment(
        shop_id,
        order_no,
        carrier,
        tracking_no,
        "delivered",
        shipped_at,
        estimated,
        shipped_at + timedelta(days=3),
    )
