# Phase 1 · Spec 03 — Deterministic demo seed (baan-bai-cha + shop-b)

**Suggested implementer:** `quick-implementer`
**Depends on:** 01 (CLI stub, deps), 02 (tables) · **Blocks:** 09 · **Parallel with:** 04, 06

## Goal
Provide `supportkit seed`: a deterministic dataset for the demo shop `baan-bai-cha` and a second tenant `shop-b` whose order numbers and customer ids deliberately collide with the demo shop's. The hand-written **golden records** below have fixed ids that evals and the demo script reference; everything else is generated with a fixed random seed. All data is fake.

## Files
| Path | Action | Purpose |
|---|---|---|
| `seed/__init__.py` | create | empty |
| `seed/golden.py` | create | golden rows as module constants (tables below, verbatim) |
| `seed/bulk.py` | create | deterministic generator for non-golden rows |
| `seed/load.py` | create | `build_dataset()`, `seed_database()` |
| `tests/test_seed_dataset.py` | create | unit tests (no DB) |
| `tests/integration/test_seed_load.py` | create | DB tests |

## Interfaces

### Constants (`seed/golden.py`)
```python
DEMO_SHOP_ID = "baan-bai-cha"
SECOND_SHOP_ID = "shop-b"
SEED_SHOP_IDS = (DEMO_SHOP_ID, SECOND_SHOP_ID)
ANCHOR = datetime(2026, 11, 15, 12, 0, tzinfo=ZoneInfo("Asia/Bangkok"))   # the dataset's "now"
RANDOM_SEED = 20261115
GOLDEN_CUSTOMERS: list[dict]; GOLDEN_PRODUCTS: list[dict]; GOLDEN_ORDERS: list[dict]
GOLDEN_ORDER_ITEMS: list[dict]; GOLDEN_SHIPMENTS: list[dict]
```
Every row is a `dict` whose keys are exactly the column names of its table (spec 02), including `shop_id`.

### Functions
```python
# seed/bulk.py
def generate_bulk(rng: random.Random, fake: Faker) -> dict[str, list[dict]]:
    """Keys: customers, products, orders, order_items, shipments. Non-golden rows for both shops."""

# seed/load.py
TABLE_ORDER = ("customers", "products", "orders", "order_items", "shipments")
def build_dataset() -> dict[str, list[dict]]:
    """golden + bulk, keyed by table name in TABLE_ORDER. Pure and deterministic."""
def seed_database(database_url: str) -> dict[str, int]:
    """Replace the two seed shops' rows. Returns {table: rows inserted} in TABLE_ORDER."""
```

### ID and order-number formats (fixed for the whole project's demo data)
| Thing | Format | Golden range | Bulk range |
|---|---|---|---|
| `order_no` | `BC-` + 4 digits | `BC-1001`–`BC-1999`, plus `BC-9001` | `BC-2001` upward |
| `order_id` | `O-` + the 4 digits of `order_no` | | |
| `shipment_id` | `S-` + the 4 digits of `order_no` | | |
| `customer_id` | `C-` + 4 digits | `C-0001`–`C-0999` | `C-1001` upward |
| `sku` | uppercase letters, digits, `-` | below | below |

Both shops use the same formats on purpose.

### Golden customers
`email` is `None` unless given. `created_at` = `2026-09-01 09:00 +07` for all golden customers.

| shop_id | customer_id | full_name | phone | email | Role in evals |
|---|---|---|---|---|---|
| baan-bai-cha | C-0001 | สมหญิง ใจดี | 081-555-0101 | somying@example.com | 2 open orders |
| baan-bai-cha | C-0002 | อนันต์ ศรีสุข | 082-555-0102 | | delivered + cancelled |
| baan-bai-cha | C-0003 | พิมพ์ชนก แก้วมณี | 083-555-0103 | | late shipment, high-value order |
| baan-bai-cha | C-0004 | วิชัย ทองดี | 084-555-0104 | | shares phone with C-0005 |
| baan-bai-cha | C-0005 | มาลี ทองดี | 084-555-0104 | | shares phone with C-0004 |
| baan-bai-cha | C-0006 | ธนพล รุ่งเรือง | 086-555-0106 | | order past return window |
| baan-bai-cha | C-0007 | Emma Wilson | 087-555-0107 | emma@example.com | English speaker, returned order |
| shop-b | C-0001 | ปรีชา มั่นคง | 091-555-0201 | | same customer_id as the demo shop's C-0001, different person |
| shop-b | C-0002 | Sarah Chen | 092-555-0202 | sarah@example.com | |

