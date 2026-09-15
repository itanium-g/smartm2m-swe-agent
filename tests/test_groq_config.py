import os
import tempfile
from pathlib import Path

from smartm2m.config import ExperimentConfig, ModelConfig, load_env_file
from smartm2m.experiment import _redact
from smartm2m.reference import ReferenceRunner


def test_groq_default_model_config():
    config = ModelConfig()
    assert config.provider == "groq"
    assert config.model == "openai/gpt-oss-120b"
    assert config.base_url == "https://api.groq.com/openai/v1"
    assert config.api_key_env == "GROQ_API_KEY"
    assert config.input_usd_per_million == 0.15
    assert config.output_usd_per_million == 0.60


def test_load_env_file(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        env_path = Path(td) / ".env"
        env_path.write_text("TEST_KEY_FOO=bar_value\nTEST_KEY_QUOTED=\"hello_world\"\n# comment\n", encoding="utf-8")
        monkeypatch.delenv("TEST_KEY_FOO", raising=False)
        monkeypatch.delenv("TEST_KEY_QUOTED", raising=False)
        load_env_file(env_path)
        assert os.environ.get("TEST_KEY_FOO") == "bar_value"
        assert os.environ.get("TEST_KEY_QUOTED") == "hello_world"


def test_groq_api_key_redaction():
    text = "Error with key gsk_sampledummykeyabcdef1234567890 in logs"
    redacted = _redact(text)
    assert "gsk_" not in redacted
    assert "[REDACTED]" in redacted


def test_reference_runner_environment_groq_keys(monkeypatch):
    root = Path(__file__).parents[1]
    config = ExperimentConfig.load(root / "configs/experiment.lock.yaml")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_fakekey12345678901234567890")
    runner = ReferenceRunner(config)
    env = runner._environment()
    assert env.get("GROQ_API_KEY") == "gsk_fakekey12345678901234567890"
    assert env.get("OPENAI_API_KEY") == "gsk_fakekey12345678901234567890"
