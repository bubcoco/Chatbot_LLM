from datetime import date

import pytest

from supportkit.core import thai_text
from supportkit.core.thai_text import (
    be_to_ce,
    ce_to_be,
    normalize_order_no,
    normalize_phone,
    normalize_tracking_no,
    parse_thai_date,
    phone_last4,
    to_arabic_digits,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("๐๑๒๓๔๕๖๗๘๙", "0123456789"),
        ("BC-๑๐๔๒ ค่ะ", "BC-1042 ค่ะ"),
        ("", ""),
        ("abc 12", "abc 12"),
    ],
)
def test_to_arabic_digits(raw, expected):
    assert to_arabic_digits(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0812345678", "0812345678"),
        ("081-234-5678", "0812345678"),
        (" 081 234 5678 ", "0812345678"),
        ("(081) 234.5678", "0812345678"),
        ("๐๘๑๒๓๔๕๖๗๘", "0812345678"),
        ("812345678", "0812345678"),
        ("+66812345678", "0812345678"),
        ("+66 81 234 5678", "0812345678"),
        ("+66 (0)81 234 5678", "0812345678"),
        ("0066812345678", "0812345678"),
        ("66812345678", "0812345678"),
        ("0612345678", "0612345678"),
        ("0912345678", "0912345678"),
        ("021234567", "021234567"),
        ("02-123-4567", "021234567"),
        ("21234567", "021234567"),
        ("+6621234567", "021234567"),
        ("6621234567", "021234567"),
        ("053123456", "053123456"),
        ("53123456", "053123456"),
        ("081234567", None),
        ("08123456789", None),
        ("0112345678", None),
        ("212345678", None),
        ("81234567", None),
        ("12345678", None),
        ("1234", None),
        ("", None),
        ("   ", None),
        ("+1 415 555 0100", None),
        ("+81312345678", None),
        ("081-234-5678 ext 2", None),
        ("08+12345678", None),
        ("abc", None),
        ("ออเดอร์", None),
    ],
)
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("5678", "5678"),
        (" 5678 ", "5678"),
        ("๕๖๗๘", "5678"),
        ("0812345678", "5678"),
        ("812345678", "5678"),
        ("+66 81 234 5678", "5678"),
        ("๐๘๑๒๓๔๕๖๗๘", "5678"),
        ("084-555-0104", "0104"),
        ("678", None),
        ("45678", None),
        ("12345678", None),
        ("56-78", None),
        ("abcd", None),
        ("", None),
    ],
)
def test_phone_last4(raw, expected):
    assert phone_last4(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("BC-1042", "BC-1042"),
        (" bc-1042 ", "BC-1042"),
        ("#BC-1042", "BC-1042"),
        ("# bc-1042", "BC-1042"),
        ("BC1042", "BC-1042"),
        ("bc1042", "BC-1042"),
        ("BC 1042", "BC-1042"),
        ("bc - 1042", "BC-1042"),
        ("BC-๑๐๔๒", "BC-1042"),
        ("#bc๑๐๔๒", "BC-1042"),
        ("A-1", "A-1"),
        ("ABCDEF-123456789012", "ABCDEF-123456789012"),
        ("", None),
        ("  ", None),
        ("ab", None),
        ("1042", None),
        ("BC-", None),
        ("BC--1042", None),
        ("##BC-1042", None),
        ("BC-1042-1", None),
        ("ABCDEFG-1", None),
        ("BC-1234567890123", None),
        ("BC-1042'; DROP TABLE orders;--", None),
        ("ออเดอร์", None),
        ("A" * 21, None),
        ("B_C-1042", None),
    ],
)
def test_normalize_order_no(raw, expected):
    assert normalize_order_no(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("KEX26111042TH", "KEX26111042TH"),
        ("kex 2611-1042 th", "KEX26111042TH"),
        (" KEX26111042TH ", "KEX26111042TH"),
        ("JT๒๖๑๑๙๙๐๐๔๒", "JT2611990042"),
        ("ABC1234", None),
        ("A" * 25, None),
        ("ABCDEFGH", None),
        ("KEX_26111042", None),
        ("", None),
    ],
)
def test_normalize_tracking_no(raw, expected):
    assert normalize_tracking_no(raw) == expected