### Golden products
`description = ""`, `is_active = True`, `updated_at = ANCHOR`.

| shop_id | sku | name_th | name_en | price_thb | stock_qty |
|---|---|---|---|---|---|
| baan-bai-cha | TEA-OOL-050 | ชาอู่หลงก้านอ่อน 50 กรัม | Soft-stem Oolong 50 g | 290.00 | 40 |
| baan-bai-cha | TEA-JAS-100 | ชามะลิ 100 กรัม | Jasmine Tea 100 g | 240.00 | 25 |
| baan-bai-cha | TEA-MAT-100 | มัทฉะเกรดพิธี 100 กรัม | Ceremonial Matcha 100 g | 890.00 | **0** (out-of-stock golden) |
| baan-bai-cha | TEA-THA-200 | ชาไทยสูตรโบราณ 200 กรัม | Classic Thai Tea 200 g | 180.00 | 60 |
| baan-bai-cha | WARE-POT-01 | กาชาเซรามิก | Ceramic Teapot | 1250.00 | 8 |
| baan-bai-cha | WARE-CUP-04 | ชุดถ้วยชา 4 ใบ | Tea Cup Set (4) | 650.00 | 12 |
| shop-b | CER-VASE-01 | แจกันเซรามิก | Ceramic Vase | 1600.00 | 5 |
| shop-b | CER-PLATE-02 | จานเซรามิก | Ceramic Plate | 450.00 | 30 |

### Golden orders
All times are `+07:00`. `synced_at = ANCHOR`. `payment_method = "promptpay"`. `shipping_address = {"district": "เมืองเชียงใหม่", "province": "เชียงใหม่", "postal_code": "50000"}`. `payment_status`: `pending` for `pending_payment` and `cancelled`, `refunded` for `returned`, otherwise `paid`. Items are `sku × qty` at the product's golden price; `subtotal = Σ qty × price`; `total = subtotal + shipping − discount`.

| shop_id | order_no | customer_id | status | ordered_at | items | subtotal | shipping | discount | total |
|---|---|---|---|---|---|---|---|---|---|
| baan-bai-cha | BC-1042 | C-0001 | shipped | 2026-11-12 10:15 | TEA-OOL-050×2, WARE-CUP-04×1 | 1230 | 0 | 0 | 1230 |
| baan-bai-cha | BC-1043 | C-0001 | pending_payment | 2026-11-14 20:40 | TEA-JAS-100×1, TEA-THA-200×1 | 420 | 50 | 0 | 470 |
| baan-bai-cha | BC-1050 | C-0002 | delivered | 2026-11-04 09:05 | WARE-POT-01×1, TEA-OOL-050×2 | 1830 | 0 | 0 | 1830 |
| baan-bai-cha | BC-1051 | C-0002 | cancelled | 2026-11-06 13:30 | WARE-CUP-04×1 | 650 | 50 | 0 | 700 |
| baan-bai-cha | BC-1060 | C-0003 | shipped | 2026-11-04 16:20 | TEA-THA-200×3 | 540 | 50 | 0 | 590 |
| baan-bai-cha | BC-1061 | C-0003 | paid | 2026-11-14 11:00 | WARE-POT-01×3, WARE-CUP-04×2 | 5050 | 0 | 200 | 4850 |
| baan-bai-cha | BC-1070 | C-0004 | packed | 2026-11-13 08:45 | TEA-JAS-100×3 | 720 | 50 | 0 | 770 |
| baan-bai-cha | BC-1071 | C-0005 | shipped | 2026-11-12 19:10 | TEA-OOL-050×1 | 290 | 50 | 0 | 340 |
| baan-bai-cha | BC-1080 | C-0006 | delivered | 2026-10-16 14:00 | TEA-MAT-100×1 | 890 | 50 | 0 | 940 |
| baan-bai-cha | BC-1081 | C-0006 | packed | 2026-11-14 09:30 | TEA-THA-200×2 | 360 | 50 | 0 | 410 |
| baan-bai-cha | BC-1090 | C-0007 | returned | 2026-10-24 12:00 | WARE-CUP-04×1 | 650 | 50 | 0 | 700 |
| baan-bai-cha | BC-1091 | C-0007 | shipped | 2026-11-13 15:25 | TEA-OOL-050×3, TEA-JAS-100×1 | 1110 | 0 | 0 | 1110 |
| shop-b | BC-1042 | C-0001 | delivered | 2026-11-08 10:00 | CER-VASE-01×2 | 3200 | 0 | 0 | 3200 |
| shop-b | BC-1050 | C-0002 | shipped | 2026-11-12 17:45 | CER-PLATE-02×2 | 900 | 60 | 0 | 960 |
| shop-b | BC-9001 | C-0001 | paid | 2026-11-14 21:05 | CER-PLATE-02×1 | 450 | 60 | 0 | 510 |

