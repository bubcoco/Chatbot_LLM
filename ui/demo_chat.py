"""Streamlit demo chat page. Talks to the supportkit demo API over HTTP only."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import api_client
import streamlit as st

API_URL = os.environ.get("SUPPORTKIT_API_URL", api_client.DEFAULT_API_URL)
PERSONAS = {  # golden records from spec 03; label -> customer_id
    "baan-bai-cha": {
        "สมหญิง (C-0001) — BC-1042, BC-1043": "C-0001",
        "อนันต์ (C-0002) — BC-1050, BC-1051": "C-0002",
        "Emma (C-0007) — BC-1090, BC-1091": "C-0007",
        "Guest (not verified)": None,
    },
    "shop-b": {
        "ปรีชา (C-0001) — BC-1042, BC-9001": "C-0001",
        "Sarah (C-0002) — BC-1050": "C-0002",
        "Guest (not verified)": None,
    },
}


def _new_conversation() -> None:
    new_id = api_client.new_session_id()
    st.session_state["session"] = new_id
    st.session_state["session_input"] = new_id


def _show_error(exc: api_client.ChatApiError) -> None:
    if exc.status_code is None:
        st.error(
            f"Cannot reach the API at {API_URL}. "
            "Start it with: supportkit serve (SUPPORTKIT_DEMO_MODE=true)."
        )
    elif exc.status_code == 404:
        st.error("The API is running without demo mode. Set SUPPORTKIT_DEMO_MODE=true.")
    elif exc.status_code == 403:
        st.error("This demo persona does not exist. Run: supportkit seed.")
    else:
        st.error(f"Request failed ({exc.status_code}: {exc.detail}).")


st.set_page_config(page_title="supportkit demo", page_icon="🍵")
st.title("supportkit — demo chat")

# Session id: the URL query string carries only this value, never shop or customer.
if "session" not in st.session_state:
    qp_session = st.query_params.get("session")
    if isinstance(qp_session, str) and api_client.is_valid_session(qp_session):
        st.session_state["session"] = qp_session
    else:
        st.session_state["session"] = api_client.new_session_id()
if "session_input" not in st.session_state:
    st.session_state["session_input"] = st.session_state["session"]

st.sidebar.warning(
    "Demo only: the persona selector stands in for customer identity. "
    "Real channels verify identity server-side."
)
shop = st.sidebar.selectbox("Shop", list(PERSONAS), key="shop")
persona = st.sidebar.selectbox("Customer", list(PERSONAS[shop]), key="persona")
st.sidebar.text_input(
    "Session ID",
    key="session_input",
    help="Keep this ID to continue the same conversation after a restart.",
)
st.sidebar.button("New conversation", on_click=_new_conversation)

session = st.session_state["session"]
session_input = st.session_state["session_input"]
if session_input != session:
    if api_client.is_valid_session(session_input):
        session = session_input
        st.session_state["session"] = session
    else:
        st.sidebar.error("Session ID must be 8–32 letters or digits.")
st.query_params["session"] = session

identity = api_client.DemoIdentity(shop, PERSONAS[shop][persona], session)

try:
    health = api_client.fetch_health(API_URL)
    model = health.get("model", "unknown")
    st.sidebar.caption(f"API: {API_URL} · model: {model}")
except api_client.ChatApiError:
    st.sidebar.caption(f"API: {API_URL} · API not reachable")

# The server is the source of truth for history; nothing is cached in session state.
try:
    history = api_client.fetch_history(API_URL, identity)
except api_client.ChatApiError as exc:
    _show_error(exc)
    history = []
for entry in history:
    st.chat_message(entry["role"]).write(entry["text"])

prompt = st.chat_input("พิมพ์ข้อความ… / Type a message…", max_chars=2000)
if prompt:
    st.chat_message("user").write(prompt)
    with st.chat_message("assistant"), st.spinner("…"):
        try:
            reply = api_client.send_message(API_URL, identity, prompt)
            st.write(reply["reply"])
        except api_client.ChatApiError as exc:
            _show_error(exc)
