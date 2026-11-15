"""Small text helpers."""

from typing import Literal


def detect_language(text: str) -> Literal["th", "en"]:
    """Return "th" if Thai characters make up at least 30% of Thai + ASCII letters."""
    thai = sum(1 for ch in text if "\u0e00" <= ch <= "\u0e7f")
    latin = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    return "th" if thai > 0 and thai >= 0.3 * (thai + latin) else "en"
