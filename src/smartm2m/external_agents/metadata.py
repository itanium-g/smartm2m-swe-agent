"""Task result model, metadata persistence, and secret redaction."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .events import ExecutedCommand


def redact_secrets(value: str) -> str:
    """Redact sensitive tokens, keys, and credentials from captured logs."""
    replacements = [
        (r"(?i)(authorization\s*:\s*bearer\s+)[^\s\"']+", r"\1[REDACTED]"),
        (r"(?i)(api[_-]?key\s*[=:]\s*)[^\s\"']+", r"\1[REDACTED]"),
        (r"(?i)(token\s*[=:]\s*)[^\s\"']+", r"\1[REDACTED]"),
        (r"\bgsk_[A-Za-z0-9_]{20,}\b", "[REDACTED]"),
        (r"\bsk-[A-Za-z0-9_]{20,}\b", "[REDACTED]"),
        (r"\bghp_[A-Za-z0-9]{20,}\b", "[REDACTED]"),
        (r"\bgithub_pat_[A-Za-z0-9_]{20,}\b", "[REDACTED]"),
    ]
    for pattern, replacement in replacements:
        value = re.sub(pattern, replacement, value)
    for env_var in ("MISTRAL_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY", "GITHUB_TOKEN", "GH_TOKEN"):
        val = os.environ.get(env_var)
        if val and len(val) >= 8:
            value = value.replace(val, "[REDACTED]")
    return value


def redact_json(value: Any) -> Any:
    """Recursively redact strings in nested data structures."""
    if isinstance(value, str):
        return redact_secrets(value)
    if isinstance(value, list):
        return [redact_json(item) for item in value]
    if isinstance(value, dict):
        return {key: redact_json(item) for key, item in value.items()}
    return value


@dataclass
class ExternalTaskResult:
    """Common result model representing one task attempt by an external coding agent."""

    instance_id: str
    agent: str
    provider: str
    cli_version: str
    configured_model: str
    reported_model: str | None
    effort_or_reasoning_setting: str | None
    base_commit: str
    workspace_path: str
    start_timestamp: str
    end_timestamp: str
    wall_duration_seconds: float
    exit_code: int | None
    timed_out: bool
    terminal_status: str  # generated, generation_failed, timed_out, provider_blocked
    termination_reason: str
    stdout_file: str
    stderr_file: str
    events_file: str
    patch_file: str
    input_tokens: int | None
    output_tokens: int | None
    thinking_tokens: int | None
    cache_tokens: int | None
    total_tokens: int | None
    patch: str
    patch_sha256: str
    prompt_sha256: str
    config_sha256: str
    git_head_before: str
    git_status_before: str
    git_status_after: str
    evaluator_status: str = "not_evaluated"
    commands_count: int = 0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExternalTaskResult":
        # Filter data to known fields
        known_fields = {f for f in cls.__annotations__}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)


def write_task_artifacts(
    task_dir: Path,
    result: ExternalTaskResult,
    *,
    stdout_raw: str,
    stderr_raw: str,
    commands: list[ExecutedCommand],
) -> None:
    """Persist all task attempt artifacts with redacted secrets."""
    task_dir.mkdir(parents=True, exist_ok=True)

    # 1. metadata.json
    metadata_path = task_dir / "metadata.json"
    safe_dict = redact_json(result.as_dict())
    metadata_path.write_text(json.dumps(safe_dict, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # 2. stdout.log
    stdout_path = task_dir / "stdout.log"
    stdout_path.write_text(redact_secrets(stdout_raw), encoding="utf-8")

    # 3. stderr.log
    stderr_path = task_dir / "stderr.log"
    stderr_path.write_text(redact_secrets(stderr_raw), encoding="utf-8")

    # 4. events.jsonl
    events_path = task_dir / "events.jsonl"
    safe_lines = [
        redact_secrets(line)
        for line in stdout_raw.splitlines()
        if line.strip().startswith("{")
    ]
    events_path.write_text("\n".join(safe_lines) + ("\n" if safe_lines else ""), encoding="utf-8")

    # 5. commands.jsonl
    commands_path = task_dir / "commands.jsonl"
    with commands_path.open("w", encoding="utf-8") as stream:
        for cmd in commands:
            safe_cmd = redact_json(cmd.as_dict())
            stream.write(json.dumps(safe_cmd, ensure_ascii=False) + "\n")

    # 6. patch.diff
    patch_path = task_dir / "patch.diff"
    patch_path.write_text(result.patch, encoding="utf-8")
