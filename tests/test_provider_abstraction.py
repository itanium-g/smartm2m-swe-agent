from smartm2m.config import ModelConfig
from smartm2m.model import (
    GroqProvider,
    MistralProvider,
    _redact_secrets,
    get_model_provider,
)


def test_get_model_provider_selection():
    mistral_cfg = ModelConfig(provider="mistral", model="codestral-2508", base_url="https://api.mistral.ai/v1")
    assert isinstance(get_model_provider(mistral_cfg), MistralProvider)

    groq_cfg = ModelConfig(provider="groq", model="openai/gpt-oss-120b", base_url="https://api.groq.com/openai/v1")
    assert isinstance(get_model_provider(groq_cfg), GroqProvider)


def test_mistral_payload_uses_random_seed_and_parallel_tool_calls_false():
    cfg = ModelConfig(provider="mistral", model="codestral-2508", base_url="https://api.mistral.ai/v1", seed=42)
    provider = MistralProvider(cfg)
    messages = [{"role": "user", "content": "hello"}]
    tools = [{"type": "function", "function": {"name": "test_fn", "parameters": {}}}]
    payload = provider.build_payload(messages, tools, temperature=0.0, seed=42, max_tokens=100)

    # Mistral strictly requires random_seed, not seed
    assert "random_seed" in payload
    assert payload["random_seed"] == 42
    assert "seed" not in payload
    assert payload.get("parallel_tool_calls") is False
    assert payload.get("tool_choice") == "auto"


def test_groq_payload_strips_reasoning_and_provider_specific_fields():
    cfg = ModelConfig(provider="groq", model="openai/gpt-oss-120b", base_url="https://api.groq.com/openai/v1", seed=42)
    provider = GroqProvider(cfg)
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "usr"},
        {
            "role": "assistant",
            "content": "",
            "reasoning": "internal thoughts",
            "provider_specific_fields": {"key": "val"},
            "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": "f", "arguments": "{}"}}
            ],
        },
        {"role": "tool", "tool_call_id": "c1", "content": "ok"},
    ]
    payload = provider.build_payload(messages, [], temperature=0.0, seed=42, max_tokens=100)
    asst_msg = payload["messages"][2]
    assert "reasoning" not in asst_msg
    assert "provider_specific_fields" not in asst_msg
    assert asst_msg["role"] == "assistant"
    assert len(asst_msg["tool_calls"]) == 1


def test_groq_returns_unknown_tools_for_local_validation():
    provider = GroqProvider(ModelConfig(provider="groq", parallel_tool_calls=False))
    tools = [{"type": "function", "function": {"name": "read_file", "parameters": {}}}]
    payload = provider.build_payload([], tools, temperature=0, seed=42, max_tokens=100)
    assert payload["disable_tool_validation"] is True
    assert payload["parallel_tool_calls"] is False
    assert "disable_tool_validation" not in provider.build_payload([], [], temperature=0, seed=42, max_tokens=100)


def test_redact_secrets_cleans_keys_and_tokens(monkeypatch):
    dummy_mistral = "dummy_mistral_secret_key_1234567890"
    dummy_groq = "gsk_dummy_groq_secret_key_1234567890abcdef"
    monkeypatch.setenv("MISTRAL_API_KEY", dummy_mistral)
    monkeypatch.setenv("GROQ_API_KEY", dummy_groq)

    sample_log = (
        f"Error in request with Bearer {dummy_mistral}: "
        f"failed for {dummy_groq} with api_key={dummy_mistral}"
    )
    cleaned = _redact_secrets(sample_log)
    assert dummy_mistral not in cleaned
    assert dummy_groq not in cleaned
    assert "[REDACTED]" in cleaned
