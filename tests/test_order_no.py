import pytest

from supportkit.core import thai_text
from supportkit.core.tools import orders


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("BC-1042", "BC-1042"),
        (" bc-1042 ", "BC-1042"),
        ("#BC-1042", "BC-1042"),
        ("BC1042", "BC-1042"),
        ("BC 1042", "BC-1042"),
    ],
)
def test_valid(raw, expected):
    assert orders.normalize_order_no(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["", "  ", "ab", "BC-1042'; DROP TABLE orders;--", "ออเดอร์", "A" * 21],
)
def test_invalid(raw):
    assert orders.normalize_order_no(raw) is None


def test_orders_uses_thai_text_normalizer():
    assert orders.normalize_order_no is thai_text.normalize_order_no