def test_era_conversion():
    assert be_to_ce(2569) == 2026
    assert ce_to_be(2026) == 2569


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-11-12", date(2026, 11, 12)),
        ("2026-11-5", date(2026, 11, 5)),
        ("2569-11-12", date(2026, 11, 12)),
        ("12/11/2569", date(2026, 11, 12)),
        ("12-11-2569", date(2026, 11, 12)),
        ("12.11.2569", date(2026, 11, 12)),
        ("๑๒/๑๑/๒๕๖๙", date(2026, 11, 12)),
        ("12/11/2026", date(2026, 11, 12)),
        ("14 พ.ย. 2569", date(2026, 11, 14)),
        ("14 พฤศจิกายน 2569", date(2026, 11, 14)),
        ("14พ.ย.2569", date(2026, 11, 14)),
        ("๑๔ พ.ย. ๒๕๖๙", date(2026, 11, 14)),
        ("14 พ.ย. 2026", date(2026, 11, 14)),
        ("4 พฤศจิกายน พ.ศ. 2569", date(2026, 11, 4)),
        ("4 พ.ย. พศ 2569", date(2026, 11, 4)),
        ("4/11/2569 พ.ศ.", date(2026, 11, 4)),
        ("4 พ.ย. ค.ศ. 2026", date(2026, 11, 4)),
        ("ค.ศ. 2026-11-04", date(2026, 11, 4)),
        ("4/11/2026 คศ", date(2026, 11, 4)),
        ("29/02/2567", date(2024, 2, 29)),
        ("29/02/2569", None),
        ("31/04/2569", None),
        ("12/13/2569", None),
        ("0/11/2569", None),
        ("พ.ศ. 2026-11-12", None),
        ("ค.ศ. 2569-11-12", None),
        ("12/11/1899", None),
        ("12/11/2399", None),
        ("12/11/69", None),
        ("14 Nov 2026", None),
        ("14 xx 2569", None),
        ("พ.ย. 2569", None),
        ("2026-11", None),
        ("", None),
        ("ออเดอร์", None),
    ],
)
def test_parse_thai_date(raw, expected):
    assert parse_thai_date(raw) == expected


# Literal expectations, independent of thai_text._MONTHS, so a swapped month is caught.
THAI_MONTHS = [
    ("มกราคม", 1), ("ม.ค.", 1), ("กุมภาพันธ์", 2), ("ก.พ.", 2),
    ("มีนาคม", 3), ("มี.ค.", 3), ("เมษายน", 4), ("เม.ย.", 4),
    ("พฤษภาคม", 5), ("พ.ค.", 5), ("มิถุนายน", 6), ("มิ.ย.", 6),
    ("กรกฎาคม", 7), ("ก.ค.", 7), ("สิงหาคม", 8), ("ส.ค.", 8),
    ("กันยายน", 9), ("ก.ย.", 9), ("ตุลาคม", 10), ("ต.ค.", 10),
    ("พฤศจิกายน", 11), ("พ.ย.", 11), ("ธันวาคม", 12), ("ธ.ค.", 12),
]


@pytest.mark.parametrize(("name", "number"), THAI_MONTHS)
def test_parse_thai_date_month_names(name, number):
    assert parse_thai_date(f"1 {name} 2569") == date(2026, number, 1)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("25พ.ศ.69-11-12", None), ("4/11/2569 พ.ศ. ค.ศ.", None)],
)
def test_parse_thai_date_marker_edge_cases(raw, expected):
    assert parse_thai_date(raw) == expected


def test_order_no_unicode_upper_folding_is_pinned():
    # str.upper() folds 'ß' to 'SS'; harmless (canonical output, bound parameter). Pinned on purpose.
    assert thai_text.normalize_order_no("ß-1") == "SS-1"


def test_months_table_is_complete():
    assert dict(THAI_MONTHS) == thai_text._MONTHS
    assert len(thai_text._MONTHS) == 24
    assert set(thai_text._MONTHS.values()) == set(range(1, 13))
