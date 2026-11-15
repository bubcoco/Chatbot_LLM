import pytest

from supportkit.core.llm import factory
from supportkit.core.llm.fake import RuleBasedFakeModel


def test_fake_rules():
    assert isinstance(factory.get_chat_model("fake:rules"), RuleBasedFakeModel)


@pytest.mark.parametrize("spec", ["fake:other", "claude", ":x", "anthropic:"])
def test_bad_specs(spec):
    with pytest.raises(ValueError):
        factory.get_chat_model(spec)


def test_real_provider_delegates(monkeypatch):
    calls = []

    def recorder(*args, **kwargs):
        calls.append((args, kwargs))
        return "model"

    # Keep the repo .env out of os.environ so later tests see clean defaults.
    monkeypatch.setattr(factory, "load_dotenv", lambda **kw: None)
    monkeypatch.setattr(factory, "init_chat_model", recorder)
    assert factory.get_chat_model("anthropic:some-model") == "model"
    assert calls == [
        (
            ("anthropic:some-model",),
            {"temperature": 0.2, "max_tokens": 1024, "timeout": 60, "max_retries": 2},
        )
    ]
