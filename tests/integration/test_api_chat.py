import asyncio
import re
from contextlib import asynccontextmanager
from uuid import uuid4

import httpx
import pytest

from supportkit.api.app import create_app
from supportkit.core.llm.fake import RuleBasedFakeModel, ScriptedChatModel, compose_order_reply
from supportkit.settings import Settings

ASK_1042 = "ออเดอร์ BC-1042 ถึงไหนแล้วคะ"
FOLLOW_UP = "แล้วเลขพัสดุล่ะคะ"


def H(shop, customer, session):
    h = {"X-Demo-Shop-Id": shop, "X-Demo-Session": session}
    if customer is not None:
        h["X-Demo-Customer-Id"] = customer
    return h


def _app(database_url, model=None):
    return create_app(
        Settings(
            _env_file=None,
            database_url=database_url,
            supportkit_demo_mode=True,
            supportkit_model="fake:rules",
        ),
        model=model or RuleBasedFakeModel(),
    )


@asynccontextmanager
async def running(app):
    async with app.router.lifespan_context(app), httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t"
    ) as c:
        yield c


class Env:
    def __init__(self, app, client):
        self.app = app
        self.client = client
        self.threads: list[str] = []

    async def chat(self, headers, message):
        r = await self.client.post("/chat", headers=headers, json={"message": message})
        if r.status_code == 200:
            self.threads.append(r.json()["thread_id"])
        return r


@pytest.fixture
async def env(database_url):
    app = _app(database_url)
    async with running(app) as client:
        e = Env(app, client)
        try:
            yield e
        finally:
            for t in set(e.threads):
                await app.state.runtime.checkpointer.adelete_thread(t)


def sess():
    return uuid4().hex[:16]


async def test_happy_path(env, two_shops):
    s = sess()
    r = await env.chat(H(two_shops.shop_a, "C-1", s), ASK_1042)
    assert r.status_code == 200
    body = r.json()
    assert "TRACK-A-1042" in body["reply"]
    assert body["thread_id"] == f"{two_shops.shop_a}:web:demo-C-1-{s}"
    assert re.fullmatch(r"[0-9a-f]{32}", body["turn_id"])


async def test_follow_up_remembers_order(env, two_shops):
    s = sess()
    h = H(two_shops.shop_a, "C-1", s)
    await env.chat(h, ASK_1042)
    r = await env.chat(h, FOLLOW_UP)
    assert r.status_code == 200
    assert "TRACK-A-1042" in r.json()["reply"]


async def test_restart_persists_history(database_url, two_shops):
    s = sess()
    h = H(two_shops.shop_a, "C-1", s)
    thread_id = f"{two_shops.shop_a}:web:demo-C-1-{s}"
    app1 = _app(database_url)
    async with running(app1) as c1:
        try:
            r = await c1.post("/chat", headers=h, json={"message": ASK_1042})
            assert r.status_code == 200
            assert r.json()["thread_id"] == thread_id
        except BaseException:
            await app1.state.runtime.checkpointer.adelete_thread(thread_id)
            raise
    app2 = _app(database_url)
    async with running(app2) as c2:
        try:
            r = await c2.post("/chat", headers=h, json={"message": FOLLOW_UP})
            assert r.status_code == 200
            assert "TRACK-A-1042" in r.json()["reply"]
            hist = await c2.get("/chat/history", headers=h)
            assert hist.status_code == 200
            assert [m["role"] for m in hist.json()["messages"]] == [
                "user",
                "assistant",
                "user",
                "assistant",
            ]
        finally:
            await app2.state.runtime.checkpointer.adelete_thread(thread_id)


async def test_other_customers_order_is_not_found(env, two_shops):
    r = await env.chat(H(two_shops.shop_a, "C-1", sess()), "ออเดอร์ BC-1050 ถึงไหนแล้วคะ")
    assert r.status_code == 200
    reply = r.json()["reply"]
    assert "TRACK-A-1050" not in reply
    assert "1830" not in reply
    assert reply == compose_order_reply({"found": False, "order_no": "BC-1050"}, "th")


async def test_same_order_no_other_shop(env, two_shops):
    r = await env.chat(H(two_shops.shop_b, "C-1", sess()), ASK_1042)
    reply = r.json()["reply"]
    assert "TRACK-B-1042" in reply
    assert "TRACK-A-1042" not in reply


