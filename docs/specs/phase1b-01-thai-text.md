# Phase 1b · Spec 01 — `thai_text.py` normalizer (100% coverage)

**Suggested implementer:** `implementer` (pure functions, but phone and order-number rules feed identity verification)
**Depends on:** — · **Blocks:** 03, 05, 07 · **Parallel with:** 02

## Goal
One stdlib-only module that normalizes Thai digits, phone numbers, order numbers, tracking numbers and
Buddhist-Era dates, with 100% line and branch coverage. The order tool switches to it, so there is one
order-number rule in the codebase. Rules are fixed by `phase1b-plan-amendments.md` issues 1 and 8.

## Files
| Path | Action | Purpose |
|---|---|---|
| `src/supportkit/core/thai_text.py` | create | the normalizer; imports nothing from `supportkit` |
| `tests/test_thai_text.py` | create | table-driven unit tests |
| `src/supportkit/core/tools/orders.py` | modify | delete local `ORDER_NO_RE` and `normalize_order_no`; add `from supportkit.core.thai_text import normalize_order_no` (the name stays importable from `orders`) |
| `tests/test_order_no.py` | modify | new expectations (below) |
| `pyproject.toml`, `uv.lock` | modify | `python -m uv add --dev pytest-cov` |
| `.github/workflows/ci.yml` | modify | add the coverage step (below) after "Tests" |

## Interfaces
```python
# src/supportkit/core/thai_text.py
from datetime import date

def to_arabic_digits(text: str) -> str: ...
def normalize_phone(raw: str) -> str | None: ...
def phone_last4(raw: str) -> str | None: ...
def normalize_order_no(raw: str) -> str | None: ...
def normalize_tracking_no(raw: str) -> str | None: ...
def be_to_ce(year: int) -> int: ...        # year - 543
def ce_to_be(year: int) -> int: ...        # year + 543
def parse_thai_date(raw: str) -> date | None: ...
```
Module constants (private): `_THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")`,
`_MOBILE_RE = r"0[689]\d{8}"`, `_LANDLINE_RE = r"0[2-57]\d{7}"`,
`_ORDER_RE = r"([A-Z]{1,6})-?(\d{1,12})"`, `_TRACKING_RE = r"[A-Z0-9]{8,24}"`, and `_MONTHS`:

| # | full | abbreviated |
|---|---|---|
| 1 | มกราคม | ม.ค. |
| 2 | กุมภาพันธ์ | ก.พ. |
| 3 | มีนาคม | มี.ค. |
| 4 | เมษายน | เม.ย. |
| 5 | พฤษภาคม | พ.ค. |
| 6 | มิถุนายน | มิ.ย. |
| 7 | กรกฎาคม | ก.ค. |
| 8 | สิงหาคม | ส.ค. |
| 9 | กันยายน | ก.ย. |
| 10 | ตุลาคม | ต.ค. |
| 11 | พฤศจิกายน | พ.ย. |
| 12 | ธันวาคม | ธ.ค. |

CI step:
```yaml
      - name: thai_text coverage (must be 100%)
        run: .venv/bin/python -m pytest -q tests/test_thai_text.py --cov=supportkit.core.thai_text --cov-branch --cov-fail-under=100
```

## Behaviour
All regexes are applied with `re.fullmatch`. No function raises on any `str` input.

**`to_arabic_digits`** — 1. Translate U+0E50–U+0E59 to `0`–`9`; every other character is unchanged.

**`normalize_phone`** — returns the domestic form, digits only, or `None`.
2. `s = to_arabic_digits(raw).strip()`. If `s` contains a character other than digits, space, `-`, `.`,
   `(`, `)`, `+`, or contains `+` anywhere but position 0 → `None`.
3. `d` = the digits of `s`.
4. Country code, first matching branch only:
   a. `s` starts with `+`: if `d` does not start with `66` → `None`; else `d = d[2:]`, country code removed.
   b. `d` starts with `0066`: `d = d[4:]`, country code removed.
   c. `d` starts with `66` and `len(d) in (10, 11)`: `d = d[2:]`, country code removed.
   If a country code was removed: drop one leading `0` from `d` if present, then `d = "0" + d`.
5. Else, if `d` does not start with `0` and `len(d) in (8, 9)`: `d = "0" + d`.
6. Return `d` if it matches `_MOBILE_RE` or `_LANDLINE_RE`, else `None`.

