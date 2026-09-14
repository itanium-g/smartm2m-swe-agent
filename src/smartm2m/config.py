"""Configuration and manifest validation.

The lock file is intentionally JSON-compatible YAML. That keeps the minimal
runtime dependency-free while still allowing a normal YAML parser to read it.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import sysconfig
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    """Raised when an experiment cannot be safely reproduced."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_data(path: Path) -> Any:
    """Load JSON or safe YAML while preserving a list-valued manifest."""
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ConfigError(f"{path} is not JSON-compatible YAML; install PyYAML to read it") from exc
        return yaml.safe_load(text)


def load_document(path: Path) -> dict[str, Any]:
    value = load_data(path)
    if not isinstance(value, dict):
        raise ConfigError(f"{path} must contain an object at the top level")
    return value


def _string_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if not isinstance(value, (list, tuple)):
        raise ConfigError(f"{field_name} must be a string or array of strings")
    return tuple(str(item) for item in value)


@dataclass(frozen=True)
class TaskSpec:
    instance_id: str
    problem_statement: str
    repo: str = ""
    base_commit: str = ""
    repo_url: str = ""
    repo_path: str = ""
    test_commands: tuple[str, ...] = ("python -m pytest -q",)
    setup_commands: tuple[str, ...] = ()
    split: str = "test"
    image: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> "TaskSpec":
        required = ["instance_id", "problem_statement"]
        missing = [key for key in required if not raw.get(key)]
        if missing:
            raise ConfigError(f"task is missing required fields: {', '.join(missing)}")
        tests = _string_tuple(raw.get("test_commands", ["python -m pytest -q"]), "test_commands")
        setup = _string_tuple(raw.get("setup_commands", []), "setup_commands")
        if not tests:
            raise ConfigError("test_commands must contain at least one trusted command")
        hidden = {
            "patch", "test_patch", "hints_text", "FAIL_TO_PASS", "PASS_TO_PASS",
            "fail_to_pass", "pass_to_pass",
        }
        leaked = sorted(key for key in raw if str(key).lower() in {value.lower() for value in hidden})
        if leaked:
            raise ConfigError(
                f"task {raw.get('instance_id', '<unknown>')} contains evaluator-only fields: {', '.join(leaked)}"
            )
        metadata = {k: v for k, v in raw.items() if k not in {
            "instance_id", "problem_statement", "repo", "base_commit", "repo_url", "repo_path",
            "test_commands", "setup_commands", "split", "image", *hidden,
        }}
        return cls(
            instance_id=str(raw["instance_id"]),
            problem_statement=str(raw["problem_statement"]),
            repo=str(raw.get("repo", "")),
            base_commit=str(raw.get("base_commit", "")),
            repo_url=str(raw.get("repo_url", "")),
            repo_path=str(raw.get("repo_path", "")),
            test_commands=tests,
            setup_commands=setup,
            split=str(raw.get("split", "test")),
            image=str(raw.get("image", "")),
            metadata=metadata,
        )

    def generation_projection(self) -> dict[str, Any]:
        """Return only fields allowed to reach the generation arm."""
        return {
            "instance_id": self.instance_id,
            "problem_statement": self.problem_statement,
            "repo": self.repo,
            "base_commit": self.base_commit,
            "repo_url": self.repo_url,
            "split": self.split,
            "test_commands": list(self.test_commands),
            "runtime": {
                "container_image": self.image,
                "test_profile": self.metadata.get("test_profile", "repository-native"),
            },
        }


@dataclass(frozen=True)
class ModelConfig:
    provider: str = "openai-compatible"
    model: str = "openai/gpt-oss-120b"
    base_url: str = "https://api.deepinfra.com/v1"
    api_key_env: str = "DEEPINFRA_API_KEY"
    temperature: float = 0.0
    seed: int | None = 42
    max_tokens: int = 8192
    timeout_seconds: float = 120.0
    max_retries: int = 2
    input_usd_per_million: float | None = None
    output_usd_per_million: float | None = None

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> "ModelConfig":
        return cls(
            provider=str(raw.get("provider", cls.provider)),
            model=str(raw.get("model", cls.model)),
            base_url=str(raw.get("base_url", cls.base_url)),
            api_key_env=str(raw.get("api_key_env", cls.api_key_env)),
            temperature=float(raw.get("temperature", cls.temperature)),
            seed=None if raw.get("seed", cls.seed) is None else int(raw.get("seed", cls.seed)),
            max_tokens=int(raw.get("max_tokens", cls.max_tokens)),
            timeout_seconds=float(raw.get("timeout_seconds", cls.timeout_seconds)),
            max_retries=int(raw.get("max_retries", cls.max_retries)),
            input_usd_per_million=(
                None if raw.get("input_usd_per_million") is None else float(raw["input_usd_per_million"])
            ),
            output_usd_per_million=(
                None if raw.get("output_usd_per_million") is None else float(raw["output_usd_per_million"])
            ),
        )


