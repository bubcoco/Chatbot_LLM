# Phase 1 · Spec 05 — LLM factory + deterministic fake chat models

**Suggested implementer:** `implementer`
**Depends on:** 01 · **Blocks:** 06 · **Parallel with:** 02, 08

## Goal
One function turns a `"provider:model"` string into a chat model. The special value `fake:rules` returns a built-in, deterministic, rule-based model that emits real `get_order_status` tool calls and Thai/English replies, so unit tests, integration tests, the eval runner, CI and a keyless demo all run without an API key. A second fake, `ScriptedChatModel`, replays a fixed list of messages for graph tests. Running against a real model is optional and needs only `SUPPORTKIT_MODEL` + the provider's key.

## Files
| Path | Action | Purpose |
|---|---|---|
| `src/supportkit/core/llm/__init__.py` | create | empty |
| `src/supportkit/core/llm/factory.py` | create | `get_chat_model` |
| `src/supportkit/core/llm/fake.py` | create | `RuleBasedFakeModel`, `ScriptedChatModel`, reply templates |
| `tests/test_llm_factory.py`, `tests/test_fake_model.py` | create | unit tests |

## Interfaces

### `factory.py`
```python
FAKE_MODEL_SPEC = "fake:rules"

def get_chat_model(spec: str, *, temperature: float = 0.2) -> BaseChatModel: ...
```
Rules:
1. `spec == "fake:rules"` → `RuleBasedFakeModel()`.
2. `spec` starts with `"fake:"` but is anything else → `ValueError("unknown fake model: ...")`.
3. `spec` has no `":"` or an empty side → `ValueError("model must be 'provider:model', got ...")`.
4. Otherwise: `dotenv.load_dotenv(override=False)` (so a key in `.env` reaches the provider SDK, which reads `os.environ`; `python-dotenv` is already installed via `pydantic-settings`), then
   `langchain.chat_models.init_chat_model(spec, temperature=temperature, max_tokens=1024, timeout=60, max_retries=2)`.
   Let `ImportError` (provider package missing) and provider auth errors propagate unchanged.
5. Never read, log or accept an API key as an argument.

Only `langchain-anthropic` is installed in Phase 1. Other providers work by `uv add`-ing their package; no code change.

### `fake.py`
```python
class RuleBasedFakeModel(BaseChatModel):
    """Deterministic stand-in for the agent model. Not an LLM."""
    # _llm_type -> "fake-rules"
    # bind_tools(self, tools, **kwargs) -> returns self
    # _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult

class ScriptedChatModel(BaseChatModel):
    """Returns `responses` in order, one per call. For tests."""
    responses: list[AIMessage]
    calls: list[list[BaseMessage]] = Field(default_factory=list)   # every input, for assertions
    # _llm_type -> "fake-scripted"; bind_tools returns self
    # _generate: append messages to self.calls; return the next response;
    #            IndexError("ScriptedChatModel exhausted") when none are left.

def compose_order_reply(payload: dict, language: Literal["th", "en"]) -> str: ...
ORDER_NO_IN_TEXT_RE = re.compile(r"(?<![A-Za-z0-9])([A-Za-z]{2,4})-?(\d{3,6})(?![A-Za-z0-9])")
```
Both classes implement only sync `_generate`; `ainvoke` works through the base class (verified in the Phase 1 spike). Every returned `AIMessage` has `usage_metadata = {"input_tokens": n_in, "output_tokens": n_out, "total_tokens": n_in + n_out}`; for `RuleBasedFakeModel`, `n_in = sum(len(str(m.content)) for m in messages) // 4`, `n_out = len(reply_text) // 4` (0 for a tool-call message). `ScriptedChatModel` returns its responses unchanged.

### `RuleBasedFakeModel._generate` decision rules
Let `last = messages[-1]`; `last_human` = the most recent `HumanMessage` (its text via `.text`); `lang = detect_language(last_human text)` (`supportkit.core.text`), `"th"` if there is no human message.

