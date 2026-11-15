import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

UI_DIR = Path(__file__).resolve().parent.parent / "ui"
if str(UI_DIR) not in sys.path:
    sys.path.insert(0, str(UI_DIR))

import api_client

PAGE = str(UI_DIR / "demo_chat.py")
HISTORY = [
    {"role": "user", "text": "สวัสดี"},
    {"role": "assistant", "text": "สวัสดีค่ะ"},
]
HEALTH = {"status": "ok", "model": "fake:rules", "demo_mode": True}


@pytest.fixture
def patched(monkeypatch):
    monkeypatch.setattr(api_client, "fetch_history", lambda base_url, identity, **kw: HISTORY)
    monkeypatch.setattr(api_client, "fetch_health", lambda base_url, **kw: HEALTH)
    return monkeypatch


def test_page_renders_history_and_sidebar(patched):
    at = AppTest.from_file(PAGE).run()

    assert not at.exception
    assert len(at.chat_message) == 2
    assert len(at.sidebar.selectbox) == 2
    assert len(at.sidebar.warning) == 1


def test_page_shows_errors_when_api_unreachable(patched):
    def unreachable(*args, **kwargs):
        raise api_client.ChatApiError(None, "cannot reach API")

    patched.setattr(api_client, "fetch_history", unreachable)
    patched.setattr(api_client, "fetch_health", unreachable)

    at = AppTest.from_file(PAGE).run()

    assert not at.exception
    assert len(at.error) >= 1


def test_sending_message_calls_api_with_identity(patched):
    calls = []

    def recorder(base_url, identity, message, **kwargs):
        calls.append((identity, message))
        return {"reply": "ตอบแล้วค่ะ", "thread_id": "t", "turn_id": "u"}

    patched.setattr(api_client, "send_message", recorder)

    at = AppTest.from_file(PAGE).run()
    at.chat_input[0].set_value("ออเดอร์ BC-1042").run()

    assert len(calls) == 1
    identity, message = calls[0]
    assert message == "ออเดอร์ BC-1042"
    assert identity.shop_id == "baan-bai-cha"
    assert identity.customer_id == "C-0001"
    assert not at.exception
