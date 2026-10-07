"""Reasoning budget for OpenRouter models (empty replies when thinking eats max_tokens)."""

from types import SimpleNamespace

from open_notebook.ai.provision import limit_reasoning


def test_openrouter_models_get_a_reasoning_token_budget():
    model = SimpleNamespace(
        openai_api_base="https://openrouter.ai/api/v1", extra_body={"x": 1}
    )
    limit_reasoning(model, 512)  # type: ignore[arg-type]
    assert model.extra_body == {"x": 1, "reasoning": {"max_tokens": 512}}


def test_other_providers_are_untouched():
    model = SimpleNamespace(
        openai_api_base="https://api.openai.com/v1", extra_body=None
    )
    limit_reasoning(model)  # type: ignore[arg-type]
    assert model.extra_body is None
