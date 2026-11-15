"""Demo-mode gating: /chat must not exist unless SUPPORTKIT_DEMO_MODE=true. No DB (lifespan not run)."""

import httpx

from supportkit.api.app import create_app
from supportkit.settings import Settings

HEADERS = {
    "X-Demo-Shop-Id": "baan-bai-cha",
    "X-Demo-Customer-Id": "C-0001",
    "X-Demo-Session": "abcdef0123456789",
}


def _client(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


def _off_app():
    return create_app(Settings(_env_file=None, supportkit_demo_mode=False))


async def test_chat_404_when_demo_off():
    async with _client(_off_app()) as c:
        r = await c.post("/chat", headers=HEADERS, json={"message": "hi"})
    assert r.status_code == 404


async def test_history_404_when_demo_off():
    async with _client(_off_app()) as c:
        r = await c.get("/chat/history", headers=HEADERS)
    assert r.status_code == 404


async def test_health_when_demo_off():
    async with _client(_off_app()) as c:
        r = await c.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["demo_mode"] is False
    assert body["model"] == "fake:rules"
    assert body["status"] == "ok"


def test_demo_off_app_has_only_health_route():
    # Spec rule 13: demo routes are not mounted at all when demo mode is off.
    assert [r.path for r in _off_app().routes] == ["/health"]


async def test_openapi_404_when_demo_off():
    async with _client(_off_app()) as c:
        r = await c.get("/openapi.json")
    assert r.status_code == 404


def test_demo_app_has_chat_routes():
    app = create_app(Settings(_env_file=None, supportkit_demo_mode=True))
    paths = list(app.openapi()["paths"])
    assert "/chat" in paths
    assert "/chat/history" in paths
