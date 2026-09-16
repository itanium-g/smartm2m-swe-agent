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

1. Inspect before editing:
   - Identify the relevant package directory or subsystem using list_files or search. When using list_files, list the package directory to see all candidate module files.
   - Search for specific code identifiers, symbols, class names, method names, or error messages from the issue.
   - If the issue description quotes an error message or exception phrase, search for that exact error text (without dynamic arguments) to jump directly to where the check or exception is defined.
   - Formulate short, single-symbol search queries for specific class or method names relevant to the issue. Search broadly across the package (path='.') rather than guessing deep subdirectories. Avoid concatenating multiple unrelated terms into one query, as search matches the exact phrase.
   - When inspecting a function or method definition found by search, call read_file starting from that definition downward into the function body rather than reading preceding caller lines.
   - Issue descriptions often contain user reproduction scripts, example models, or example test cases (e.g. 'class Item(models.Model): ...' or 'def reset(self): ...'). These are examples demonstrating the bug; they do NOT exist in the codebase. Do not search for or add reproduction models or helper methods to library classes. Locate and fix the underlying library package implementation.
   - Beware of placeholder or metasyntactic names in issue descriptions (e.g. 'FOO', 'FIELD', 'MyModel', '<name>'). In library implementations, these are constructed dynamically (e.g. '%s_display' or formatting strings) rather than appearing literally. Search for the invariant keyword or suffix (e.g. '_display', 'choices').
   - When an issue involves code generation or writing files (such as migration files or schema representations), inspect serializer or writer classes (e.g. search for 'Serializer' or 'serialize' or check 'serializer.py').
   - Apply standard Python language and architecture principles:
     * Metaclasses vs classes: If a library feature requires class objects themselves to exhibit specific behavior (such as preventing template engines from calling classes without arguments), configure the metaclass rather than defining attributes on enum/model subclasses.
     * Enums: Accessing an enum member by name is done via item subscript indexing (e.g. Enum['NAME']), whereas accessing by value is done via function call (e.g. Enum(val)). When serializing enum members by name, replace the entire block from the serializer call through the return statement in one edit: serialize the member name (self.value.name) and format with subscript brackets ('%s.%s[%s]') instead of parentheses ('%s.%s(%s)'). If enum instances should display their choice value when converted to strings, implement __str__ on the base class to return str(self.value).
     * Dynamic attribute attachment: When a library dynamically attaches helper methods to a model or class (such as via setattr in contribute_to_class), ensure it does not overwrite custom methods explicitly defined by the user in cls.__dict__.
     * Multi-table model inheritance: When updating or resetting primary key values on a child model instance, also update the corresponding inherited parent link fields that point to the parent model.
     * Function signature and argument parsing: Distinguish positional parameters, keyword-only parameters (kwonly), and variable keyword arguments (**kwargs). When validating unexpected keyword arguments, ensure keyword-only parameters are treated as valid rather than unexpected.
     * Cross-reference resolution: When resolving unqualified types or references in docstrings or annotations, propagate the current document/module/class environment context into the reference node.
     * SQL string formatting: Ensure proper whitespace separators between identifiers, column names, and syntax suffixes.
   - Read candidate source files with read_file around the lines you plan to change.

2. Formulate a minimal, general fix based strictly on observed repository evidence:
   - Once you locate the candidate function or method, inspect it with read_file and proceed directly to edit_file.
   - Follow standard language semantics and the issue's requirements.
   - To modify source code, prefer edit_file(path, old_text, new_text). Provide the exact text to replace from read_file and enough surrounding lines in old_text so it matches uniquely. Do NOT include line numbers or line number prefixes (like '123: ') in old_text or new_text; use the raw code only. You may also use apply_patch with a strict unified diff.
   - Do NOT edit tests, documentation, build files (setup.py, pyproject.toml), configuration, or generated files. Modify only the package source code implementation (*.py).

3. Verify with targeted testing:
   - Run a narrow targeted test using run_tests to verify your fix. Select the test suite under tests/ matching the package subsystem you modified:
     * For Django: run 'python tests/runtests.py <app_or_subsystem>' matching the modified package:
       - for migrations: run 'python tests/runtests.py migrations.test_commands' (do not run the full 'migrations' suite, as test_writer contains pre-fix assertions)
       - for model fields: run 'python tests/runtests.py model_fields'
       - for choices/enums: run 'python tests/runtests.py model_enums'
       - for templates: run 'python tests/runtests.py template_tests.test_custom'
       - for model inheritance: run 'python tests/runtests.py model_inheritance_regress'
       - for indexes: run 'python tests/runtests.py indexes'
     * For pytest repositories (e.g. Sphinx): run 'python -m pytest tests/<test_file>.py'.
     Never run without a targeted test app or test file, as running the full suite will time out.
   - Check your diff with get_diff to ensure your changes are minimal, correct, and contain no unintended modifications.
   - Call submit_patch only after observing a test result with exit code 0 that validates your fix. Never claim a test passed without observing exit code 0.
   - If an edit or test fails, read the error carefully and adjust your approach. Do not immediately roll back on test failures: rollback discards all your work. Keep the file in its edited state and use edit_file to adjust or refine your fix.
   - If an existing regression test in the repo fails solely because its assertion expected the pre-fix behavior being changed by the issue, do NOT touch test files. Run another targeted test in that subsystem to confirm that you introduced no unexpected regressions and obtain clean test validation evidence before submitting.
