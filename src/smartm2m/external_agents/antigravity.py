"""Google Antigravity CLI ('agy') external agent backend."""

from __future__ import annotations

import os
import re
from pathlib import Path

from .base import ExternalAgent
from .events import ExecutedCommand, TokenUsage, parse_agy_events


class AntigravityAgent(ExternalAgent):
    """External agent backend managing the Google Antigravity CLI ('agy')."""

    name = "agy"
    provider = "google"

    def __init__(
        self,
        *,
        executable: str = "agy",
        model: str = "gemini-3.8-flash-high",
        effort: str | None = "high",
        output_format: str = "stream-json",
        dangerously_skip_permissions: bool = True,
        disable_slash_commands: bool = True,
        sandbox: bool = False,
    ):
        super().__init__(executable=executable, model=model, effort=effort)
        self.output_format = output_format
        self.dangerously_skip_permissions = dangerously_skip_permissions
        self.disable_slash_commands = disable_slash_commands
        self.sandbox = sandbox

    def build_command(self, prompt: str, workspace: Path) -> list[str]:
        cmd = [
            self.resolve_executable(),
            "-p",
            prompt,
            "--output-format",
            self.output_format,
            "--model",
            self.configured_model,
        ]
        # Only pass --effort if specified and not conflicting with model name suffix
        if self.effort:
            model_lower = self.configured_model.lower()
            # If model name has suffix like -high, -medium, -low, pass effort only if it matches
            has_suffix = any(model_lower.endswith(f"-{lvl}") for lvl in ("low", "medium", "high", "max"))
            if not has_suffix or model_lower.endswith(f"-{self.effort.lower()}"):
                cmd.extend(["--effort", self.effort])
        if self.dangerously_skip_permissions:
            cmd.append("--dangerously-skip-permissions")
        if self.disable_slash_commands:
            cmd.append("--disable-slash-commands")
        if self.sandbox:
            cmd.append("--sandbox")
        return cmd

    def build_env(self, workspace: Path) -> dict[str, str]:
        """Construct a clean execution environment that strictly isolates the measured run."""
        env = os.environ.copy()

        # Prevent leakage of current development session context
        forbidden_prefixes = (
            "ANTIGRAVITY_",
            "AGY_",
            "GEMINI_",
            "CONVERSATION_",
            "SESSION_",
            "SUBAGENT_",
            "DEVELOPMENT_",
            "TASK_ID",
            "PARENT_CONVERSATION",
        )
        for key in list(env.keys()):
            if any(key.upper().startswith(prefix) for prefix in forbidden_prefixes):
                env.pop(key, None)

        # Ensure user local bin is in PATH for agy and helper tools
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
        usage, commands, conversation_id, reported_model, _ = parse_agy_events(stdout_text)
        return usage, commands, conversation_id, reported_model

    def detect_provider_block(
        self,
        stdout_text: str,
        stderr_text: str,
        returncode: int,
    ) -> tuple[bool, str]:
        combined = f"{stdout_text}\n{stderr_text}".lower()
        patterns = [
            (r"quota\s+exceeded|resource_exhausted|exhausted\s+your\s+quota|status:\s*429", "quota_exceeded"),
            (r"rate_limit|rate\s+limit|too\s+many\s+requests", "rate_limit"),
            (r"authentication\s+failed|unauthorized|invalid\s+credentials|status:\s*401", "auth_failure"),
            (r"invalid\s+model\s+selection|model\s+not\s+found|unknown\s+model", "model_unavailable"),
            (r"account\s+suspended|billing\s+blocked", "billing_blocked"),
        ]
        for pattern, reason in patterns:
            if re.search(pattern, combined):
                return True, reason
        return False, ""
