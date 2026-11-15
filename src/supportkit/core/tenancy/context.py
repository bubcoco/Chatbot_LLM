"""Tenant identity. Built server-side only; never from LLM output."""

import re
from dataclasses import dataclass

SHOP_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
CUSTOMER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


@dataclass(frozen=True, slots=True)
class TenantContext:
    shop_id: str
    customer_id: str | None  # None = identity not verified

    def __post_init__(self) -> None:
        if not isinstance(self.shop_id, str) or not SHOP_ID_RE.fullmatch(self.shop_id):
            raise ValueError(f"invalid shop_id: {self.shop_id!r}")
        if self.customer_id is not None and (
            not isinstance(self.customer_id, str) or not CUSTOMER_ID_RE.fullmatch(self.customer_id)
        ):
            raise ValueError(f"invalid customer_id: {self.customer_id!r}")
