import pytest

from supportkit.core.text import detect_language


@pytest.mark.parametrize(
    "text,expected",
    [
        ("ออเดอร์ BC-1042 ถึงไหนแล้วคะ", "th"),
        ("Where is my order BC-1042?", "en"),
        ("", "en"),
        ("BC-1042 ค่ะ", "th"),
        ("ออเดอร์ BC-1042 สถานะ: จัดส่งแล้วค่ะ จัดส่งโดย Kerry Express เลขพัสดุ KEX26111042TH", "th"),
    ],
)
def test_detect_language(text, expected):
    assert detect_language(text) == expected
