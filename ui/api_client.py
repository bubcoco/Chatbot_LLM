"""Tiny sync HTTP client for the supportkit demo API.

The Streamlit page talks to the API only through this module. It holds no
business logic and never touches the database or the graph.
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from typing import Any

import httpx

DEFAULT_API_URL = "http://127.0.0.1:8000"
_TIMEOUT_SECONDS = 60.0
_SESSION_RE = re.compile(r"[A-Za-z0-9]{8,32}")


@dataclass(frozen=True)
class DemoIdentity:
    shop_id: str
    customer_id: str | None  # None = guest (unverified)
    session: str  # ^[A-Za-z0-9]{8,32}$


class ChatApiError(Exception):
    def __init__(self, status_code: int | None, detail: str):
        super().__init__(f"{status_code}: {detail}")
        self.status_code = status_code  # None = could not connect
        self.detail = detail


def new_session_id() -> str:
    return secrets.token_hex(8)


def is_valid_session(value: str) -> bool:
    return _SESSION_RE.fullmatch(value) is not None


def identity_headers(identity: DemoIdentity) -> dict[str, str]:
    headers = {
        "X-Demo-Shop-Id": identity.shop_id,
        "X-Demo-Session": identity.session,
    }
    if identity.customer_id is not None:
        headers["X-Demo-Customer-Id"] = identity.customer_id
    return headers


def _raise_for_status(response: httpx.Response) -> None:
    if response.is_success:
        return
    detail = f"HTTP {response.status_code}"
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict) and isinstance(body.get("detail"), str):
        detail = body["detail"]
    raise ChatApiError(response.status_code, detail)


def _request(
    method: str,
    base_url: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    json: Any = None,
    client: httpx.Client | None,
) -> dict | list:
    def _do(c: httpx.Client) -> dict | list:
        try:
            response = c.request(method, f"{base_url}{path}", headers=headers, json=json)
        except httpx.HTTPError as exc:
            raise ChatApiError(None, "cannot reach API") from exc
        _raise_for_status(response)
        return response.json()

    if client is not None:
        return _do(client)
    with httpx.Client(timeout=_TIMEOUT_SECONDS) as own_client:
        return _do(own_client)


def send_message(
    base_url: str,
    identity: DemoIdentity,
    message: str,
    *,
    client: httpx.Client | None = None,
) -> dict:
    result = _request(
        "POST",
        base_url,
        "/chat",
        headers=identity_headers(identity),
        json={"message": message},
        client=client,
    )
    return result  # type: ignore[return-value]


def fetch_history(
    base_url: str,
    identity: DemoIdentity,
    *,
    client: httpx.Client | None = None,
) -> list[dict]:
    result = _request(
        "GET",
        base_url,
        "/chat/history",
        headers=identity_headers(identity),
        client=client,
    )
    return result["messages"]  # type: ignore[index,return-value]


def fetch_health(base_url: str, *, client: httpx.Client | None = None) -> dict:
    result = _request("GET", base_url, "/health", client=client)
    return result  # type: ignore[return-value]