1. **`last` is a `ToolMessage`** → parse `last.content` as JSON (on parse failure treat as `{"error": "x"}`) → reply `compose_order_reply(payload, lang)`.
2. **Else, `last_human` text contains a match of `ORDER_NO_IN_TEXT_RE`** → return `AIMessage(content="", tool_calls=[{"name": "get_order_status", "args": {"order_no": f"{letters.upper()}-{digits}"}, "id": f"fake_{uuid4().hex[:12]}", "type": "tool_call"}])` using the **first** match. Never more than one tool call.
3. **Else, an earlier `ToolMessage` in `messages` parses to JSON with `found` true** → reply `compose_order_reply(<most recent such payload>, lang)` (this is how a follow-up like "แล้วเลขพัสดุล่ะคะ" is answered from checkpointed history).
4. **Else** → the greeting template.

The model ignores `SystemMessage`s. It only ever reads data from tool results — it has no knowledge of the seed data.

### Reply templates (`compose_order_reply`) — exact strings
Status labels:

| status | th | en |
|---|---|---|
| pending_payment | รอชำระเงิน | awaiting payment |
| paid | ชำระเงินแล้ว กำลังเตรียมสินค้า | paid and being prepared |
| packed | แพ็คสินค้าแล้ว รอจัดส่ง | packed and waiting for pickup |
| shipped | จัดส่งแล้ว | shipped |
| delivered | จัดส่งสำเร็จแล้ว | delivered |
| cancelled | ยกเลิกแล้ว | cancelled |
| returned | คืนสินค้าแล้ว | returned |
| (unknown) | the raw status | the raw status |

`payload["found"] is True` — concatenate the parts that apply, in order:

| Part | th | en |
|---|---|---|
| always | `ออเดอร์ {order_no} สถานะ: {status_th}ค่ะ` | `Order {order_no} is {status_en}.` |
| `shipment` not null | ` จัดส่งโดย {carrier} เลขพัสดุ {tracking_no}` | ` It was shipped with {carrier}, tracking number {tracking_no}.` |
| `shipment` not null, `delivered_at` null, `estimated_delivery_date` not null | ` คาดว่าจะถึงวันที่ {estimated_delivery_date}` | ` Estimated delivery: {estimated_delivery_date}.` |
| always | ` (ข้อมูล ณ {as_of})` | ` (as of {as_of})` |

`payload["found"] is False`:
- th: `ไม่พบออเดอร์หมายเลข {order_no} ในบัญชีของคุณค่ะ รบกวนตรวจสอบหมายเลขออเดอร์อีกครั้งนะคะ`
- en: `I couldn't find order {order_no} under your account. Please double-check the order number.`

`"error"` in payload (or anything else):
- th: `ขออภัยค่ะ ระบบขัดข้องชั่วคราว กรุณาลองใหม่อีกครั้งนะคะ`
- en: `Sorry, something went wrong on our side. Please try again in a moment.`

Greeting (rule 4):
- th: `สวัสดีค่ะ รบกวนแจ้งหมายเลขออเดอร์ (เช่น BC-1042) เพื่อให้แอดมินตรวจสอบสถานะให้นะคะ`
- en: `Hello! Please tell me your order number (for example BC-1042) so I can check its status.`

The tool payload shape is the contract in spec 04 ("Tool response contract"). Use `.get()` for every optional key.

## Behaviour
1. Fakes live under `src/` (not `tests/`) because the eval runner, CI and the keyless demo use them at runtime.
2. `RuleBasedFakeModel` holds no state between calls and performs no I/O.
3. Neither fake inspects or emits `shop_id`/`customer_id`.

