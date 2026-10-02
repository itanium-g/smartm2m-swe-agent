"""External coding-agent benchmark subsystem for Codex CLI and Antigravity CLI."""

from __future__ import annotations

from .antigravity import AntigravityAgent
from .base import ExternalAgent
from .codex import CodexAgent
from .events import ExecutedCommand, TokenUsage
from .metadata import ExternalTaskResult
from .prompts import COMMON_PROMPT_TEMPLATE, hash_prompt, render_prompt

__all__ = [
    "COMMON_PROMPT_TEMPLATE",
    "AntigravityAgent",
    "CodexAgent",
    "ExecutedCommand",
    "ExternalAgent",
    "ExternalTaskResult",
    "TokenUsage",
    "hash_prompt",
    "render_prompt",
]
