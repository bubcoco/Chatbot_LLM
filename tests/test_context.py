import dataclasses

import pytest

from supportkit.core.graph.state import SupportContext, bangkok_now, thread_id_for
from supportkit.core.tenancy.context import TenantContext

NOW = "2026-11-15T12:00:00+07:00"


def test_tenant_ok():
    TenantContext("baan-bai-cha", "C-0001")
    TenantContext("baan-bai-cha", None)


@pytest.mark.parametrize(
    "shop,cust",
    [("", "C-0001"), ("Shop B", "C-1"), ("shop:b", None), ("shop-b", ""), ("shop-b", "a b")],
)
def test_tenant_invalid(shop, cust):
    with pytest.raises(ValueError):
        TenantContext(shop, cust)


def test_support_context_ok():
    ctx = SupportContext("shop-b", "web", "demo-guest-abc12345", None, NOW)
    assert ctx.tenant == TenantContext("shop-b", None)


def test_support_context_invalid():
    with pytest.raises(ValueError):
        SupportContext("shop-b", "sms", "u1", None, NOW)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        SupportContext("shop-b", "web", "a:b", None, NOW)
    with pytest.raises(ValueError):
        SupportContext("Bad Shop", "web", "u1", None, NOW)
    with pytest.raises(ValueError):
        SupportContext("shop-b", "web", "u1", "a b", NOW)


def test_thread_id():
    ctx = SupportContext("baan-bai-cha", "web", "u1", "C-0001", NOW)
    assert thread_id_for(ctx) == "baan-bai-cha:web:u1"


def test_frozen():
    ctx = SupportContext("shop-b", "web", "u1", None, NOW)
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.shop_id = "x"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        dataclasses.replace(ctx).customer_id = "C-1"  # type: ignore[misc]
    t = TenantContext("shop-b", None)
    with pytest.raises(dataclasses.FrozenInstanceError):
        t.shop_id = "x"  # type: ignore[misc]


def test_bangkok_now():
    assert bangkok_now().endswith("+07:00")