**`phone_last4`**
7. `s = to_arabic_digits(raw).strip()`. If `s` is exactly four digits → `s`.
8. Otherwise `n = normalize_phone(raw)`; return `n[-4:]` if `n` is not `None`, else `None`.

**`normalize_order_no`** — returns `PREFIX-DIGITS` or `None`.
9. `s = to_arabic_digits(raw).strip()`; remove one leading `#` (`removeprefix`); delete all whitespace
   (`"".join(s.split())`); upper-case.
10. If `s` matches `_ORDER_RE` → `f"{letters}-{digits}"`, else `None`. (Max length 19.)

**`normalize_tracking_no`**
11. `to_arabic_digits`, delete all whitespace and `-`, upper-case. Return it if it matches `_TRACKING_RE`
    and contains at least one digit, else `None`.

**`parse_thai_date`** — a whole-string parser for sheet cells; returns a Gregorian `date` or `None`.
12. `s = to_arabic_digits(raw).strip()`.
13. Era marker: if `s` contains `พ.ศ.` or `พศ` → era `"be"`; else if it contains `ค.ศ.` or `คศ` → era
    `"ce"`; else era `None`. Remove the marker, then collapse whitespace runs to one space and strip.
14. Match, in this order:
    a. `(\d{4})-(\d{1,2})-(\d{1,2})` → year, month, day.
    b. `(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})` → day, month, year (Thai order is day first).
    c. `(\d{1,2}) ?(\D+?) ?(\d{4})` → day, month name, year; the name (stripped) must be a key of
       `_MONTHS` (full or abbreviated), else `None`.
    No match → `None`.
15. Year: era `"be"` → `be_to_ce(year)`; era `"ce"` → unchanged; no era → `be_to_ce(year)` if
    `year >= 2400`, else unchanged. If the resulting year is outside 1900–2200 → `None`.
16. `date(year, month, day)`; on `ValueError` → `None`.
17. Two-digit years are not accepted (they fall through to `None`); the sync job will decide per shop.

## Tests
`tests/test_thai_text.py`, `pytest.mark.parametrize` tables. Every row below is one case.

`to_arabic_digits`: `"๐๑๒๓๔๕๖๗๘๙"` → `"0123456789"`; `"BC-๑๐๔๒ ค่ะ"` → `"BC-1042 ค่ะ"`; `""` → `""`; `"abc 12"` → unchanged.

`normalize_phone`
| Input | Expected |
|---|---|
| `"0812345678"`, `"081-234-5678"`, `" 081 234 5678 "`, `"(081) 234.5678"`, `"๐๘๑๒๓๔๕๖๗๘"` | `"0812345678"` |
| `"812345678"` (Excel) | `"0812345678"` |
| `"+66812345678"`, `"+66 81 234 5678"`, `"+66 (0)81 234 5678"`, `"0066812345678"`, `"66812345678"` | `"0812345678"` |
| `"0612345678"`, `"0912345678"` | unchanged |
| `"021234567"`, `"02-123-4567"`, `"21234567"`, `"+6621234567"`, `"6621234567"` | `"021234567"` |
| `"053123456"`, `"53123456"` | `"053123456"` |
| `"081234567"` (9 digits, starts 08), `"08123456789"` (11), `"0112345678"` (01), `"212345678"` (9 digits, starts 2), `"81234567"` (8 digits, starts 8), `"12345678"`, `"1234"`, `""`, `"   "` | `None` |
| `"+1 415 555 0100"`, `"+81312345678"`, `"081-234-5678 ext 2"`, `"08+12345678"`, `"abc"`, `"ออเดอร์"` | `None` |

`phone_last4`
| Input | Expected |
|---|---|
| `"5678"`, `" 5678 "`, `"๕๖๗๘"` | `"5678"` |
| `"0812345678"`, `"812345678"`, `"+66 81 234 5678"`, `"๐๘๑๒๓๔๕๖๗๘"` | `"5678"` |
| `"084-555-0104"` | `"0104"` |
| `"678"`, `"45678"`, `"12345678"`, `"56-78"`, `"abcd"`, `""` | `None` |

`normalize_order_no`
| Input | Expected |
|---|---|
| `"BC-1042"`, `" bc-1042 "`, `"#BC-1042"`, `"# bc-1042"`, `"BC1042"`, `"bc1042"`, `"BC 1042"`, `"bc - 1042"`, `"BC-๑๐๔๒"`, `"#bc๑๐๔๒"` | `"BC-1042"` |
| `"A-1"` | `"A-1"` |
| `"ABCDEF-123456789012"` | unchanged |
| `""`, `"  "`, `"ab"`, `"1042"`, `"BC-"`, `"BC--1042"`, `"##BC-1042"`, `"BC-1042-1"`, `"ABCDEFG-1"`, `"BC-1234567890123"`, `"BC-1042'; DROP TABLE orders;--"`, `"ออเดอร์"`, `"A" * 21`, `"B_C-1042"` | `None` |