@dataclass(frozen=True)
class ArmConfig:
    max_turns: int = 60
    # Dollar limits are optional because provider pricing may be unavailable or
    # endpoint-specific. Track 3 parity is enforced by the common turn and
    # completion-token caps in the lock file; observed spend is reported when
    # pricing is configured.
    cost_limit_usd: float | None = None
    wall_time_seconds: int = 2700
    command_timeout_seconds: int = 120
    max_output_chars: int = 10000

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> "ArmConfig":
        return cls(
            max_turns=int(raw.get("max_turns", cls.max_turns)),
            cost_limit_usd=(
                None if raw.get("cost_limit_usd", cls.cost_limit_usd) is None
                else float(raw["cost_limit_usd"])
            ),
            wall_time_seconds=int(raw.get("wall_time_seconds", cls.wall_time_seconds)),
            command_timeout_seconds=int(raw.get("command_timeout_seconds", cls.command_timeout_seconds)),
            max_output_chars=int(raw.get("max_output_chars", cls.max_output_chars)),
        )


@dataclass(frozen=True)
class ReferenceConfig:
    executable: str = "mini-extra"
    version: str = "2.4.6"
    source_sha: str = "a83fcae82d2a08f0ee0c688f9d137b3566c097f8"
    evaluator_sha: str = "02e7a74ffd0b707aab73d203fe87bdc7c76afc8e"
    config_path: str = ""
    subset: str = "verified"
    split: str = "test"
    workers: int = 1
    command_template: str = ""

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> "ReferenceConfig":
        return cls(
            executable=str(raw.get("executable", cls.executable)),
            version=str(raw.get("version", cls.version)),
            source_sha=str(raw.get("source_sha", cls.source_sha)),
            evaluator_sha=str(raw.get("evaluator_sha", cls.evaluator_sha)),
            config_path=str(raw.get("config_path", cls.config_path)),
            subset=str(raw.get("subset", cls.subset)),
            split=str(raw.get("split", cls.split)),
            workers=int(raw.get("workers", cls.workers)),
            command_template=str(raw.get("command_template", cls.command_template)),
        )


