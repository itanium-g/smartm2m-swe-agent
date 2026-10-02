"""OpenAI Codex CLI external agent backend."""

from __future__ import annotations

import os
import re
from pathlib import Path

from .base import ExternalAgent
from .events import ExecutedCommand, TokenUsage, parse_codex_events


class CodexAgent(ExternalAgent):
    """External agent backend managing the OpenAI Codex CLI."""

    name = "codex"
    provider = "openai"

    def __init__(
        self,
        *,
        executable: str = "codex",
        model: str = "gpt-6.1-sol",
        ephemeral: bool = True,
        sandbox: str = "workspace-write",
        ignore_user_config: bool = True,
        ignore_rules: bool = True,
        structured_output: bool = True,
        reasoning_effort: str | None = None,
    ):
        super().__init__(executable=executable, model=model, effort=reasoning_effort)
        self.ephemeral = ephemeral
        self.sandbox = sandbox
        self.ignore_user_config = ignore_user_config
        self.ignore_rules = ignore_rules
        self.structured_output = structured_output

    def build_command(self, prompt: str, workspace: Path) -> list[str]:
        cmd = [self.resolve_executable(), "exec"]
        if self.ephemeral:
            cmd.append("--ephemeral")
        if self.structured_output:
            cmd.append("--json")
        if self.sandbox:
            cmd.extend(["--sandbox", self.sandbox])
        if self.ignore_user_config:
            cmd.append("--ignore-user-config")
        if self.ignore_rules:
            cmd.append("--ignore-rules")
        if self.effort:
            cmd.extend(["-c", f"model_reasoning_effort={self.effort}"])
        cmd.extend(["-m", self.configured_model])
        cmd.extend(["-C", str(workspace.resolve())])
        cmd.append(prompt)
        return cmd

    def build_env(self, workspace: Path) -> dict[str, str]:
        env = os.environ.copy()
        # Ensure user local bin is in PATH for codex and helper tools
        local_bin = str(Path.home() / ".local" / "bin")
        current_path = env.get("PATH", "")
        if local_bin not in current_path.split(os.pathsep):
            env["PATH"] = f"{local_bin}{os.pathsep}{current_path}"
        env["CI"] = "1"
        env["PAGER"] = "cat"
        return env

    def parse_stream(
        self,
        stdout_text: str,
    ) -> tuple[TokenUsage, list[ExecutedCommand], str | None, str | None]:
        usage, commands, thread_id, _ = parse_codex_events(stdout_text)
        return usage, commands, thread_id, None

    def detect_provider_block(
        self,
        stdout_text: str,
        stderr_text: str,
        returncode: int,
    ) -> tuple[bool, str]:
        combined = f"{stdout_text}\n{stderr_text}".lower()
        patterns = [
            (r"quota\s+exceeded|insufficient_quota|exceeded\s+your\s+current\s+quota", "quota_exceeded"),
            (r"rate_limit_exceeded|rate\s+limit|too\s+many\s+requests|status:\s*429", "rate_limit"),
            (r"invalid_api_key|authentication\s+failed|unauthorized|status:\s*401", "auth_failure"),
            (r"model_not_found|does\s+not\s+exist\s+or\s+you\s+do\s+not\s+have\s+access", "model_unavailable"),
            (r"account\s+deactivated|billing\s+hard\s+limit", "billing_blocked"),
        ]
        for pattern, reason in patterns:
            if re.search(pattern, combined):
                return True, reason
        return False, ""