### Golden shipments
`synced_at = ANCHOR`. Orders not listed have no shipment.

| shop_id | order_no | carrier | tracking_no | status | shipped_at | estimated_delivery_date | delivered_at |
|---|---|---|---|---|---|---|---|
| baan-bai-cha | BC-1042 | Kerry Express | KEX26111042TH | in_transit | 2026-11-13 14:00 | 2026-11-16 | — |
| baan-bai-cha | BC-1050 | Flash Express | TH26110050A | delivered | 2026-11-05 10:00 | 2026-11-07 | 2026-11-08 13:20 |
| baan-bai-cha | BC-1060 | Thailand Post | EB261100060TH | in_transit | 2026-11-05 09:00 | 2026-11-09 (late golden) | — |
| baan-bai-cha | BC-1071 | J&T Express | JT2611007100 | in_transit | 2026-11-13 16:30 | 2026-11-17 | — |
| baan-bai-cha | BC-1080 | Kerry Express | KEX26101080TH | delivered | 2026-10-17 10:00 | 2026-10-19 | 2026-10-20 11:00 |
| baan-bai-cha | BC-1090 | Flash Express | TH26100090B | delivered | 2026-10-25 10:00 | 2026-10-27 | 2026-10-28 15:00 |
| baan-bai-cha | BC-1091 | Kerry Express | KEX26111091TH | in_transit | 2026-11-14 10:00 | 2026-11-16 | — |
| shop-b | BC-1042 | J&T Express | JT2611990042 | delivered | 2026-11-09 09:00 | 2026-11-11 | 2026-11-12 15:00 |
| shop-b | BC-1050 | Flash Express | TH26119950B | in_transit | 2026-11-13 11:00 | 2026-11-16 | — |

### Bulk generation (`seed/bulk.py`)
Setup in `build_dataset()`: `rng = random.Random(RANDOM_SEED)`; `fake = Faker("th_TH"); fake.seed_instance(RANDOM_SEED)`. Faker is used **only** for `fake.name()`. Generate in this exact order so output is reproducible: demo-shop products → demo-shop customers → demo-shop orders (items and shipment generated together with each order) → shop-b customers → shop-b orders.

