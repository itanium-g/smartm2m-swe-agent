"""Common, version-controlled benchmark prompt template for external agents."""

from __future__ import annotations

import hashlib

COMMON_PROMPT_TEMPLATE = """You are solving a SWE-bench software engineering issue.

The repository is already checked out at the required base commit.

Issue:

{problem_statement}

Fix the issue in the repository.

Requirements:

- Inspect the existing implementation before modifying it.
- Make the smallest correct general source-code change.
- Do not modify tests merely to make them pass.
- Do not modify benchmark or evaluation infrastructure.
- Run relevant repository tests when useful.{test_helper_instruction}
- Do not search the internet for the original issue, solution, pull request, patch, SWE-bench answer, or hidden evaluator information.
- Leave the final implementation in the working tree.
- Do not create a Git commit.
- The benchmark controller will extract `git diff` and grade it using the official SWE-bench evaluator."""

DEFAULT_TEST_HELPER_INSTRUCTION = (
    "\n- You can run tests using ./.benchmark/test <optional test command> "
    "(for example `./.benchmark/test` to run default tests or `./.benchmark/test <command>` "
    "to run a targeted test in the task container)."
)


def render_prompt(
    problem_statement: str,
    *,
    include_test_helper: bool = True,
    custom_helper_instruction: str | None = None,
) -> str:
    """Render the standard SWE-bench problem statement into the benchmark prompt template."""
    helper = (
        custom_helper_instruction
        if custom_helper_instruction is not None
        else (DEFAULT_TEST_HELPER_INSTRUCTION if include_test_helper else "")
    )
    return COMMON_PROMPT_TEMPLATE.format(
        problem_statement=problem_statement.strip(),
        test_helper_instruction=helper,
    )


def hash_prompt(prompt: str) -> str:
    """Return the SHA-256 hex digest of the exact rendered prompt."""
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()
