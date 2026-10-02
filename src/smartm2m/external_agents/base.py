"""Abstract base class for external CLI coding agents."""

from __future__ import annotations

import os
import shutil
import subprocess
import sysconfig
from abc import ABC, abstractmethod
from pathlib import Path

from .events import ExecutedCommand, TokenUsage


class ExternalAgent(ABC):
    """Abstract interface for external headless CLI coding agents."""

    name: str
    provider: str
    executable: str
    configured_model: str
    effort: str | None

    def __init__(
        self,
        *,
        executable: str,
        model: str,
        effort: str | None = None,
    ):
        self.executable = executable
        self.configured_model = model
        self.effort = effort

    def resolve_executable(self) -> str:
        """Resolve the executable binary, checking PATH and common user directories."""
        if shutil.which(self.executable) is not None:
            return self.executable

        # Check user local bin candidates
        candidates = [
            Path.home() / ".local" / "bin" / self.executable,
            Path(sysconfig.get_path("scripts", scheme="posix_user")) / self.executable,
        ]
        for candidate in candidates:
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)

        return self.executable

    def detect_version(self) -> str:
        """Probe the CLI executable to detect its version string."""
        resolved = self.resolve_executable()
        try:
            proc = subprocess.run(
                [resolved, "--version"],
                text=True,
                capture_output=True,
                timeout=15,
                check=False,
            )
            out = proc.stdout.strip() or proc.stderr.strip()
            return out or f"{self.name} (unknown version)"
        except Exception as exc:
            return f"{self.name} (error detecting version: {exc})"

    @abstractmethod
    def build_command(self, prompt: str, workspace: Path) -> list[str]:
        """Construct the subprocess CLI argv for a single task run."""
        ...

    @abstractmethod
    def build_env(self, workspace: Path) -> dict[str, str]:
        """Construct a clean execution environment that prevents session leakage."""
        ...

    @abstractmethod
    def parse_stream(
        self,
        stdout_text: str,
    ) -> tuple[TokenUsage, list[ExecutedCommand], str | None, str | None]:
        """Parse structured output into TokenUsage, commands, session_id, and reported_model."""
        ...

    @abstractmethod
    def detect_provider_block(
        self,
        stdout_text: str,
        stderr_text: str,
        returncode: int,
    ) -> tuple[bool, str]:
        """Check whether output indicates a provider-side quota/rate-limit/auth block."""
        ...
