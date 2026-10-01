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

SYSTEM_PROMPT = """You are the SMARTM2M software-engineering agent.
Solve the issue using the supplied repository and typed tools.

1. Inspect the implementation before editing. List the relevant package, search
   for a short symbol or exact error, then read the surrounding function body.
   Issue examples describe behavior; their helper classes may not exist in the
   repository. Search invariant symbols rather than example names.
2. Explain the cause using the observed code. Make a minimal general change to
   package source. Prefer edit_file with an exact, unique block copied from the
   current read_file output. Re-read after a rejected edit or rollback.
   Do not edit tests, documentation, configuration, build files, or generated
   files. You may read existing tests to understand expected behavior.
3. Find the repository's native test runner and select a test file, module, or
   subsystem relevant to the change. Declared default commands may be broad;
   inspect the repository before choosing one. Use the project's runner rather
   than assuming pytest is installed. Diagnose assertion failures in place.
   An import failure can mean the selected test name or environment is wrong;
   inspect the diagnostic before changing or discarding source code.
4. Use get_diff to review the complete change. After a relevant test passes,
   call submit_patch. Every edit invalidates earlier test evidence. A failing
   relevant test remains evidence of a problem; do not select unrelated passing
   tests to bypass it. Clean replay and official grading happen after submission.
5. Change approach when an action repeats without progress. Inspect a different
   symbol, read another range, or refine the existing change. Rollback is for a
   confirmed source break, not for an ordinary assertion or repeated command.
6. Use only issue text and repository evidence. Do not retrieve gold patches,
   hidden tests, evaluation labels, or solutions from outside the workspace.
"""


@dataclass
class AgentResult:
    instance_id: str
    status: str
    reason: str
    turns: int
    model_requests: int
    model_attempts: int
    estimated_cost_usd: float | None
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    patch: str
    patch_sha256: str
    events: list[dict[str, Any]] = field(default_factory=list)
    commands: list[dict[str, Any]] = field(default_factory=list)
    recovery_used: bool = False
    validation_required: bool = True
    last_successful_test_command: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "status": self.status,
            "reason": self.reason,
            "turns": self.turns,
            "model_requests": self.model_requests,
            "model_attempts": self.model_attempts,
            "estimated_cost_usd": self.estimated_cost_usd,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "patch_sha256": self.patch_sha256,
            "recovery_used": self.recovery_used,
            "validation_required": self.validation_required,
            "last_successful_test_command": self.last_successful_test_command,
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
        "name": call.name,
        "content": json.dumps({"ok": result.ok, "content": result.content, "metadata": result.metadata}, ensure_ascii=False),
    }


