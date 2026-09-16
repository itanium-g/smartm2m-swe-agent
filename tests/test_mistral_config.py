from pathlib import Path

from smartm2m.config import ExperimentConfig
from smartm2m.reference import ReferenceRunner


def test_mistral_config_loading():
    root = Path(__file__).parents[1]
    config = ExperimentConfig.load(root / "configs/experiment.mistral.yaml")
    assert config.model.provider == "mistral"
    assert config.model.model == "codestral-2508"
    assert config.model.base_url == "https://api.mistral.ai/v1"
    assert config.model.api_key_env == "MISTRAL_API_KEY"
    assert config.model.parallel_tool_calls is False
    assert config.model.temperature == 0.0
    assert config.model.seed == 42
    assert config.model.max_tokens == 2048
    assert config.model.input_usd_per_million == 0.30
    assert config.model.output_usd_per_million == 0.90


def test_reference_runner_environment_mistral_keys(monkeypatch):
    root = Path(__file__).parents[1]
    config = ExperimentConfig.load(root / "configs/experiment.mistral.yaml")
    monkeypatch.setenv("MISTRAL_API_KEY", "dummy_mistral_key_1234567890")
    runner = ReferenceRunner(config)
    env = runner._environment()
    assert env.get("MISTRAL_API_KEY") == "dummy_mistral_key_1234567890"


def test_reference_runner_model_prefix_mistral():
    root = Path(__file__).parents[1]
    config = ExperimentConfig.load(root / "configs/experiment.mistral.yaml")
    runner = ReferenceRunner(config)
    cmd = runner.command(Path("/tmp/fake_output"))
    # In command template or cli args, model should have mistral/ prefix
    cmd_str = " ".join(cmd)
    assert "mistral/codestral-2508" in cmd_str
