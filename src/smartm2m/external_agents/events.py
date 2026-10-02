"""Structured event stream parsing and token accounting for Codex and Antigravity CLIs."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class TokenUsage:
    """Observed token usage from CLI structured streams."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    thinking_tokens: int | None = None
    cache_tokens: int | None = None
    total_tokens: int | None = None

    def as_dict(self) -> dict[str, int | None]:
        return asdict(self)


@dataclass(frozen=True)
class ExecutedCommand:
    """Record of a tool-executed shell command observed during agent run."""

    command: str
    returncode: int | None = None
    output: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_codex_events(
    stdout_text: str,
) -> tuple[TokenUsage, list[ExecutedCommand], str | None, str | None]:
    """Parse Codex CLI NDJSON output stream.

    Returns:
        (usage, executed_commands, thread_id, last_message_text)
    """
    thread_id: str | None = None
    last_message: str | None = None
    commands: list[ExecutedCommand] = []

    # Token counters across turns
    input_tokens = 0
    cached_tokens = 0
    output_tokens = 0
    thinking_tokens = 0
    has_usage = False

    for line in stdout_text.splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        event_type = event.get("type")
        if event_type == "thread.started":
            thread_id = event.get("thread_id")
        elif event_type == "item.completed":
            item = event.get("item", {})
            item_type = item.get("type")
            if item_type == "agent_message":
                last_message = item.get("text")
            elif item_type == "command_execution":
                cmd = item.get("command", "")
                rc = item.get("exit_code")
                out = item.get("aggregated_output", "")
                commands.append(ExecutedCommand(command=cmd, returncode=rc, output=out))
        elif event_type == "turn.completed":
            usage = event.get("usage", {})
            if usage:
                has_usage = True
                input_tokens += int(usage.get("input_tokens", 0) or 0)
                cached_tokens += int(usage.get("cached_input_tokens", 0) or 0)
                output_tokens += int(usage.get("output_tokens", 0) or 0)
                thinking_tokens += int(usage.get("reasoning_output_tokens", 0) or 0)

    if not has_usage:
        usage_obj = TokenUsage()
    else:
        total = input_tokens + output_tokens
        usage_obj = TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            thinking_tokens=thinking_tokens,
            cache_tokens=cached_tokens,
            total_tokens=total,
        )

    return usage_obj, commands, thread_id, last_message


def parse_agy_events(
    stdout_text: str,
) -> tuple[TokenUsage, list[ExecutedCommand], str | None, str | None, str | None]:
    """Parse Antigravity CLI stream-json NDJSON output stream.

    Returns:
        (usage, executed_commands, conversation_id, reported_model, final_response)
    """
    conversation_id: str | None = None
    reported_model: str | None = None
    final_response: str | None = None
    commands: list[ExecutedCommand] = []

    # Step-level token accounting in case final result event is missing
    step_input_tokens = 0
    step_output_tokens = 0
    step_thinking_tokens = 0
    step_cache_tokens = 0
    has_step_usage = False

    result_usage: TokenUsage | None = None

    for line in stdout_text.splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        event_name = event.get("event")
        if event_name == "init":
            conversation_id = event.get("conversation_id")
            init_data = event.get("init", {})
            reported_model = init_data.get("model")
        elif event_name == "step_update":
            step = event.get("step_update", {})
            if not conversation_id and step.get("conversation_id"):
                conversation_id = step.get("conversation_id")
            step_type = step.get("step_type")
            if step_type == "tool" and step.get("state") == "DONE":
                tool_info = step.get("tool_info", {})
                params = tool_info.get("parameters", {})
                cmd = params.get("CommandLine") or params.get("command") or ""
                if cmd:
                    out = str(tool_info.get("output", ""))
                    rc = tool_info.get("exit_code") if "exit_code" in tool_info else tool_info.get("returncode")
                    commands.append(ExecutedCommand(command=cmd, returncode=rc, output=out))
            usage = step.get("usage", {})
            if usage:
                has_step_usage = True
                step_input_tokens = max(step_input_tokens, int(usage.get("input_tokens", 0) or 0))
                step_output_tokens += int(usage.get("output_tokens", 0) or 0)
                step_thinking_tokens += int(usage.get("thinking_tokens", 0) or 0)
                step_cache_tokens = max(step_cache_tokens, int(usage.get("cache_read_tokens", 0) or 0))
        elif event_name == "result":
            res = event.get("result", {})
            if not conversation_id and res.get("conversation_id"):
                conversation_id = res.get("conversation_id")
            final_response = res.get("response")
            usage = res.get("usage", {})
            if usage:
                in_tok = usage.get("input_tokens")
                out_tok = usage.get("output_tokens")
                think_tok = usage.get("thinking_tokens")
                cache_tok = usage.get("cache_read_tokens")
                tot_tok = usage.get("total_tokens")
                result_usage = TokenUsage(
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                    thinking_tokens=think_tok,
                    cache_tokens=cache_tok,
                    total_tokens=tot_tok,
                )

    if result_usage is not None:
        final_usage = result_usage
    elif has_step_usage:
        total = step_input_tokens + step_output_tokens
        final_usage = TokenUsage(
            input_tokens=step_input_tokens,
            output_tokens=step_output_tokens,
            thinking_tokens=step_thinking_tokens,
            cache_tokens=step_cache_tokens,
            total_tokens=total,
        )
    else:
        final_usage = TokenUsage()

    return final_usage, commands, conversation_id, reported_model, final_response