def _prune_history(messages: list[dict[str, Any]], max_chars: int = 60000) -> list[dict[str, Any]]:
    """Bound context without breaking JSON tool output or tool-call pairing."""
    def size(items: list[dict[str, Any]]) -> int:
        return len(json.dumps(items, ensure_ascii=False))

    if size(messages) <= max_chars:
        return messages
    pruned = []
    cutoff = len(messages) - 6
    for index, message in enumerate(messages):
        if index < 2 or index >= cutoff or message.get("role") != "tool":
            pruned.append(message)
            continue
        try:
            payload = json.loads(str(message.get("content") or ""))
        except (ValueError, TypeError):
            pruned.append(message)
            continue
        if not isinstance(payload, dict) or not isinstance(payload.get("content"), str):
            pruned.append(message)
            continue
        content = payload["content"]
        if len(content) > 1000:
            payload["content"] = content[:400] + "\n[older output shortened]\n" + content[-400:]
            pruned.append({**message, "content": json.dumps(payload, ensure_ascii=False)})
        else:
            pruned.append(message)
    prefix = pruned[:2]
    history = pruned[2:]
    omitted = False
    notice = {"role": "user", "content": (
        "Earlier complete tool interactions were omitted to bound context. "
        "The workspace still contains your edits. Use get_diff or read_file to inspect its current state."
    )}
    # Remove whole assistant/tool exchanges, retaining at least two recent turns.
    while size(prefix + ([notice] if omitted else []) + history) > max_chars:
        starts = [i for i, message in enumerate(history) if message.get("role") == "assistant"]
        if len(starts) <= 2:
            break
        history = history[starts[1]:]
        omitted = True
    return prefix + ([notice] if omitted else []) + history


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
                    f"Base repository test runner: {list(task.test_commands)}\n"
                    "Note: Always specify the targeted test module or test file in run_tests (e.g. 'python tests/runtests.py <app_name>' or 'python -m pytest tests/<test_file>.py'); running without a test target will time out.\n"
                    "Start by using list_files, search, or read_file. You must perform at least one tool action."
                ),
            },
        ]
        events: list[dict[str, Any]] = []
        seen: dict[str, int] = {}
        last_read_signature = ""
        consecutive_file_reads = 0
        recovery_used = False
        inspected = False
        observed_cost = 0.0
        cost_known = True
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0
        turns = 0
        consecutive_protocol_errors = 0
        logical_requests_before = int(getattr(self.model, "logical_requests", 0))
        request_attempts_before = int(getattr(self.model, "request_attempts", logical_requests_before))
        status = "provider_error"
        reason = "agent did not reach a terminal submission"
        started = time.monotonic()

        while turns < self.arm.max_turns:
            if time.monotonic() - started > self.arm.wall_time_seconds:
                status, reason = "wall_time_exhausted", "episode wall-time limit reached"
                break
            turns += 1
            send_messages = _prune_history(
                messages, max_chars=24000 if self.model_config.provider == "groq" else 60000
            )
            try:
                response = self.model.complete(
                    send_messages,
                    tool_schemas(task),
                    temperature=self.model_config.temperature,
                    seed=self.model_config.seed,
                    max_tokens=self.model_config.max_tokens,
                )
            except ModelError as exc:
                events.append(_event("model_error", error=str(exc)))
                if exc.recoverable and consecutive_protocol_errors < 2:
                    consecutive_protocol_errors += 1
                    cost_known = False
                    recovery_used = True
                    messages.append({"role": "user", "content": (
                        "The provider could not parse your previous tool response. "
                        "Call exactly one of the listed tools with valid JSON arguments. "
                        "Do not invent tool names or use a commentary tool."
                    )})
                    continue
                status, reason = "provider_error", str(exc)
                break
            consecutive_protocol_errors = 0
            usage = response.usage
            prompt_tokens += usage.prompt_tokens
            completion_tokens += usage.completion_tokens
            total_tokens += usage.total_tokens
            if usage.estimated_cost_usd is not None:
                observed_cost += usage.estimated_cost_usd
                if self.arm.cost_limit_usd is not None and observed_cost > self.arm.cost_limit_usd:
                    events.append(_event("budget_exhausted", cost_usd=observed_cost, limit_usd=self.arm.cost_limit_usd))
                    status, reason = "budget_exhausted", "observed model usage exceeded episode cost limit"
                    break
            else:
                cost_known = False
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
                has_diff = bool(runner.get_diff().content)
                if has_diff:
                    prompt_msg = "You must call a typed tool to proceed. Code changes are present: run run_tests to verify, review get_diff, and call submit_patch once verified."
                else:
                    prompt_msg = "You must call a typed tool to proceed. Use list_files, search, or read_file to locate and inspect the code, then apply your fix with edit_file. Do not call get_diff or submit_patch before editing."
                messages.append({
                    "role": "user",
                    "content": prompt_msg,
                })
                continue

            submitted = False
            user_feedback: list[str] = []
            for call in response.tool_calls:
                if call.name in {"apply_patch", "edit_file"} and not inspected:
                    result = ToolResult(
                        False,
                        "inspection required before editing; use list_files, search, or read_file first",
                        {"error": "inspection_required"},
                    )
                else:
                    result = runner.execute(call)
                events.append(_event("tool_result", turn=turns, tool_call_id=call.id, name=call.name, result={
                    "ok": result.ok, "content": result.content, "metadata": result.metadata,
                }))
                messages.append(_tool_message(call, result))

                if result.ok and call.name in {"list_files", "search", "read_file"}:
                    inspected = True

                if call.name == "apply_patch" and not result.ok:
                    user_feedback.append(
                        "The patch was rejected. Prefer using edit_file(path, old_text, new_text) for bounded, "
                        "reliable replacements instead of apply_patch. Do not repeat the same invalid patch."
                    )
                elif call.name == "edit_file" and not result.ok:
                    if "test files are outside the generation edit boundary" in result.content:
                        user_feedback.append(
                            "Editing test files is strictly forbidden. Tests specify expected behavior: "
                            "you must inspect and edit the package source code implementation (e.g. under django/ or sphinx/) "
                            "so that existing tests pass without modifying the test files."
                        )
                    elif "documentation" in result.content:
                        user_feedback.append(
                            "Editing documentation or markup files is forbidden. You must edit the Python "
                            "source code (*.py) in the library package that implements the behavior."
                        )
                    elif "0 occurrences" in result.content or "not found" in result.content:
                        target_p = call.arguments.get("path", "file")
                        user_feedback.append(
                            f"edit_file failed: old_text was not found in {target_p}. "
                            "Make sure you did NOT include line numbers (e.g. '123: ') in old_text or new_text. "
                            "Use read_file on that file to copy the EXACT raw lines of code including indentation."
                        )
                    elif "occurrences" in result.content:
                        user_feedback.append(
                            f"edit_file failed: {result.content}. Include more surrounding context lines in old_text "
                            "so that it matches uniquely."
                        )
                    elif "identical" in result.content:
                        user_feedback.append(
                            "edit_file failed: old_text and new_text are identical; no changes were made. "
                            "You must provide the original code in old_text and the MODIFIED replacement code in new_text. "
                            "Do not submit identical text for both arguments."
                        )
                    else:
                        user_feedback.append(
                            f"edit_file failed: {result.content}. Read the target file around the line you want to change, "
                            "and provide the exact matching code block."
                        )
                elif call.name == "submit_patch" and not result.ok:
                    user_feedback.append(
                        f"submit_patch failed: {result.content}. Run a relevant test command using run_tests "
                        "that passes with exit code 0 before submitting."
                    )
                elif call.name == "rollback":
                    user_feedback.append(
                        "You called rollback, which discarded all uncommitted changes. "
                        "Do NOT repeat the exact same edit that was just rolled back. "
                        "If the previous edit failed, diagnose why (check syntax, indexing [] vs call (), types, or imports) "
                        "and formulate a DIFFERENT, corrected fix using edit_file."
                    )

                if call.name == "run_tests":
                    if result.metadata.get("failure_class") == "build_failure":
                        if runner.checkpoints:
                            rollback = runner.rollback()
                            recovery_used = True
                            events.append(_event("automatic_rollback", reason="build_failure", result=rollback.content))
                            user_feedback.append(
                                "The last patch caused a syntax/import/build failure. The controller restored the latest checkpoint. Diagnose the observed failure and apply a corrected source-only change."
                            )
                    elif not result.ok:
                        user_feedback.append(
                            "Tests did not pass. Inspect the diagnostic and the relevant existing tests. "
                            "Keep the current source change while diagnosing ordinary failures. "
                            "If the runner or target is invalid, select a valid relevant target; "
                            "otherwise refine the implementation until the relevant tests pass."
                        )

                if call.name in {"search", "read_file", "list_files"}:
                    call_sig = hashlib.sha256((call.name + json.dumps(call.arguments, sort_keys=True)).encode()).hexdigest()
                    seen[call_sig] = seen.get(call_sig, 0) + 1
                    if call.name == "search":
                        query_text = str(call.arguments.get("query", "")).strip()
                        if query_text:
                            query_sig = f"q:{query_text}"
                            seen[query_sig] = seen.get(query_sig, 0) + 1
                            if seen[query_sig] >= 2 and not result.metadata.get("count"):
                                user_feedback.append(
                                    f"The search query '{query_text}' returned no matches across {seen[query_sig]} attempts. "
                                    "Stop searching for this phrase; it is not in the codebase. "
                                    "Instead, search for a single class/method name (e.g. 'Serializer', 'serialize', 'autodetector') "
                                    "or inspect files listed in list_files using read_file."
                                )
                    if seen[call_sig] >= 2:
                        if call.name == "search" and not result.metadata.get("count"):
                            user_feedback.append(
                                f"You already searched for '{call.arguments.get('query')}' with no matches. "
                                "Do not repeat the same unsuccessful query. Try a single invariant symbol, "
                                "check for placeholder words, search a broader directory (e.g. path='.'), or list files."
                            )
                        else:
                            user_feedback.append(
                                f"You already called {call.name} with these arguments. "
                                "You have inspected this code. Be decisive: formulate your fix and apply it now using edit_file(path, old_text, new_text). "
                                "You can verify your change immediately with run_tests."
                            )

                if call.name == "read_file" and result.ok:
                    read_signature = json.dumps(call.arguments, sort_keys=True) + runner.state_hash()
                    if read_signature == last_read_signature:
                        consecutive_file_reads += 1
                    else:
                        last_read_signature = read_signature
                        consecutive_file_reads = 1
                    if consecutive_file_reads >= 4:
                        user_feedback.append(
                            "The same file range has been read repeatedly without changes. "
                            "Read a different range or symbol, or apply a fix based on the current evidence."
                        )
                    if consecutive_file_reads >= 6:
                        status, reason = "loop_exhausted", "repeated read of the same range without progress"
                        break
                else:
                    last_read_signature = ""
                    consecutive_file_reads = 0

                if call.name == "run_tests" and result.ok:
                    user_feedback.append(
                        "The current patch passed this test command. Review get_diff and submit_patch "
                        "when the command covers the issue; rerun only after another edit or for additional coverage."
                    )

                if call.name in {"apply_patch", "edit_file", "run_tests", "rollback", "submit_patch"} and not result.ok:
                    state = runner.state_hash()
                    signature = hashlib.sha256((call.name + json.dumps(call.arguments, sort_keys=True) + state).encode()).hexdigest()
                    seen[signature] = seen.get(signature, 0) + 1
                    if seen[signature] == 2:
                        recovery_used = True
                        events.append(_event("loop_recovery", repeated_action=call.name, result="workspace preserved"))
                        user_feedback.append(
                            f"Repeated failed action: {call.name}. Your source changes are preserved. "
                            "Read the current code and diagnostic, then change the arguments or implementation."
                        )
                    elif seen[signature] >= 5:
                        status, reason = "loop_exhausted", f"repeated failed action: {call.name} with no progress"
                        break


                if call.name == "submit_patch" and result.ok:
                    submitted = True
                    break

            if user_feedback and not submitted:
                messages.append({
                    "role": "user",
                    "content": "\n\n".join(user_feedback),
                })

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
        model_requests = int(getattr(self.model, "logical_requests", logical_requests_before + turns)) - logical_requests_before
        model_attempts = int(
            getattr(self.model, "request_attempts", request_attempts_before + model_requests)
        ) - request_attempts_before
        return AgentResult(
            task.instance_id,
            status,
            reason,
            turns,
            model_requests,
            model_attempts,
            observed_cost if cost_known else None,
            prompt_tokens,
            completion_tokens,
            total_tokens,
            patch,
            patch_hash,
            events,
            runner.command_records(),
            recovery_used,
            True,
            runner.last_successful_test_command(),
        )