@dataclass(frozen=True)
class ExperimentConfig:
    protocol_version: str
    manifest_path: Path
    expected_count: int
    tasks: tuple[TaskSpec, ...]
    model: ModelConfig
    reference: ReferenceConfig
    custom: ArmConfig
    baseline: ArmConfig
    results_root: Path
    official_evaluator_command: str = ""
    dataset_name: str = "princeton-nlp/SWE-bench_Verified"
    dataset_revision: str = "b316c349947c29963fce3f4a65967c9807a4b673"
    run_id_prefix: str = "smartm2m"
    config_path: Path = Path("experiment.lock.yaml")
    manifest_source: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path) -> "ExperimentConfig":
        config_path = Path(path).resolve()
        raw = load_document(config_path)
        manifest_config = raw.get("manifest", {})
        if isinstance(manifest_config, dict):
            manifest_value = manifest_config.get("path", raw.get("manifest_path", ""))
            expected_value = manifest_config.get("expected_count", raw.get("expected_count"))
        else:
            manifest_value = raw.get("manifest_path", manifest_config)
            expected_value = raw.get("expected_count")
        if not manifest_value:
            raise ConfigError("configuration must declare manifest.path")
        manifest_path = (config_path.parent / str(manifest_value)).resolve()
        if not manifest_path.exists():
            raise ConfigError(f"manifest does not exist: {manifest_path}")
        manifest = load_data(manifest_path)
        manifest_source: dict[str, Any] = {}
        if isinstance(manifest, list):
            task_values = manifest
        elif isinstance(manifest, dict):
            task_values = manifest.get("tasks", [])
            if isinstance(manifest.get("source"), dict):
                manifest_source = dict(manifest["source"])
        else:
            task_values = []
        if not isinstance(task_values, list):
            raise ConfigError(f"{manifest_path} must contain a tasks array")
        tasks = tuple(TaskSpec.from_mapping(item) for item in task_values)
        expected = int(len(tasks) if expected_value is None else expected_value)
        return cls(
            protocol_version=str(raw.get("protocol_version", "track3-v1")),
            manifest_path=manifest_path,
            expected_count=expected,
            tasks=tasks,
            model=ModelConfig.from_mapping(dict(raw.get("model", {}))),
            reference=ReferenceConfig.from_mapping(dict(raw.get("reference", {}))),
            custom=ArmConfig.from_mapping(dict(raw.get("custom", {}))),
            baseline=ArmConfig.from_mapping(dict(raw.get("baseline", raw.get("custom", {})))),
            results_root=(config_path.parent / str(raw.get("results_root", "../results"))).resolve(),
            official_evaluator_command=str(raw.get("official_evaluator_command", "")),
            dataset_name=str(raw.get("dataset_name", "princeton-nlp/SWE-bench_Verified")),
            dataset_revision=str(raw.get("dataset_revision", "")),
            run_id_prefix=str(raw.get("run_id_prefix", "smartm2m")),
            config_path=config_path,
            manifest_source=manifest_source,
        )

    def validate_manifest(self, *, allow_unresolved: bool = False) -> list[str]:
        errors: list[str] = []
        ids = [task.instance_id for task in self.tasks]
        duplicates = sorted({item for item in ids if ids.count(item) > 1})
        if duplicates:
            errors.append(f"duplicate instance IDs: {', '.join(duplicates)}")
        if self.expected_count <= 0:
            errors.append("expected_count must be positive")
        if len(self.tasks) != self.expected_count:
            errors.append(f"manifest has {len(self.tasks)} tasks but expected_count is {self.expected_count}")
        for task in self.tasks:
            if any(str(field).lower() in {
                "patch", "test_patch", "hints_text", "fail_to_pass", "pass_to_pass",
            } for field in task.metadata):
                errors.append(f"forbidden evaluator field leaked into metadata for {task.instance_id}")
            if self.manifest_source and (not task.repo or not task.repo_url):
                errors.append(f"{task.instance_id}: frozen manifest must include repo and repo_url")
        if self.protocol_version.startswith("track3") and not self.dataset_revision:
            errors.append("dataset_revision must be an immutable revision, not blank")
        if self.manifest_source:
            source_dataset = str(self.manifest_source.get("dataset_name", ""))
            source_revision = str(self.manifest_source.get("dataset_revision", ""))
            if source_dataset and source_dataset != self.dataset_name:
                errors.append(f"manifest dataset_name {source_dataset!r} does not match lock {self.dataset_name!r}")
            if source_revision and source_revision != self.dataset_revision:
                errors.append("manifest dataset_revision does not match the lock file")
            if self.manifest_source.get("selected_ids_sha256"):
                selected_hash = sha256_bytes("\n".join(ids).encode("utf-8"))
                if selected_hash != self.manifest_source["selected_ids_sha256"]:
                    errors.append("frozen manifest ID order does not match selected_ids_sha256")
        elif self.protocol_version.startswith("track3") and self.tasks and self.dataset_revision:
            errors.append("frozen evaluation manifest must declare its dataset source and selection fingerprint")
        if errors and not allow_unresolved:
            raise ConfigError("manifest gate failed: " + "; ".join(errors))
        return errors

    def lock_fingerprint(self) -> str:
        payload = {
            "protocol_version": self.protocol_version,
            "config_sha256": sha256_file(self.config_path),
            "manifest_sha256": sha256_file(self.manifest_path),
            "tasks": [task.generation_projection() for task in self.tasks],
            "model": self.model.__dict__,
            "reference": self.reference.__dict__,
            "custom": self.custom.__dict__,
            "baseline": self.baseline.__dict__,
            "manifest_source": self.manifest_source,
        }
        return sha256_bytes(json.dumps(payload, sort_keys=True, default=str).encode())


def command_exists(command: str) -> bool:
    if shutil.which(command) is not None:
        return True
    # ``pip install --user`` is common in the managed Work image, but its
    # scripts directory is not always on PATH.  Discovering that directory
    # keeps the reference check honest without hard-coding a machine path.
    if not Path(command).is_absolute() or Path(command).parent == Path("."):
        user_script = Path(sysconfig.get_path("scripts", scheme="posix_user")) / command
        return user_script.is_file() and os.access(user_script, os.X_OK)
    return False


def environment_summary() -> dict[str, Any]:
    return {
        "python": os.sys.version,
        "platform": os.sys.platform,
        "machine": platform.machine(),
        "docker": shutil.which("docker") or "",
        "git": shutil.which("git") or "",
    }
