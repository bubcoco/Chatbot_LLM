"""Chat model factory: turns a "provider:model" string into a chat model."""

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel

from supportkit.core.llm.fake import RuleBasedFakeModel

FAKE_MODEL_SPEC = "fake:rules"


def get_chat_model(spec: str, *, temperature: float = 0.2) -> BaseChatModel:
    """Build a chat model from ``"provider:model"``; ``"fake:rules"`` is keyless."""
    if spec == FAKE_MODEL_SPEC:
        return RuleBasedFakeModel()
    if spec.startswith("fake:"):
        raise ValueError(f"unknown fake model: {spec!r}")
    provider, sep, model = spec.partition(":")
    if not sep or not provider or not model:
        raise ValueError(f"model must be 'provider:model', got {spec!r}")
    # Let a key in .env reach the provider SDK, which reads os.environ.
    load_dotenv(override=False)
    return init_chat_model(
        spec, temperature=temperature, max_tokens=1024, timeout=60, max_retries=2
    )
