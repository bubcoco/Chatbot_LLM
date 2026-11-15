"""Deterministic fake chat models for tests, evals, CI and keyless demos."""

import json
import re
from typing import Any, Literal
from uuid import uuid4

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field, PrivateAttr

from supportkit.core.text import detect_language

ORDER_NO_IN_TEXT_RE = re.compile(r"(?<![A-Za-z0-9])([A-Za-z]{2,4})-?(\d{3,6})(?![A-Za-z0-9])")

_STATUS_TH = {
    "pending_payment": "รอชำระเงิน",
    "paid": "ชำระเงินแล้ว กำลังเตรียมสินค้า",
    "packed": "แพ็คสินค้าแล้ว รอจัดส่ง",
    "shipped": "จัดส่งแล้ว",
    "delivered": "จัดส่งสำเร็จแล้ว",
    "cancelled": "ยกเลิกแล้ว",
    "returned": "คืนสินค้าแล้ว",
}
_STATUS_EN = {
    "pending_payment": "awaiting payment",
    "paid": "paid and being prepared",
    "packed": "packed and waiting for pickup",
    "shipped": "shipped",
    "delivered": "delivered",
    "cancelled": "cancelled",
    "returned": "returned",
}

GREETING = {
    "th": "สวัสดีค่ะ รบกวนแจ้งหมายเลขออเดอร์ (เช่น BC-1042) เพื่อให้แอดมินตรวจสอบสถานะให้นะคะ",
    "en": "Hello! Please tell me your order number (for example BC-1042) so I can check its status.",
}
_ERROR = {
    "th": "ขออภัยค่ะ ระบบขัดข้องชั่วคราว กรุณาลองใหม่อีกครั้งนะคะ",
    "en": "Sorry, something went wrong on our side. Please try again in a moment.",
}


def compose_order_reply(payload: dict, language: Literal["th", "en"]) -> str:
    """Render a get_order_status tool payload as a customer-facing reply."""
    th = language == "th"
    if payload.get("found") is True:
        order_no = payload.get("order_no")
        status = payload.get("status")
        labels = _STATUS_TH if th else _STATUS_EN
        label = labels.get(status, status)
        as_of = payload.get("as_of")
        shipment = payload.get("shipment")
        if th:
            text = f"ออเดอร์ {order_no} สถานะ: {label}ค่ะ"
        else:
            text = f"Order {order_no} is {label}."
        if shipment:
            carrier = shipment.get("carrier")
            tracking = shipment.get("tracking_no")
            if th:
                text += f" จัดส่งโดย {carrier} เลขพัสดุ {tracking}"
            else:
                text += f" It was shipped with {carrier}, tracking number {tracking}."
            eta = shipment.get("estimated_delivery_date")
            if shipment.get("delivered_at") is None and eta is not None:
                text += f" คาดว่าจะถึงวันที่ {eta}" if th else f" Estimated delivery: {eta}."
        text += f" (ข้อมูล ณ {as_of})" if th else f" (as of {as_of})"
        return text
    if payload.get("found") is False:
        order_no = payload.get("order_no")
        if th:
            return (
                f"ไม่พบออเดอร์หมายเลข {order_no} ในบัญชีของคุณค่ะ "
                "รบกวนตรวจสอบหมายเลขออเดอร์อีกครั้งนะคะ"
            )
        return (
            f"I couldn't find order {order_no} under your account. "
            "Please double-check the order number."
        )
    return _ERROR[language]


def _parse_json(content: Any) -> dict:
    try:
        data = json.loads(content if isinstance(content, str) else str(content))
    except (ValueError, TypeError):
        return {"error": "x"}
    return data if isinstance(data, dict) else {"error": "x"}


def _usage(n_in: int, n_out: int) -> dict[str, int]:
    return {"input_tokens": n_in, "output_tokens": n_out, "total_tokens": n_in + n_out}


class RuleBasedFakeModel(BaseChatModel):
    """Deterministic stand-in for the agent model. Not an LLM."""

    @property
    def _llm_type(self) -> str:
        return "fake-rules"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "RuleBasedFakeModel":
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        n_in = sum(len(str(m.content)) for m in messages) // 4
        last_human = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
        human_text = last_human.text if last_human is not None else ""
        lang = detect_language(human_text) if last_human is not None else "th"

        match = ORDER_NO_IN_TEXT_RE.search(human_text)
        reply: str | None = None
        tool_calls: list[dict] = []
        if messages and isinstance(messages[-1], ToolMessage):
            reply = compose_order_reply(_parse_json(messages[-1].content), lang)
        elif match:
            tool_calls = [
                {
                    "name": "get_order_status",
                    "args": {"order_no": f"{match.group(1).upper()}-{match.group(2)}"},
                    "id": f"fake_{uuid4().hex[:12]}",
                    "type": "tool_call",
                }
            ]
        else:
            found_payload = None
            for m in reversed(messages):
                if isinstance(m, ToolMessage):
                    payload = _parse_json(m.content)
                    if payload.get("found") is True:
                        found_payload = payload
                        break
            reply = (
                compose_order_reply(found_payload, lang)
                if found_payload is not None
                else GREETING[lang]
            )

        text = reply or ""
        msg = AIMessage(
            content=text,
            tool_calls=tool_calls,
            usage_metadata=_usage(n_in, len(text) // 4),
        )
        return ChatResult(generations=[ChatGeneration(message=msg)])


class ScriptedChatModel(BaseChatModel):
    """Returns `responses` in order, one per call. For tests."""

    responses: list[AIMessage]
    calls: list[list[BaseMessage]] = Field(default_factory=list)
    _index: int = PrivateAttr(default=0)

    @property
    def _llm_type(self) -> str:
        return "fake-scripted"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedChatModel":
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.calls.append(list(messages))
        if self._index >= len(self.responses):
            raise IndexError("ScriptedChatModel exhausted")
        msg = self.responses[self._index]
        self._index += 1
        return ChatResult(generations=[ChatGeneration(message=msg)])
