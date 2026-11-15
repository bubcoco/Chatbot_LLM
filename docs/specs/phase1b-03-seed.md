# Phase 1b · Spec 03 — Seed: golden phone variants and raw sheet rows

**Suggested implementer:** `quick-implementer` (data and assertions are given)
**Depends on:** 01 (`thai_text`), 02 (new tables) · **Blocks:** 09 · **Parallel with:** 04, 05

## Goal
Make the golden customers verifiable by phone in every format the plan lists (plain, dropped leading
zero, `+66`, Thai digits, hyphenated, shared), with `C-0001` matching the Phase 1 example
`ออเดอร์ BC-1042 เบอร์ 0812345678`. Add raw sheet-style rows (Thai numerals, Buddhist-Era dates) that must
normalize to golden records. No id, order, price, date or tracking number changes.

## Files
| Path | Action | Purpose |
|---|---|---|
| `seed/golden.py` | modify | phones of the 9 golden customers; new `GOLDEN_RAW_SHEET_ROWS` |
| `seed/load.py` | modify | `DELETE_ORDER` also clears the two new tables |
| `tests/test_seed_dataset.py` | modify | phone tests replaced, raw-row test added |
| `tests/integration/test_seed_load.py` | modify | re-seed clears verification state |

## Interfaces
`seed/golden.py` — change only the `phone` argument of `GOLDEN_CUSTOMERS`:

| shop | customer | phone stored (exactly) | variant | normalized | last 4 |
|---|---|---|---|---|---|
| baan-bai-cha | C-0001 | `0812345678` | plain | `0812345678` | `5678` |
| baan-bai-cha | C-0002 | `823456789` | leading zero dropped (Excel) | `0823456789` | `6789` |
| baan-bai-cha | C-0003 | `+66834567890` | international | `0834567890` | `7890` |
| baan-bai-cha | C-0004 | `084-555-0104` | hyphenated, shared | `0845550104` | `0104` |
| baan-bai-cha | C-0005 | `084-555-0104` | shared with C-0004 | `0845550104` | `0104` |
| baan-bai-cha | C-0006 | `๐๘๖๕๕๕๐๑๐๖` | Thai digits | `0865550106` | `0106` |
| baan-bai-cha | C-0007 | `+66 87 555 0107` | international with spaces | `0875550107` | `0107` |
| shop-b | C-0001 | `091-555-0201` | unchanged | `0915550201` | `0201` |
| shop-b | C-0002 | `092-555-0202` | unchanged | `0925550202` | `0202` |

The stored values are deliberately **not** normalized: verification must work on what a sheet delivers.
`shop-b`'s `BC-1042` owner keeps a phone different from `0812345678`, so the demo prompt fails in `shop-b`.

Add after `GOLDEN_SHIPMENTS`:
```python
# Rows as a Google Sheet would deliver them (Phase 2 sync input). Each must normalize, via
# supportkit.core.thai_text, to the golden baan-bai-cha order with the same order number.
GOLDEN_RAW_SHEET_ROWS = [
    {"order_no": "bc 1042", "customer_phone": "812345678", "ordered_at": "12/11/2569"},
    {"order_no": "BC1043", "customer_phone": "๐๘๑๒๓๔๕๖๗๘", "ordered_at": "๑๔ พ.ย. ๒๕๖๙"},
    {"order_no": "#bc-1050", "customer_phone": "+66 82 345 6789", "ordered_at": "4 พฤศจิกายน พ.ศ. 2569"},
    {"order_no": "BC-1091", "customer_phone": "087-555-0107", "ordered_at": "2026-11-13"},
]
```

`seed/load.py`:
```python
DELETE_ORDER = (
    "verification_failures",
    "conversations",
    "refund_requests",
    "shipments",
    "order_items",
    "orders",
    "customer_identities",
    "products",
    "customers",
)
```

## Behaviour
1. `seed/bulk.py` is not touched; bulk phones keep the `0NN-555-NNNN` shape and the RNG sequence is unchanged, so every bulk row stays byte-identical.
2. `seed/` must not import `supportkit` (unchanged rule); only the tests import `thai_text`.
3. Re-seeding deletes the two seed shops' identity links, verification failures and conversation rows. Checkpoints are not touched: a demo thread that was verified before a re-seed loses access on its next turn through `prepare` revalidation (spec 06).

## Tests
`tests/test_seed_dataset.py`:
- Delete `test_every_phone_has_the_fake_format`.
- Keep `test_shared_phone_for_c0004_and_c0005`.
- Add:

| Test | Assertion |
|---|---|
| `test_golden_phones_exact` | the nine `(shop_id, customer_id) → phone` pairs equal column 3 of the table above |
| `test_golden_phones_normalize` | for the nine rows, `normalize_phone(phone)` and `phone_last4(phone)` equal columns 5 and 6 |
| `test_demo_anchor_phone` | `baan-bai-cha` `C-0001` phone is `"0812345678"`; `shop-b` `C-0001` (owner of `shop-b`'s `BC-1042`) has `phone_last4 != "5678"` |
| `test_bulk_phones_keep_fake_format` | every customer whose id starts with `C-1` matches `^0\d{2}-555-\d{4}$` |
| `test_every_phone_is_normalizable` | `normalize_phone(c["phone"]) is not None` for all customers of both shops |
| `test_raw_sheet_rows_normalize_to_golden` | for each row of `GOLDEN_RAW_SHEET_ROWS`: `normalize_order_no(row["order_no"])` is the `order_no` of a `baan-bai-cha` golden order; `normalize_phone(row["customer_phone"]) == normalize_phone(<that order's customer's phone>)`; `parse_thai_date(row["ordered_at"]) == order["ordered_at"].astimezone(BANGKOK).date()` |
| `test_build_dataset_is_deterministic` | unchanged, still passes |

`tests/integration/test_seed_load.py` — add `test_reseed_clears_verification_state(database_url)`:
insert into `customer_identities` `('baan-bai-cha','web','seedtest-u1','C-0001')`, into
`verification_failures` `('baan-bai-cha','web','seedtest-u1','BC-1042')`, into `conversations`
`('baan-bai-cha','baan-bai-cha:web:seedtest-u1')`, and one `conversations` row for a shop id
`t-seed-<hex>`; run `seed_database`; the three `baan-bai-cha` rows are gone, the `t-seed-*` row is still
there (delete it in `finally`).

## Acceptance
```powershell
.\.venv\Scripts\ruff.exe check src tests db seed evals ui
.\.venv\Scripts\supportkit.exe seed            # same row counts as before (customers 67, orders 218, ...)
$env:LANGGRAPH_STRICT_MSGPACK='true'; .\.venv\Scripts\python.exe -m pytest -q     # whole suite green
.\.venv\Scripts\supportkit.exe eval --require-all                                # still 10/10
```
`docker compose exec db psql -U supportkit -c "select customer_id, phone from customers where shop_id='baan-bai-cha' and customer_id like 'C-000%' order by 1"` shows the seven phones of the table.

## Out of scope
- `seed/bulk.py`, any order/shipment/product value, `ui/demo_chat.py` (spec 08), eval cases (spec 09).
- Normalizing phones at seed time; a sheet sync (Phase 2).