**Products, demo shop only (34 rows → 40 with golden).**
Teas: for each `(code, th, en, base)` × each size `(50, 1.0)`, `(100, 1.8)`, `(200, 3.2)`: `sku = f"TEA-{code}-{size:03d}"`, `name_th = f"{th} {size} กรัม"`, `name_en = f"{en} {size} g"`, `price_thb = round(base * mult / 10) * 10`, `stock_qty = rng.randint(0, 80)`.
```
("GRN","ชาเขียว","Green Tea",150) ("BLK","ชาดำอัสสัม","Assam Black Tea",140) ("ROS","ชากุหลาบ","Rose Tea",190)
("CHA","ชาคาโมมายล์","Chamomile Tea",210) ("PUE","ชาผู่เอ๋อร์","Pu-erh Tea",320) ("LEM","ชาตะไคร้","Lemongrass Tea",120)
("BUT","ชาอัญชัน","Butterfly Pea Tea",130) ("HOJ","ชาโฮจิฉะ","Hojicha",260)
```
Teaware: `(sku, th, en, price)`, `stock_qty = rng.randint(0, 20)`:
```
("WARE-STR-01","ที่กรองชาสแตนเลส","Stainless Tea Strainer",180) ("WARE-TIN-01","กระปุกเก็บใบชา","Tea Tin",220)
("WARE-WSK-01","แปรงตีมัทฉะ","Matcha Whisk",390) ("WARE-BWL-01","ถ้วยมัทฉะ","Matcha Bowl",520)
("WARE-GLS-02","แก้วชาใส 2 ใบ","Glass Tea Cups (2)",340) ("WARE-TRY-01","ถาดชาไม้ไผ่","Bamboo Tea Tray",780)
("WARE-KET-01","กาต้มน้ำไฟฟ้า","Electric Kettle",1490) ("WARE-SPN-01","ช้อนตักชาไม้","Wooden Tea Scoop",90)
("WARE-INF-01","ขวดชงชาเย็น","Cold Brew Bottle",450) ("WARE-GFT-01","ชุดของขวัญชา","Tea Gift Set",990)
```
The skipped `(GRN..HOJ)` codes never collide with golden SKUs.

**Customers.** Demo shop: 53 rows `C-1001`..`C-1053`. shop-b: 5 rows `C-1001`..`C-1005`. `full_name = fake.name()`, `phone = f"0{rng.randint(80, 99)}-555-{rng.randint(0, 9999):04d}"`, `email = None`, `created_at = ANCHOR - timedelta(days=rng.randint(30, 365))`.

**Orders.** Demo shop: 188 rows `BC-2001`..`BC-2188` (→ 200 with golden). shop-b: 15 rows `BC-2001`..`BC-2015`. For each order, in order:
1. `customer_id = rng.choice(<that shop's bulk customers>)["customer_id"]` (bulk orders never belong to golden customers).
2. `status = rng.choices(["pending_payment","paid","packed","shipped","delivered","cancelled","returned"], weights=[8,8,8,22,40,8,6])[0]`.
3. `ordered_at = ANCHOR - timedelta(days=rng.randint(1, 90), minutes=rng.randint(0, 1439))`.
4. Items: `n = min(rng.randint(1, 3), len(<that shop's products>))` distinct products (clamp added in review: shop-b has only 2 products; RNG consumption is unchanged) via `rng.sample(<all that shop's products, golden included>, n)`, each `qty = rng.randint(1, 3)`, `unit_price_thb` = product price, `line_no` from 1.
5. Money: `subtotal = Σ`; demo shop `shipping = 0 if subtotal >= 1000 else 50`; shop-b `shipping = 0 if subtotal >= 2000 else 60`; `discount = 0`; `total = subtotal + shipping`.
6. `payment_method = rng.choice(["promptpay","bank_transfer","cod","card"])`; `payment_status` by the same rule as golden orders.
7. `shipping_address = rng.choice(ADDRESSES)` where `ADDRESSES` is the list below. `synced_at = ANCHOR`.
8. Shipment only if status ∈ {shipped, delivered, returned}: `carrier = rng.choice(["Kerry Express","Flash Express","Thailand Post","J&T Express"])`; `tracking_no = f"BULK{rng.randint(0, 10**10 - 1):010d}"`; `shipped_at = ordered_at + timedelta(days=1)`; `estimated_delivery_date = (shipped_at + timedelta(days=3)).date()`; status `in_transit` and `delivered_at = None` for `shipped`, else status `delivered` and `delivered_at = shipped_at + timedelta(days=3)`.
```python
ADDRESSES = [
  {"district": "เมืองเชียงใหม่", "province": "เชียงใหม่", "postal_code": "50000"},
  {"district": "บางรัก", "province": "กรุงเทพมหานคร", "postal_code": "10500"},
  {"district": "เมืองขอนแก่น", "province": "ขอนแก่น", "postal_code": "40000"},
  {"district": "หาดใหญ่", "province": "สงขลา", "postal_code": "90110"},
  {"district": "เมืองภูเก็ต", "province": "ภูเก็ต", "postal_code": "83000"},
]
```
Money values are `Decimal`. Bulk tracking numbers start with `BULK` so they can never equal a golden tracking number.