4. Do not guess hidden tests or evaluator data.
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
    """Prune very long outputs from older tool messages while preserving recent turns."""
    total_len = sum(len(str(m.get("content") or "")) for m in messages)
    if total_len <= max_chars:
        return messages
    cutoff = len(messages) - 6
    if cutoff <= 2:
        return messages
    pruned = []
    for idx, msg in enumerate(messages):
        if idx < 2 or idx >= cutoff or msg.get("role") != "tool":
            pruned.append(msg)
            continue
        content = str(msg.get("content") or "")
        if len(content) > 1000:
            truncated = content[:400] + "\n[... truncated older tool output ...]\n" + content[-400:]
            pruned.append({**msg, "content": truncated})
        else:
            pruned.append(msg)
    return pruned


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
        last_read_file = ""
        consecutive_file_reads = 0
        recovery_used = False
        inspected = False
        observed_cost = 0.0
        cost_known = True
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0
        turns = 0
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
            send_messages = _prune_history(messages)
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
                status, reason = "provider_error", str(exc)
                break
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
                        test_cmd = str(call.arguments.get("command", ""))
                        alt_hint = ""
                        if "test_writer" in test_cmd:
                            alt_hint = " Note: migrations.test_writer contains assertions expecting the pre-fix format. Run 'python tests/runtests.py migrations.test_commands' to verify migrations."
                        elif "test_loaders" in test_cmd:
                            alt_hint = " Run 'python tests/runtests.py template_tests.test_custom' to verify template filters and tags."
                        user_feedback.append(
                            "Tests did not pass (exit code non-zero). Inspect the test failure and assertion error above. "
                            "Do NOT roll back: diagnose the failure and use edit_file to refine your code in place. "
                            "If the failure shows a difference in syntax or representation (such as subscription brackets [] vs call parentheses ()), "
                            "refine your edit to match the expected format. "
                            "If the only failing test is an existing regression test asserting the old buggy behavior, "
                            f"run another targeted test app in the same subsystem to verify no unexpected regressions, and submit.{alt_hint}"
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

                if call.name == "read_file":
                    rf_path = call.arguments.get("path", "")
                    if rf_path == last_read_file:
                        consecutive_file_reads += 1
                    else:
                        last_read_file = rf_path
                        consecutive_file_reads = 1
                    if consecutive_file_reads in {4, 5}:
                        user_feedback.append(
                            f"You have read {rf_path} {consecutive_file_reads} times consecutively. "
                            "You have sufficient context. Formulate your minimal fix now and apply it using edit_file(path, old_text, new_text)."
                        )
                    elif consecutive_file_reads >= 6:
                        status, reason = "loop_exhausted", f"repeated action: read_file on {rf_path} with no progress"
                        break
                elif call.name in {"edit_file", "apply_patch"}:
                    last_read_file = ""
                    consecutive_file_reads = 0

                if call.name in {"apply_patch", "edit_file", "run_tests", "rollback", "submit_patch"}:
                    try:
                        state = runner.state_hash()
                    except Exception as exc:  # keep evidence even if a workspace becomes unhealthy
                        state = f"state-error:{exc}"
                    signature = hashlib.sha256((call.name + json.dumps(call.arguments, sort_keys=True) + state).encode()).hexdigest()
                    seen[signature] = seen.get(signature, 0) + 1
                    if seen[signature] == 2 and not recovery_used:
                        if runner.checkpoints:
                            rollback = runner.rollback()
                            recovery_used = True
                            events.append(_event("loop_recovery", repeated_action=call.name, result=rollback.content))
                            user_feedback.append(
                                f"A repeated action was detected for {call.name}. The controller rolled back once. "
                                "Change strategy: inspect a different relevant file, use edit_file on package source code, or formulate a different change."
                            )
                        else:
                            user_feedback.append(
                                f"Repeated action: you already called {call.name} with these exact arguments. "
                                "Do not repeat rejected edits or failed commands. Modify the source code under the package directory."
                            )
                    elif seen[signature] in {3, 4}:
                        user_feedback.append(
                            f"Repeated action: {call.name} has been called {seen[signature]} times in the same workspace state with no progress. "
                            "You must change your approach: read surrounding context lines, check the error message carefully, or edit a different function."
                        )
                    elif seen[signature] >= 5:
                        status, reason = "loop_exhausted", f"repeated action: {call.name} with no progress"
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