async def test_order_only_in_other_shop(env, two_shops):
    r = await env.chat(H(two_shops.shop_b, "C-1", sess()), "ออเดอร์ BC-1050 ถึงไหนแล้วคะ")
    assert r.status_code == 200
    assert "TRACK-" not in r.json()["reply"]


async def test_guest_gets_no_order_data(env, two_shops):
    s = sess()
    r = await env.chat(H(two_shops.shop_a, None, s), ASK_1042)
    assert r.status_code == 200
    assert "TRACK-" not in r.json()["reply"]
    assert r.json()["thread_id"].endswith(f"demo-guest-{s}")


async def test_persona_switch_isolated(env, two_shops):
    s = sess()
    r1 = await env.chat(H(two_shops.shop_a, "C-1", s), ASK_1042)
    r2 = await env.chat(H(two_shops.shop_a, "C-2", s), FOLLOW_UP)
    assert r2.status_code == 200
    assert "TRACK-A-1042" not in r2.json()["reply"]
    assert r1.json()["thread_id"] != r2.json()["thread_id"]


async def test_extra_body_fields_rejected(env, two_shops):
    r = await env.client.post(
        "/chat",
        headers=H(two_shops.shop_a, "C-1", sess()),
        json={"message": "ออเดอร์ BC-1042", "customer_id": "C-2", "shop_id": two_shops.shop_b},
    )
    assert r.status_code == 422


async def test_bad_headers_400(env, two_shops):
    a = two_shops.shop_a
    s = sess()
    cases = [
        {"X-Demo-Shop-Id": a, "X-Demo-Customer-Id": "C-1"},  # missing session
        H(a, "C-1", "short"),
        H("Bad Shop", "C-1", s),
        H(a, "a b", s),
    ]
    for headers in cases:
        r = await env.client.post("/chat", headers=headers, json={"message": "hi"})
        assert r.status_code == 400, headers
        assert r.json() == {"detail": "invalid_demo_identity"}


async def test_unknown_identity_403(env, two_shops):
    s = sess()
    for headers in (
        H(two_shops.shop_a, "C-404", s),
        H("t-none-zzz", None, s),
        H(two_shops.shop_b, "C-2", s),
    ):
        r = await env.client.post("/chat", headers=headers, json={"message": "hi"})
        assert r.status_code == 403, headers
        assert r.json() == {"detail": "unknown_demo_identity"}


async def test_bad_body_422(env, two_shops):
    h = H(two_shops.shop_a, "C-1", sess())
    for body in ({"message": ""}, {"message": "   "}, {"message": "x" * 2001}, {}):
        r = await env.client.post("/chat", headers=h, json=body)
        assert r.status_code == 422, body


async def test_history_empty_for_new_session(env, two_shops):
    r = await env.client.get("/chat/history", headers=H(two_shops.shop_a, "C-1", sess()))
    assert r.status_code == 200
    assert r.json()["messages"] == []


async def test_agent_failure_502(database_url, two_shops):
    app = _app(database_url, model=ScriptedChatModel(responses=[]))
    s = sess()
    async with running(app) as c:
        try:
            msg = "ข้อความลับ-secret-marker"
            r = await c.post("/chat", headers=H(two_shops.shop_a, "C-1", s), json={"message": msg})
            assert r.status_code == 502
            assert r.json() == {"detail": "agent_error"}
            assert msg not in r.text
        finally:
            # The input is checkpointed before the model fails, so the thread exists.
            await app.state.runtime.checkpointer.adelete_thread(
                f"{two_shops.shop_a}:web:demo-C-1-{s}"
            )


async def test_concurrent_turns_serialised(env, two_shops):
    s = sess()
    h = H(two_shops.shop_a, "C-1", s)
    r1, r2 = await asyncio.gather(env.chat(h, ASK_1042), env.chat(h, FOLLOW_UP))
    assert r1.status_code == 200
    assert r2.status_code == 200
    hist = await env.client.get("/chat/history", headers=h)
    roles = [m["role"] for m in hist.json()["messages"]]
    assert roles == ["user", "assistant", "user", "assistant"]
