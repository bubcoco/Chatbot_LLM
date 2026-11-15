import json

import httpx
import pytest

from ui import api_client
from ui.api_client import ChatApiError, DemoIdentity

BASE = "http://testserver"
IDENTITY = DemoIdentity("baan-bai-cha", "C-0001", "abcd1234")
GUEST = DemoIdentity("shop-b", None, "abcd1234")


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_identity_headers_with_customer():
    assert api_client.identity_headers(IDENTITY) == {
        "X-Demo-Shop-Id": "baan-bai-cha",
        "X-Demo-Session": "abcd1234",
        "X-Demo-Customer-Id": "C-0001",
    }


def test_identity_headers_guest_has_no_customer_header():
    headers = api_client.identity_headers(GUEST)
    assert headers == {"X-Demo-Shop-Id": "shop-b", "X-Demo-Session": "abcd1234"}
    assert "X-Demo-Customer-Id" not in headers


def test_send_message_posts_json_and_returns_body():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json={"reply": "ok", "thread_id": "t", "turn_id": "u"})

    result = api_client.send_message(BASE, IDENTITY, "สวัสดี", client=_client(handler))

    assert result == {"reply": "ok", "thread_id": "t", "turn_id": "u"}
    request = captured["request"]
    assert request.method == "POST"
    assert request.url.path == "/chat"
    assert json.loads(request.content) == {"message": "สวัสดี"}
    assert request.headers["X-Demo-Shop-Id"] == "baan-bai-cha"
    assert request.headers["X-Demo-Session"] == "abcd1234"
    assert request.headers["X-Demo-Customer-Id"] == "C-0001"


def test_fetch_history_returns_messages():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json={"thread_id": "t", "messages": [{"role": "user", "text": "hi"}]})

    result = api_client.fetch_history(BASE, IDENTITY, client=_client(handler))

    assert result == [{"role": "user", "text": "hi"}]
    assert captured["request"].method == "GET"
    assert captured["request"].url.path == "/chat/history"


def test_fetch_health_returns_body():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/health"
        return httpx.Response(200, json={"status": "ok", "model": "fake:rules", "demo_mode": True})

    result = api_client.fetch_health(BASE, client=_client(handler))

    assert result == {"status": "ok", "model": "fake:rules", "demo_mode": True}


def test_403_uses_detail_string():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"detail": "unknown_demo_identity"})

    with pytest.raises(ChatApiError) as info:
        api_client.send_message(BASE, IDENTITY, "x", client=_client(handler))

    assert info.value.status_code == 403
    assert info.value.detail == "unknown_demo_identity"


def test_422_with_non_string_detail_falls_back_to_http_status():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"detail": [{"msg": "x"}]})

    with pytest.raises(ChatApiError) as info:
        api_client.send_message(BASE, IDENTITY, "x", client=_client(handler))

    assert info.value.status_code == 422
    assert info.value.detail == "HTTP 422"


def test_connect_error_maps_to_unreachable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    with pytest.raises(ChatApiError) as info:
        api_client.fetch_history(BASE, IDENTITY, client=_client(handler))

    assert info.value.status_code is None
    assert info.value.detail == "cannot reach API"


def test_new_session_id_is_unique_and_valid():
    first = api_client.new_session_id()
    second = api_client.new_session_id()

    assert first != second
    assert api_client.is_valid_session(first)
    assert api_client.is_valid_session(second)
    assert len(first) == 16


def test_is_valid_session():
    results = [
        api_client.is_valid_session(value)
        for value in ["abc", "abcd-1234", "a" * 33, "abcd1234"]
    ]
    assert results == [False, False, False, True]