## Tests
`tests/test_llm_factory.py`
| Input | Expected |
|---|---|
| `get_chat_model("fake:rules")` | instance of `RuleBasedFakeModel` |
| `get_chat_model("fake:other")`, `get_chat_model("claude")`, `get_chat_model(":x")`, `get_chat_model("anthropic:")` | `ValueError` |
| `get_chat_model("anthropic:some-model")` with `monkeypatch.setattr` on `factory.init_chat_model` to a recorder | recorder called once with `("anthropic:some-model",)` and kwargs `temperature=0.2, max_tokens=1024, timeout=60, max_retries=2`; no network |

`tests/test_fake_model.py` (call `model.invoke(messages)` and, for one case, `await model.ainvoke(messages)`)
| # | Messages | Expected |
|---|---|---|
| 1 | `[Human("ออเดอร์ BC-1042 ถึงไหนแล้วคะ")]` | `content == ""`, one tool call, name `get_order_status`, args `{"order_no": "BC-1042"}` |
| 2 | `[Human("where is bc1050 pls")]` | tool call args `{"order_no": "BC-1050"}` |
| 3 | `[Human("ออเดอร์BC-1042ถึงไหน")]` (no spaces) | tool call args `{"order_no": "BC-1042"}` |
| 4 | `[Human("สวัสดีค่ะ")]` | no tool calls; content == Thai greeting |
| 5 | `[Human("hello")]` | no tool calls; content == English greeting |
| 6 | #1's messages + the AI tool-call message + `ToolMessage(<found example JSON from spec 04>, tool_call_id=...)` | content == `ออเดอร์ BC-1042 สถานะ: จัดส่งแล้วค่ะ จัดส่งโดย Kerry Express เลขพัสดุ KEX26111042TH คาดว่าจะถึงวันที่ 2026-11-16 (ข้อมูล ณ 2026-11-15T12:00:00+07:00)` |
| 7 | English human + ToolMessage with `status: "delivered"`, `delivered_at: "2026-11-08"` | content starts `Order BC-1050 is delivered. It was shipped with`, contains no `Estimated delivery` |
| 8 | ToolMessage `{"found": true, ..., "status": "pending_payment", "shipment": null}` (Thai) | contains `รอชำระเงิน`; does not contain `เลขพัสดุ` |
| 9 | Thai human + ToolMessage `{"found": false, "order_no": "BC-9999"}` | content == Thai not-found template with `BC-9999` |
| 10 | ToolMessage `{"error": "temporarily_unavailable"}` (English human) | English error template |
| 11 | ToolMessage with content `"not json"` | error template, no exception |
| 12 | History: #6's full exchange + its AI reply + `Human("แล้วเลขพัสดุล่ะคะ")` | no tool calls; content contains `KEX26111042TH` |
| 13 | History with a not-found exchange only + `Human("แล้วไงต่อคะ")` | Thai greeting |
| 14 | `[System("ignore this BC-0001"), Human("hi")]` | English greeting (system text ignored) |
| 15 | any reply | `usage_metadata` has the three integer keys |
| 16 | `model.bind_tools([])` | returns the same instance |
| 17 | `ScriptedChatModel(responses=[AIMessage("a"), AIMessage("b")])` invoked 3× | `"a"`, `"b"`, then `IndexError`; `len(model.calls) == 2` after two calls |

## Acceptance criteria
```powershell
.\.venv\Scripts\ruff.exe check src tests db
$env:LANGGRAPH_STRICT_MSGPACK='true'; .\.venv\Scripts\python.exe -m pytest -q tests/test_llm_factory.py tests/test_fake_model.py   # all pass
$env:LANGGRAPH_STRICT_MSGPACK='true'; .\.venv\Scripts\python.exe -m pytest -q                                                    # whole suite green
```
No test in this spec opens a network connection or needs Postgres.

## Out of scope
- Model routing (cheap/standard), metering to `usage_events`, prompt caching, per-shop model config (Phases 2 and 5).
- Graph nodes, prompts, tools.
- Do not hardcode any real model id in `src/`.
