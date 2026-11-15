"""Build the demo dataset and load it into Postgres.

Only the two seed shops' rows are replaced. Never TRUNCATE, never touch other shop_ids.
"""

import copy
import random

import psycopg
from faker import Faker
from psycopg.types.json import Jsonb

from seed.bulk import generate_bulk
from seed.golden import (
    GOLDEN_CUSTOMERS,
    GOLDEN_ORDER_ITEMS,
    GOLDEN_ORDERS,
    GOLDEN_PRODUCTS,
    GOLDEN_SHIPMENTS,
    RANDOM_SEED,
    SEED_SHOP_IDS,
)

TABLE_ORDER = ("customers", "products", "orders", "order_items", "shipments")

# Children before parents.
DELETE_ORDER = (
    "refund_requests",
    "shipments",
    "order_items",
    "orders",
    "customer_identities",
    "products",
    "customers",
)


def build_dataset() -> dict[str, list[dict]]:
    """golden + bulk, keyed by table name in TABLE_ORDER. Pure and deterministic."""
    rng = random.Random(RANDOM_SEED)
    fake = Faker("th_TH")
    fake.seed_instance(RANDOM_SEED)
    bulk = generate_bulk(rng, fake)
    golden = {
        "customers": GOLDEN_CUSTOMERS,
        "products": GOLDEN_PRODUCTS,
        "orders": GOLDEN_ORDERS,
        "order_items": GOLDEN_ORDER_ITEMS,
        "shipments": GOLDEN_SHIPMENTS,
    }
    return {table: copy.deepcopy(golden[table]) + bulk[table] for table in TABLE_ORDER}


def seed_database(database_url: str) -> dict[str, int]:
    """Replace the two seed shops' rows. Returns {table: rows inserted} in TABLE_ORDER."""
    dataset = build_dataset()
    shop_ids = list(SEED_SHOP_IDS)
    counts: dict[str, int] = {}
    # One transaction: the connection context commits on success and rolls back on error.
    with psycopg.connect(database_url) as conn, conn.cursor() as cur:
        for table in DELETE_ORDER:
            cur.execute(f"DELETE FROM {table} WHERE shop_id = ANY(%s)", (shop_ids,))
        for table in TABLE_ORDER:
            rows = dataset[table]
            columns = list(rows[0].keys())
            placeholders = ", ".join(["%s"] * len(columns))
            sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
            params = [
                tuple(
                    Jsonb(row[col]) if col == "shipping_address" else row[col]
                    for col in columns
                )
                for row in rows
            ]
            cur.executemany(sql, params)
            counts[table] = len(rows)
    return counts
