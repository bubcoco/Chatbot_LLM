"""Thai text normalization: digits, phone numbers, order and tracking numbers, Buddhist-Era dates.

Stdlib only. Nothing here imports from supportkit. No function raises on any str input.
"""

import re
from datetime import date

_THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")

_PHONE_CHARS_RE = re.compile(r"[0-9 \-.()+]*", re.ASCII)
_NON_DIGIT_RE = re.compile(r"[^0-9]")
_FOUR_DIGITS_RE = re.compile(r"[0-9]{4}", re.ASCII)
_MOBILE_RE = re.compile(r"0[689][0-9]{8}", re.ASCII)
_LANDLINE_RE = re.compile(r"0[2-57][0-9]{7}", re.ASCII)
_ORDER_RE = re.compile(r"([A-Z]{1,6})-?([0-9]{1,12})", re.ASCII)
_TRACKING_RE = re.compile(r"[A-Z0-9]{8,24}", re.ASCII)

_DATE_ISO_RE = re.compile(r"([0-9]{4})-([0-9]{1,2})-([0-9]{1,2})", re.ASCII)
_DATE_NUMERIC_RE = re.compile(r"([0-9]{1,2})[/.-]([0-9]{1,2})[/.-]([0-9]{4})", re.ASCII)
_DATE_NAMED_RE = re.compile(r"([0-9]{1,2}) ?([^0-9]+?) ?([0-9]{4})", re.ASCII)

_BE_MARKERS = ("พ.ศ.", "พศ")
_CE_MARKERS = ("ค.ศ.", "คศ")

_MONTHS: dict[str, int] = {
    "มกราคม": 1,
    "ม.ค.": 1,
    "กุมภาพันธ์": 2,
    "ก.พ.": 2,
    "มีนาคม": 3,
    "มี.ค.": 3,
    "เมษายน": 4,
    "เม.ย.": 4,
    "พฤษภาคม": 5,
    "พ.ค.": 5,
    "มิถุนายน": 6,
    "มิ.ย.": 6,
    "กรกฎาคม": 7,
    "ก.ค.": 7,
    "สิงหาคม": 8,
    "ส.ค.": 8,
    "กันยายน": 9,
    "ก.ย.": 9,
    "ตุลาคม": 10,
    "ต.ค.": 10,
    "พฤศจิกายน": 11,
    "พ.ย.": 11,
    "ธันวาคม": 12,
    "ธ.ค.": 12,
}


def to_arabic_digits(text: str) -> str:
    """Translate Thai digits to 0-9; every other character is unchanged."""
    return text.translate(_THAI_DIGITS)


def normalize_phone(raw: str) -> str | None:
    """Domestic digits-only form of a Thai phone number, or None."""
    s = to_arabic_digits(raw).strip()
    if _PHONE_CHARS_RE.fullmatch(s) is None or "+" in s[1:]:
        return None
    d = _NON_DIGIT_RE.sub("", s)
    country_removed = False
    if s.startswith("+"):
        if not d.startswith("66"):
            return None
        d = d[2:]
        country_removed = True
    elif d.startswith("0066"):
        d = d[4:]
        country_removed = True
    elif d.startswith("66") and len(d) in (10, 11):
        d = d[2:]
        country_removed = True
    if country_removed:
        d = "0" + d.removeprefix("0")
    elif not d.startswith("0") and len(d) in (8, 9):
        d = "0" + d
    if _MOBILE_RE.fullmatch(d) or _LANDLINE_RE.fullmatch(d):
        return d
    return None


def phone_last4(raw: str) -> str | None:
    """The last four digits of a phone number, or the input itself if it is exactly four digits."""
    s = to_arabic_digits(raw).strip()
    if _FOUR_DIGITS_RE.fullmatch(s):
        return s
    n = normalize_phone(raw)
    return n[-4:] if n is not None else None


def normalize_order_no(raw: str) -> str | None:
    """Canonical PREFIX-DIGITS order number, or None."""
    s = to_arabic_digits(raw).strip().removeprefix("#")
    s = "".join(s.split()).upper()
    m = _ORDER_RE.fullmatch(s)
    return f"{m.group(1)}-{m.group(2)}" if m else None


def normalize_tracking_no(raw: str) -> str | None:
    """Upper-case tracking number without spaces or hyphens, or None."""
    s = "".join(to_arabic_digits(raw).split()).replace("-", "").upper()
    if _TRACKING_RE.fullmatch(s) and any(c.isdigit() for c in s):
        return s
    return None


def be_to_ce(year: int) -> int:
    return year - 543


def ce_to_be(year: int) -> int:
    return year + 543


def parse_thai_date(raw: str) -> date | None:
    """Whole-string date parser for sheet cells; returns a Gregorian date or None."""
    s = to_arabic_digits(raw).strip()
    era: str | None = None
    if any(m in s for m in _BE_MARKERS):
        era, markers = "be", _BE_MARKERS
    elif any(m in s for m in _CE_MARKERS):
        era, markers = "ce", _CE_MARKERS
    else:
        markers = ()
    for marker in markers:
        s = s.replace(marker, " ")
    s = " ".join(s.split())

    if m := _DATE_ISO_RE.fullmatch(s):
        year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
    elif m := _DATE_NUMERIC_RE.fullmatch(s):
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
    elif m := _DATE_NAMED_RE.fullmatch(s):
        month_no = _MONTHS.get(m.group(2).strip())
        if month_no is None:
            return None
        day, month, year = int(m.group(1)), month_no, int(m.group(3))
    else:
        return None

    if era == "be" or (era is None and year >= 2400):
        year = be_to_ce(year)
    if not 1900 <= year <= 2200:
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None