`normalize_tracking_no`
| Input | Expected |
|---|---|
| `"KEX26111042TH"`, `"kex 2611-1042 th"`, `" KEX26111042TH "` | `"KEX26111042TH"` |
| `"JT๒๖๑๑๙๙๐๐๔๒"` | `"JT2611990042"` |
| `"ABC1234"` (7), `"A" * 25`, `"ABCDEFGH"` (no digit), `"KEX_26111042"`, `""` | `None` |

`be_to_ce(2569) == 2026`; `ce_to_be(2026) == 2569`.

`parse_thai_date`
| Input | Expected |
|---|---|
| `"2026-11-12"`, `"2026-11-5"` | `date(2026,11,12)`, `date(2026,11,5)` |
| `"2569-11-12"` | `date(2026,11,12)` |
| `"12/11/2569"`, `"12-11-2569"`, `"12.11.2569"`, `"๑๒/๑๑/๒๕๖๙"`, `"12/11/2026"` | `date(2026,11,12)` |
| `"14 พ.ย. 2569"`, `"14 พฤศจิกายน 2569"`, `"14พ.ย.2569"`, `"๑๔ พ.ย. ๒๕๖๙"`, `"14 พ.ย. 2026"` | `date(2026,11,14)` |
| `"4 พฤศจิกายน พ.ศ. 2569"`, `"4 พ.ย. พศ 2569"`, `"4/11/2569 พ.ศ."` | `date(2026,11,4)` |
| `"4 พ.ย. ค.ศ. 2026"`, `"ค.ศ. 2026-11-04"`, `"4/11/2026 คศ"` | `date(2026,11,4)` |
| each of the 12 full names and 12 abbreviations as `f"1 {name} 2569"` (one parametrized test over `_MONTHS`) | `date(2026, n, 1)` |
| `"29/02/2567"` | `date(2024,2,29)` |
| `"29/02/2569"`, `"31/04/2569"`, `"12/13/2569"`, `"0/11/2569"` | `None` |
| `"พ.ศ. 2026-11-12"` (→ year 1483), `"ค.ศ. 2569-11-12"`, `"12/11/1899"`, `"12/11/2399"` | `None` |
| `"12/11/69"`, `"14 Nov 2026"`, `"14 xx 2569"`, `"พ.ย. 2569"`, `"2026-11"`, `""`, `"ออเดอร์"` | `None` |

`tests/test_order_no.py` — replace the table with:
| Input | Expected |
|---|---|
| `"BC-1042"`, `" bc-1042 "`, `"#BC-1042"`, `"BC1042"`, `"BC 1042"` | `"BC-1042"` |
| `""`, `"  "`, `"ab"`, `"BC-1042'; DROP TABLE orders;--"`, `"ออเดอร์"`, `"A" * 21` | `None` |
and add `from supportkit.core.tools import orders; assert orders.normalize_order_no is thai_text.normalize_order_no`.
(Changed from Phase 1: `"BC1042"` used to stay `"BC1042"`, `"BC 1042"` used to be `None`.)

## Acceptance
```powershell
.\.venv\Scripts\ruff.exe check src tests db seed evals ui
$env:LANGGRAPH_STRICT_MSGPACK='true'; .\.venv\Scripts\python.exe -m pytest -q tests/test_thai_text.py --cov=supportkit.core.thai_text --cov-branch --cov-report=term-missing --cov-fail-under=100   # passes, 100%
$env:LANGGRAPH_STRICT_MSGPACK='true'; .\.venv\Scripts\python.exe -m pytest -q        # whole suite green
.\.venv\Scripts\supportkit.exe eval --require-all                                   # still 10/10
```
`rg -n "import" src/supportkit/core/thai_text.py` shows only `re` and `datetime`.
No `# pragma: no cover` anywhere in the module.

## Out of scope
- Number/price parsing, date extraction from free text, PII masking (`08x-xxx-1234`) — Phase 2 output guard.
- `core/text.py` (`detect_language`) stays where it is.
- `core/llm/fake.py` (spec 05), any tool behaviour other than the `normalize_order_no` import swap.
- Do not add dependencies other than `pytest-cov`.
