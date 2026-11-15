"""Unit tests for the deterministic demo seed. No database needed."""

import re
from decimal import Decimal

import pytest

from seed.golden import DEMO_SHOP_ID, SECOND_SHOP_ID, SEED_SHOP_IDS
from seed.load import TABLE_ORDER, build_dataset


@pytest.fixture(scope="module")
def dataset() -> dict[str, list[dict]]:
    return build_dataset()


def _rows(dataset, table, shop_id):
    return [row for row in dataset[table] if row["shop_id"] == shop_id]


def _order(dataset, shop_id, order_no):
    (order,) = [o for o in _rows(dataset, "orders", shop_id) if o["order_no"] == order_no]
    return order


def _shipment_for(dataset, shop_id, order_id):
    matches = [s for s in _rows(dataset, "shipments", shop_id) if s["order_id"] == order_id]
    assert len(matches) == 1
    return matches[0]


def test_build_dataset_is_deterministic():
    assert build_dataset() == build_dataset()


def test_row_counts_for_demo_shop(dataset):
    assert len(_rows(dataset, "products", DEMO_SHOP_ID)) == 40
    assert len(_rows(dataset, "customers", DEMO_SHOP_ID)) == 60
    assert len(_rows(dataset, "orders", DEMO_SHOP_ID)) == 200


def test_row_counts_for_second_shop(dataset):
    assert len(_rows(dataset, "products", SECOND_SHOP_ID)) == 2
    assert len(_rows(dataset, "customers", SECOND_SHOP_ID)) == 7
    assert len(_rows(dataset, "orders", SECOND_SHOP_ID)) == 18


def test_every_row_has_a_seed_shop_id(dataset):
    assert set(dataset) == set(TABLE_ORDER)
    for table in TABLE_ORDER:
        for row in dataset[table]:
            assert row["shop_id"] in SEED_SHOP_IDS, (table, row)


def test_order_no_and_order_id_are_unique_per_shop(dataset):
    for shop_id in SEED_SHOP_IDS:
        orders = _rows(dataset, "orders", shop_id)
        assert len({o["order_no"] for o in orders}) == len(orders)
        assert len({o["order_id"] for o in orders}) == len(orders)


def test_order_nos_shared_across_shops(dataset):
    demo = {o["order_no"] for o in _rows(dataset, "orders", DEMO_SHOP_ID)}
    second = {o["order_no"] for o in _rows(dataset, "orders", SECOND_SHOP_ID)}
    shared = demo & second
    assert {"BC-1042", "BC-1050"} <= shared
    bulk_shared = {n for n in shared if 2001 <= int(n[3:]) <= 2999}
    assert len(bulk_shared) >= 15


def test_demo_bc_1042_golden_record(dataset):
    order = _order(dataset, DEMO_SHOP_ID, "BC-1042")
    assert order["customer_id"] == "C-0001"
    assert order["status"] == "shipped"
    assert order["total_thb"] == Decimal(1230)
    shipment = _shipment_for(dataset, DEMO_SHOP_ID, order["order_id"])
    assert shipment["tracking_no"] == "KEX26111042TH"
    assert shipment["carrier"] == "Kerry Express"


def test_shop_b_bc_1042_golden_record(dataset):
    order = _order(dataset, SECOND_SHOP_ID, "BC-1042")
    assert order["customer_id"] == "C-0001"
    assert order["total_thb"] == Decimal(3200)
    shipment = _shipment_for(dataset, SECOND_SHOP_ID, order["order_id"])
    assert shipment["tracking_no"] == "JT2611990042"


def test_order_totals_and_subtotals_add_up(dataset):
    for shop_id in SEED_SHOP_IDS:
        items_by_order: dict[str, list[dict]] = {}
        for item in _rows(dataset, "order_items", shop_id):
            items_by_order.setdefault(item["order_id"], []).append(item)
        for order in _rows(dataset, "orders", shop_id):
            assert order["total_thb"] == (
                order["subtotal_thb"] + order["shipping_fee_thb"] - order["discount_thb"]
            ), order["order_no"]
            items = items_by_order.get(order["order_id"], [])
            computed = sum(
                (Decimal(i["qty"]) * i["unit_price_thb"] for i in items), Decimal(0)
            )
            assert order["subtotal_thb"] == computed, order["order_no"]


def test_foreign_references_stay_inside_the_shop(dataset):
    for shop_id in SEED_SHOP_IDS:
        skus = {p["sku"] for p in _rows(dataset, "products", shop_id)}
        customer_ids = {c["customer_id"] for c in _rows(dataset, "customers", shop_id)}
        order_ids = {o["order_id"] for o in _rows(dataset, "orders", shop_id)}
        for item in _rows(dataset, "order_items", shop_id):
            assert item["sku"] in skus
            assert item["order_id"] in order_ids
        for order in _rows(dataset, "orders", shop_id):
            assert order["customer_id"] in customer_ids
        for shipment in _rows(dataset, "shipments", shop_id):
            assert shipment["order_id"] in order_ids


def test_out_of_stock_golden_matcha(dataset):
    (matcha,) = [
        p
        for p in _rows(dataset, "products", DEMO_SHOP_ID)
        if p["sku"] == "TEA-MAT-100"
    ]
    assert matcha["stock_qty"] == 0


def test_shared_phone_for_c0004_and_c0005(dataset):
    phones = {
        c["customer_id"]: c["phone"] for c in _rows(dataset, "customers", DEMO_SHOP_ID)
    }
    assert phones["C-0004"] == phones["C-0005"]


def test_every_phone_has_the_fake_format(dataset):
    pattern = re.compile(r"^0\d{2}-555-\d{4}$")
    for customer in dataset["customers"]:
        assert pattern.match(customer["phone"]), customer


def test_no_bulk_order_uses_a_golden_customer(dataset):
    for order in dataset["orders"]:
        number = int(order["order_no"][3:])
        if 2001 <= number <= 2999:
            assert not order["customer_id"].startswith("C-0"), order
