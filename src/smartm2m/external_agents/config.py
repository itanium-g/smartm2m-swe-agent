"""Configuration parser and validator for external agents benchmark."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import ConfigError, TaskSpec, load_data, load_document, load_env_file


@dataclass(frozen=True)
class ExternalAgentsConfig:
    """Configuration for external coding agent benchmark runs."""

    protocol_version: str
    manifest_path: Path
    expected_count: int
    tasks: tuple[TaskSpec, ...]
    attempts_per_task: int = 1
    wall_time_seconds: int = 2700
    sequential: bool = True
    command_timeout_seconds: int = 120
    # Codex settings
    codex_executable: str = "codex"
    codex_model: str = "gpt-6.1-sol"
    codex_sandbox: str = "workspace-write"
    codex_ephemeral: bool = True
    codex_structured_output: bool = True
    codex_ignore_user_config: bool = True
    codex_ignore_rules: bool = True
    codex_effort: str | None = None
    # AGY settings
    agy_executable: str = "agy"
    agy_model: str = "gemini-3.8-flash-high"
    agy_effort: str | None = "high"
    agy_output_format: str = "stream-json"
    agy_dangerously_skip_permissions: bool = True
    agy_disable_slash_commands: bool = True
    # Evaluator settings
    dataset_name: str = "MariusHobbhahn/swe-bench-verified-mini"
    dataset_revision: str = "b316c349947c29963fce3f4a65967c9807a4b673"
    evaluator_metadata_dataset: str = "SWE-bench/SWE-bench_Verified"
    evaluator_metadata_revision: str = "78f471bf655a3137b2e8a75af1501690ec009ec3"
    split: str = "test"
    reuse_pinned_swebench: bool = True
    # Paths & provenance
    results_root: Path = Path("results")
    config_path: Path = Path("configs/external-agents.yaml")
    config_sha256: str = ""
    manifest_sha256: str = ""
    manifest_source: dict[str, Any] = field(default_factory=dict)

    @property
    def reference(self) -> Any:
        from types import SimpleNamespace
        return SimpleNamespace(split=self.split)

    @classmethod
    def load(cls, path: str | Path) -> "ExternalAgentsConfig":
        load_env_file()
        config_path = Path(path).resolve()
        raw = load_document(config_path)

        manifest_info = raw.get("manifest", {})
        if isinstance(manifest_info, dict):
            manifest_val = manifest_info.get("path", raw.get("manifest_path", ""))
            expected_val = manifest_info.get("expected_count", raw.get("expected_count"))
        else:
            manifest_val = raw.get("manifest_path", manifest_info)
            expected_val = raw.get("expected_count")

        if not manifest_val:
            raise ConfigError("configuration must declare manifest.path")

        manifest_path = (config_path.parent / str(manifest_val)).resolve()
        if not manifest_path.exists():
            raise ConfigError(f"manifest does not exist: {manifest_path}")

        manifest_data = load_data(manifest_path)
        manifest_source: dict[str, Any] = {}
        if isinstance(manifest_data, list):
            task_items = manifest_data
        elif isinstance(manifest_data, dict):
            task_items = manifest_data.get("tasks", [])
            if isinstance(manifest_data.get("source"), dict):
                manifest_source = dict(manifest_data["source"])
        else:
            task_items = []

        tasks = tuple(TaskSpec.from_mapping(item) for item in task_items)
        expected = int(len(tasks) if expected_val is None else expected_val)

        exec_cfg = raw.get("execution", {})
        codex_cfg = raw.get("codex", {})
        agy_cfg = raw.get("agy", {})
        eval_cfg = raw.get("evaluator", {})

        cfg_bytes = config_path.read_bytes()
        man_bytes = manifest_path.read_bytes()

        return cls(
            protocol_version=str(raw.get("protocol_version", "external-agents-v1")),
            manifest_path=manifest_path,
            expected_count=expected,
            tasks=tasks,
            attempts_per_task=int(exec_cfg.get("attempts_per_task", 1)),
            wall_time_seconds=int(exec_cfg.get("wall_time_seconds", 2700)),
            sequential=bool(exec_cfg.get("sequential", True)),
            command_timeout_seconds=int(exec_cfg.get("command_timeout_seconds", 120)),
            codex_executable=str(codex_cfg.get("executable", "codex")),
            codex_model=str(codex_cfg.get("model", "gpt-6.1-sol")),
            codex_sandbox=str(codex_cfg.get("sandbox", "workspace-write")),
            codex_ephemeral=bool(codex_cfg.get("ephemeral", True)),
            codex_structured_output=bool(codex_cfg.get("structured_output", True)),
            codex_ignore_user_config=bool(codex_cfg.get("ignore_user_config", True)),
            codex_ignore_rules=bool(codex_cfg.get("ignore_rules", True)),
            codex_effort=codex_cfg.get("effort"),
            agy_executable=str(agy_cfg.get("executable", "agy")),
            agy_model=str(agy_cfg.get("model", "gemini-3.8-flash-high")),
            agy_effort=agy_cfg.get("effort", "high"),
            agy_output_format=str(agy_cfg.get("output_format", "stream-json")),
            agy_dangerously_skip_permissions=bool(agy_cfg.get("dangerously_skip_permissions", True)),
            agy_disable_slash_commands=bool(agy_cfg.get("disable_slash_commands", True)),
            dataset_name=str(eval_cfg.get("dataset_name", "MariusHobbhahn/swe-bench-verified-mini")),
            dataset_revision=str(eval_cfg.get("dataset_revision", "b316c349947c29963fce3f4a65967c9807a4b673")),
            evaluator_metadata_dataset=str(eval_cfg.get("evaluator_metadata_dataset", "SWE-bench/SWE-bench_Verified")),
            evaluator_metadata_revision=str(
                eval_cfg.get("evaluator_metadata_revision", "78f471bf655a3137b2e8a75af1501690ec009ec3")
            ),
            split=str(eval_cfg.get("split", "test")),
            reuse_pinned_swebench=bool(eval_cfg.get("reuse_pinned_swebench", True)),
            results_root=(config_path.parent / str(raw.get("results_root", "results"))).resolve(),
            config_path=config_path,
            config_sha256=hashlib.sha256(cfg_bytes).hexdigest(),
            manifest_sha256=hashlib.sha256(man_bytes).hexdigest(),
            manifest_source=manifest_source,
        )

    def validate_manifest(self) -> list[str]:
        errors: list[str] = []
        ids = [t.instance_id for t in self.tasks]
        if len(self.tasks) != self.expected_count:
            errors.append(f"task count {len(self.tasks)} != expected {self.expected_count}")
        if len(set(ids)) != len(ids):
            errors.append("manifest contains duplicate instance IDs")
        for t in self.tasks:
            if not t.base_commit:
                errors.append(f"{t.instance_id}: base_commit missing")
        return errors