## Behaviour (`seed_database`)
1. Uses sync `psycopg.connect(database_url)` and **one transaction**.
2. Deletes existing rows `WHERE shop_id = ANY(%s)` with `SEED_SHOP_IDS`, in this order: `refund_requests`, `shipments`, `order_items`, `orders`, `customer_identities`, `products`, `customers`. Never `TRUNCATE`, never touches another `shop_id`, never touches LangGraph tables.
3. Inserts `build_dataset()` in `TABLE_ORDER` with `cursor.executemany`; column list comes from the row dict's keys; `shipping_address` is wrapped with `psycopg.types.json.Jsonb`.
4. Running it twice yields identical table contents (idempotent). Any error rolls back everything.
5. `build_dataset()` performs no I/O and returns equal data on every call.

## Tests
`tests/test_seed_dataset.py` (unit)
| # | Check | Expected |
|---|---|---|
| 1 | `build_dataset() == build_dataset()` | `True` |
| 2 | Row counts for `baan-bai-cha` | products 40, customers 60, orders 200 |
| 3 | Row counts for `shop-b` | products 2, customers 7, orders 18 |
| 4 | Every row in every table | has key `shop_id` ∈ `SEED_SHOP_IDS` |
| 5 | `(shop_id, order_no)` and `(shop_id, order_id)` | unique |
| 6 | order_nos present in both shops | include `BC-1042`, `BC-1050`, and ≥ 15 bulk numbers |
| 7 | Demo shop `BC-1042` | `customer_id == "C-0001"`, `status == "shipped"`, `total_thb == Decimal("1230")`; its shipment has `tracking_no == "KEX26111042TH"`, `carrier == "Kerry Express"` |
| 8 | shop-b `BC-1042` | `customer_id == "C-0001"`, `total_thb == Decimal("3200")`, shipment `tracking_no == "JT2611990042"` |
| 9 | Every order | `total_thb == subtotal_thb + shipping_fee_thb - discount_thb` and `subtotal_thb == Σ qty × unit_price_thb` of its items |
| 10 | Every `order_items.sku` / `orders.customer_id` / `shipments.order_id` | exists in the same shop's products / customers / orders |
| 11 | Product `TEA-MAT-100` (demo shop) | `stock_qty == 0` |
| 12 | Customers `C-0004`, `C-0005` (demo shop) | same `phone` |
| 13 | Every phone | matches `^0\d{2}-555-\d{4}$` |
| 14 | No bulk order | has a golden customer_id (`C-0xxx`) |

`tests/integration/test_seed_load.py` (uses `database_url` fixture; skips without Postgres)
| # | Steps | Expected |
|---|---|---|
| 1 | Insert a customer under shop `t-seed-<8 hex>`; run `seed_database` twice; delete the extra customer in `finally` | both runs return identical counts; `SELECT count(*) FROM orders WHERE shop_id='baan-bai-cha'` = 200; the extra shop's customer still exists |
| 2 | After seeding: `SELECT s.tracking_no FROM orders o JOIN shipments s USING (shop_id, order_id) WHERE o.shop_id='baan-bai-cha' AND o.order_no='BC-1042'` | `KEX26111042TH` |

## Acceptance criteria
```powershell
.\.venv\Scripts\supportkit.exe seed      # prints: customers: 67 / products: 42 / orders: 218 / order_items: N / shipments: N ; exit 0
.\.venv\Scripts\supportkit.exe seed      # same output again
.\.venv\Scripts\ruff.exe check src tests db seed
$env:LANGGRAPH_STRICT_MSGPACK='true'; .\.venv\Scripts\python.exe -m pytest -q
```

## Out of scope
- `cli.py` (the `seed` command already exists from spec 01), migrations, anything under `src/`.
- Policy documents, Google Sheet CSV export, `customer_identities` / `refund_requests` rows.
- Real names, phone numbers or addresses of real people.
