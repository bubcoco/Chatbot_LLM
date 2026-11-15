"""DEMO ONLY — trusts caller-supplied identity. Replaced by verified channel identity in Phase 2/3. Never import this outside api/chat.py.

All X-Demo-* header handling lives here. Callers only ever see a SupportContext.
"""

import re
from typing import Annotated

import psycopg
from fastapi import Header, HTTPException, Request

from supportkit.core.graph.state import SupportContext, bangkok_now
from supportkit.core.tenancy import repositories
from supportkit.core.tenancy.context import CUSTOMER_ID_RE, SHOP_ID_RE, TenantContext

SESSION_RE = re.compile(r"^[A-Za-z0-9]{8,32}$")


async def demo_context(
    request: Request,
    x_demo_shop_id: Annotated[str | None, Header()] = None,
    x_demo_customer_id: Annotated[str | None, Header()] = None,
    x_demo_session: Annotated[str | None, Header()] = None,
) -> SupportContext:
    shop = x_demo_shop_id
    session = x_demo_session
    customer = x_demo_customer_id or None  # empty string counts as absent
    if (
        not shop
        or not session
        or not SHOP_ID_RE.fullmatch(shop)
        or not SESSION_RE.fullmatch(session)
        or (customer is not None and not CUSTOMER_ID_RE.fullmatch(customer))
    ):
        raise HTTPException(400, "invalid_demo_identity")

    try:
        async with request.app.state.runtime.pool.connection() as conn:
            if customer is not None:
                known = await repositories.customer_exists(conn, TenantContext(shop, customer))
            else:
                known = await repositories.shop_has_customers(conn, shop)
    except psycopg.OperationalError:
        raise HTTPException(503, "database_unavailable") from None
    if not known:
        raise HTTPException(403, "unknown_demo_identity")

    return SupportContext(
        shop_id=shop,
        channel="web",
        channel_user_id=f"demo-{customer or 'guest'}-{session}",
        customer_id=customer,
        now=bangkok_now(),
    )
