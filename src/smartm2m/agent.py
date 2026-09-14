"""The custom Track 3 controller.

The controller is intentionally small and inspectable. Its differentiators are
operational: typed tools, executed-test evidence, patch identity, checkpoints,
and bounded recovery. It does not receive SWE-bench gold fields.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any

from .config import ArmConfig, ModelConfig, TaskSpec
from .model import ModelError
from .protocol import ModelClient, ModelResponse, ToolCall
from .task import generation_payload
from .tools import ToolResult, ToolRunner, tool_schemas


SYSTEM_PROMPT = """You are the SMARTM2M Track 3 custom software-engineering agent.
Solve the issue in the supplied repository using the available typed tools.
Inspect before editing. Make the smallest general source-only change that fixes
the issue. Do not edit tests, build files, configuration, logs, or generated
artifacts. Reproduce the failure when practical, run a declared test command
after edits, inspect the diff, and call submit_patch only after the actual test
result supports the patch. Never claim that a test passed without observing a
tool result with a zero exit status. If a patch breaks import/syntax/build,
repair from the rollback checkpoint. Do not use hidden evaluator fields or
guess hidden tests.
"""


@dataclass
class AgentResult:
    instance_id: str
    status: str
    reason: str
    turns: int
    model_requests: int
    estimated_cost_usd: float | None
    patch: str
    patch_sha256: str
    events: list[dict[str, Any]] = field(default_factory=list)
    commands: list[dict[str, Any]] = field(default_factory=list)
    recovery_used: bool = False
    validation_required: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "status": self.status,
            "reason": self.reason,
            "turns": self.turns,
            "model_requests": self.model_requests,
            "estimated_cost_usd": self.estimated_cost_usd,
            "patch_sha256": self.patch_sha256,
            "recovery_used": self.recovery_used,
            "validation_required": self.validation_required,
        }


def _assistant_message(response: ModelResponse) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": response.content or None}
    if response.tool_calls:
        message["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": json.dumps(call.arguments, ensure_ascii=False)},
            }
            for call in response.tool_calls
        ]
    return message


def _tool_message(call: ToolCall, result: ToolResult) -> dict[str, Any]:
    return {
        "role": "tool",
        "tool_call_id": call.id,
        "content": json.dumps({"ok": result.ok, "content": result.content, "metadata": result.metadata}, ensure_ascii=False),
    }


def _event(kind: str, **values: Any) -> dict[str, Any]:
    return {"timestamp": time.time(), "kind": kind, **values}


class CustomAgent:
    def __init__(self, model: ModelClient, *, arm: ArmConfig, model_config: ModelConfig | None = None):
        self.model = model
        self.arm = arm
        self.model_config = model_config or ModelConfig()

    def run(self, task: TaskSpec, runner: ToolRunner) -> AgentResult:
        payload = generation_payload(task)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Repository workspace: .\n"
                    f"Task input (safe projection):\n{json.dumps(payload, indent=2, ensure_ascii=False)}\n"
                    f"Declared visible test commands: {list(task.test_commands)}\n"
                    "Start by using list_files, search, or read_file. You must perform at least one tool action."
                ),
            },
        ]
        events: list[dict[str, Any]] = []
        seen: dict[str, int] = {}
        recovery_used = False
        total_cost: float | None = 0.0
        turns = 0
        status = "provider_error"
        reason = "agent did not reach a terminal submission"
        started = time.monotonic()

        while turns < self.arm.max_turns:
            if time.monotonic() - started > self.arm.wall_time_seconds:
                status, reason = "wall_time_exhausted", "episode wall-time limit reached"
                break
            turns += 1
            try:
                response = self.model.complete(
                    messages,
                    tool_schemas(task),
                    temperature=self.model_config.temperature,
                    seed=self.model_config.seed,
                    max_tokens=self.model_config.max_tokens,
                )
            except ModelError as exc:
                events.append(_event("model_error", error=str(exc)))
                status, reason = "provider_error", str(exc)
                break
            usage = response.usage
            if usage.estimated_cost_usd is not None:
                total_cost = (total_cost or 0.0) + usage.estimated_cost_usd
                if total_cost > self.arm.cost_limit_usd:
                    events.append(_event("budget_exhausted", cost_usd=total_cost, limit_usd=self.arm.cost_limit_usd))
                    status, reason = "budget_exhausted", "observed model usage exceeded episode cost limit"
                    break
            elif total_cost == 0.0:
                total_cost = None
            events.append(
                _event(
                    "model_response",
                    turn=turns,
                    content=response.content,
                    tool_calls=[{"id": c.id, "name": c.name, "arguments": c.arguments} for c in response.tool_calls],
                    finish_reason=response.finish_reason,
                    usage=usage.raw,
                )
            )
            messages.append(_assistant_message(response))
            if not response.tool_calls:
                messages.append({
                    "role": "user",
                    "content": "Use one of the typed tools now. If the patch is ready, call get_diff, run_tests, then submit_patch.",
                })
                continue

            submitted = False
            for call in response.tool_calls:
                result = runner.execute(call)
                events.append(_event("tool_result", turn=turns, tool_call_id=call.id, name=call.name, result={
                    "ok": result.ok, "content": result.content, "metadata": result.metadata,
                }))
                messages.append(_tool_message(call, result))

                if call.name == "run_tests" and result.metadata.get("failure_class") == "build_failure":
                    if runner.checkpoints:
                        rollback = runner.rollback()
                        recovery_used = True
                        events.append(_event("automatic_rollback", reason="build_failure", result=rollback.content))
                        messages.append({
                            "role": "user",
                            "content": "The last patch caused a syntax/import/build failure. The controller restored the latest checkpoint. Diagnose the observed failure and apply a corrected source-only patch.",
                        })

                if call.name in {"apply_patch", "run_tests", "rollback", "submit_patch"}:
                    try:
                        state = runner.state_hash()
                    except Exception as exc:  # keep evidence even if a workspace becomes unhealthy
                        state = f"state-error:{exc}"
                    signature = hashlib.sha256((call.name + json.dumps(call.arguments, sort_keys=True) + state).encode()).hexdigest()
                    seen[signature] = seen.get(signature, 0) + 1
                    if seen[signature] >= 2 and not recovery_used:
                        if runner.checkpoints:
                            rollback = runner.rollback()
                            recovery_used = True
                            events.append(_event("loop_recovery", repeated_action=call.name, result=rollback.content))
                            messages.append({
                                "role": "user",
                                "content": "A repeated action/workspace state was detected. The controller rolled back once. Change strategy: inspect a different relevant file or formulate a smaller patch.",
                            })
                        else:
                            status, reason = "loop_exhausted", "repeated action/workspace state with no checkpoint"
                            break
                    elif seen[signature] >= 2 and recovery_used:
                        status, reason = "loop_exhausted", "repeated action/workspace state after recovery"
                        break

                if call.name == "submit_patch" and result.ok:
                    submitted = True
                    break
            if status == "loop_exhausted":
                break
            if submitted:
                patch = runner.get_diff().content
                if not patch:
                    status, reason = "verifier_rejected", "submit_patch was called with no source diff"
                else:
                    status, reason = "submitted", "patch sealed; clean replay validation is required"
                break

        else:
            status, reason = "turn_limit_exhausted", "episode turn limit reached"

        try:
            patch = runner.get_diff().content
        except Exception:
            patch = ""
        patch_hash = hashlib.sha256(patch.encode("utf-8")).hexdigest()
        return AgentResult(
            task.instance_id,
            status,
            reason,
            turns,
            getattr(self.model, "calls", turns),
            total_cost,
            patch,
            patch_hash,
            events,
            runner.command_records(),
            recovery_used,
            True,
        )
