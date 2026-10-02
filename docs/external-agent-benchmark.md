# Exploratory Codex CLI vs Antigravity CLI Benchmark

## 1. Purpose and Rationale

The primary SMARTM2M Track 3 experiment is a controlled comparison of the unmodified `mini-swe-agent` reference against the SMARTM2M custom reliability controller on the same model, seed, frozen SWE-bench tasks, and attempt budgets.

This **Exploratory External Coding-Agent Benchmark** is an additive, cleanly separated evaluation subsystem designed to answer:

> "How do OpenAI Codex CLI and Google Antigravity CLI (`agy`) perform as complete, modern coding-agent harnesses on the exact same eight frozen SWE-bench tasks under identical process, workspace, task, time, and evaluation protocols?"

### Critical Separation from Primary Track 3
- **Not a Same-Model Experiment:** Codex CLI uses OpenAI models (`gpt-6.1-sol`), while Antigravity CLI uses Google Gemini models (`gemini-3.8-flash-high`).
- **Complete Harnesses:** Each CLI incorporates its own proprietary system prompts, context management routines, tool sets, model routing, reasoning configuration, and subprocess/file editing mechanics.
- **Strict Independence:** This benchmark does not alter, replace, or recalculate historical Track 3 results (`results/track3-primary/`, `results/track3-mistral-codestral-final/`). Historical evidence remains immutable.

---

## 2. Architecture & Design Principles

```
                    Frozen Tasks (8 SWE-bench Verified)
                                   |
         +-------------------------+-------------------------+
         |                                                   |
         v                                                   v
     Codex CLI                                           AGY CLI
   (`codex exec`)                                    (`agy --print`)
         |                                                   |
  Fresh Workspace 1..8                                Fresh Workspace 1..8
(Clean Base + Test Helper)                         (Clean Base + Test Helper)
         |                                                   |
         +-------------------------+-------------------------+
                                   |
                       Working Tree `git diff`
                                   |
                                   v
                         Sealed Predictions
                       (`predictions.jsonl`)
                                   |
                                   v
                     Official SWE-Bench Evaluator
                     (commit `02e7a74ffd0b...`)
                                   |
                                   v
                    Paired Comparison & Checksums
```

### Key Design Decisions

1. **Native Headless Execution (No ACP for V1):**
   The benchmark directly spawns native CLI processes (`codex exec` and `agy -p`) rather than relying on Agent Client Protocol (ACP). This eliminates translation layers, reduces third-party dependencies, minimizes the failure surface, and simplifies version pinning. A generic Python abstraction (`ExternalAgent`) enables adding an ACP backend in the future.
2. **One Process Per Task:**
   Neither CLI is run as a persistent, multi-task daemon or continuous conversation. Every single task attempt spawns a brand-new subprocess. No chat history, conversation ID, or context leaks across tasks.
3. **Workspace Isolation:**
   Each task attempt materializes a disposable clone or clean copy pinned to the exact task `base_commit`. The controller verifies:
   - `git rev-parse HEAD` exactly matches `task.base_commit`.
   - `git status --porcelain` is clean prior to agent launch.
   Never run agents from the benchmark repository checkout.
4. **Patch Authority:**
   Model prose and declarations ("I fixed the bug", "All tests pass") are never trusted. The benchmark controller extracts:
   ```bash
   git diff --binary <base_commit>
   ```
   directly from the working tree. Untracked files are staged with `git add -N .` so new files are included, while temporary test artifacts (`__pycache__`, `*.pyc`, `.benchmark/`) are strictly excluded. If no diff exists, `model_patch = ""` is honestly recorded.
5. **Container-Backed Test Helper (`./.benchmark/test`):**
   Task repositories depend on historical Python and package environments. Rather than assuming the host OS has every environment, the harness injects an executable `./.benchmark/test` helper script into the task workspace.
   - When Docker is available, `./.benchmark/test <command>` mounts the workspace into the official SWE-bench x86_64 container image (`/testbed`) and executes repository-native tests.
   - The `.benchmark/` directory is registered in `.git/info/exclude` so it never affects `git status` or leaks into predictions.
   - Evaluator-only fields (`FAIL_TO_PASS`, `PASS_TO_PASS`, gold patch) are strictly withheld from the helper.
6. **Strict Development Session Non-Contamination:**
   The development session of Antigravity CLI building this harness is not a measured benchmark episode. The harness strips all session and development variables (`ANTIGRAVITY_*`, `AGY_*`, `CONVERSATION_*`, etc.) before launching measured child processes.

---

## 3. Matched Benchmark Protocol

| Parameter | Codex CLI Arm | Antigravity CLI Arm |
|---|---|---|
| **Binary** | `codex` (`codex-cli 0.159.3`) | `agy` (`1.2.14`) |
| **Model** | `gpt-6.1-sol` | `gemini-3.8-flash-high` |
| **Effort / Reasoning** | Configured via `-c model_reasoning_effort=...` | High (`--effort high`) |
| **Invocation** | `codex exec --ephemeral --json -m <model> -C <ws> <prompt>` | `agy -p <prompt> --output-format stream-json --model <model> --dangerously-skip-permissions --disable-slash-commands` |
| **Sandbox Policy** | `workspace-write` (or `danger-full-access` for Docker) | Native host sandbox / skip-permissions |
| **Attempts / Task** | 1 | 1 |
| **Wall Limit** | 2,700 seconds (45 min) per task | 2,700 seconds (45 min) per task |
| **Execution** | Sequential (Task 1 to 8) | Sequential (Task 1 to 8) |
| **Denominator** | 8 frozen SWE-bench Verified tasks | 8 frozen SWE-bench Verified tasks |
| **Evaluator** | Official SWE-bench commit `02e7a74` | Official SWE-bench commit `02e7a74` |

---

## 4. Common Benchmark Prompt

Both agents receive the exact same version-controlled prompt template rendered from `src/smartm2m/external_agents/prompts.py`:

```text
You are solving a SWE-bench software engineering issue.

The repository is already checked out at the required base commit.

Issue:

{{problem_statement}}

Fix the issue in the repository.

Requirements:

- Inspect the existing implementation before modifying it.
- Make the smallest correct general source-code change.
- Do not modify tests merely to make them pass.
- Do not modify benchmark or evaluation infrastructure.
- Run relevant repository tests when useful.
- You can run tests using ./.benchmark/test <optional test command> (for example `./.benchmark/test` to run default tests or `./.benchmark/test <command>` to run a targeted test in the task container).
- Do not search the internet for the original issue, solution, pull request, patch, SWE-bench answer, or hidden evaluator information.
- Leave the final implementation in the working tree.
- Do not create a Git commit.
- The benchmark controller will extract `git diff` and grade it using the official SWE-bench evaluator.
```

The SHA-256 digest of the rendered prompt is stored in every task's `metadata.json`.

---

## 5. Result Bundle Hierarchy

Each run creates an isolated directory under `results/cli-comparison-<run-id>/`:

```
results/cli-comparison-<run-id>/
  manifest.json          # Run metadata, host summary, task projections, version hashes
  config.yaml            # Frozen configuration snapshot
  prompt.txt             # Rendered prompt template
  codex/
    metadata.json        # Aggregate codex arm metadata & task statuses
    predictions.jsonl    # Sealed predictions (instance_id, model, model_patch)
    summary.json         # High-level statistics
    summary.md           # Human-readable summary table
    tasks/
      <instance_id>/
        metadata.json    # Complete ExternalTaskResult model
        events.jsonl     # Filtered structured event lines
        stdout.log       # Full raw stdout stream (secrets redacted)
        stderr.log       # Full raw stderr stream (secrets redacted)
        commands.jsonl   # Extracted shell commands, return codes, and output
        patch.diff       # Extracted working tree diff
  agy/
    metadata.json
    predictions.jsonl
    summary.json
    summary.md
    tasks/
      <instance_id>/
        metadata.json
        events.jsonl
        stdout.log
        stderr.log
        commands.jsonl
        patch.diff
  evaluation/
    codex/               # Official SWE-bench evaluation run logs & report
    agy/                 # Official SWE-bench evaluation run logs & report
  comparison.json        # Paired outcome matrix & per-task resolution
  comparison.md          # Markdown paired comparison report
  checksums.sha256       # SHA-256 digests of all retained files
```

---

## 6. Run State Machine & Incomplete Run Safety

### Terminal States
- `generated`: Process completed; working tree diff was extracted (patch may be empty or non-empty).
- `generation_failed`: CLI process returned a non-zero exit code.
- `timed_out`: Subprocess exceeded `wall_time_seconds`.
- `provider_blocked`: Quota exhaustion, rate limiting, authentication failure, or provider outage detected.

### Incomplete Run Protection
If a run is interrupted by quota, network outage, or process termination:
- The run is marked `provider_blocked` or `incomplete`.
- Unattempted tasks remain pending.
- **No headline "0/8" score is calculated.** The report explicitly indicates that the benchmark was incomplete.
- Running with `--resume` skips all already completed attempts and attempts only pending tasks.

---

## 7. Exact CLI Commands

### Dry-Run Preflight
Validates manifest, 8 task base commits, Docker availability, container images, and CLI versions without invoking any models:
```bash
smartm2m external-benchmark --dry-run --config configs/external-agents.yaml
```

### Synthetic Integration Smoke Test
Runs a live end-to-end smoke iteration on a disposable synthetic repository (no benchmark tasks consumed):
```bash
# Smoke test both Codex and AGY
smartm2m external-benchmark --smoke --agent all

# Smoke test Codex only
smartm2m external-benchmark --smoke --agent codex

# Smoke test AGY only
smartm2m external-benchmark --smoke --agent agy
```

### Full Benchmark Execution
```bash
# Run both arms sequentially (Codex then AGY) and evaluate
smartm2m external-benchmark --agent all --config configs/external-agents.yaml --run-id cli-comparison-v1

# Run Codex arm only
smartm2m external-benchmark --agent codex --config configs/external-agents.yaml --run-id cli-comparison-v1

# Run AGY arm only
smartm2m external-benchmark --agent agy --config configs/external-agents.yaml --run-id cli-comparison-v1
```

### Resuming an Interrupted Run
```bash
smartm2m external-benchmark --resume --config configs/external-agents.yaml --run-id cli-comparison-v1
```

### Re-Evaluating Saved Predictions
```bash
smartm2m external-benchmark --evaluate-only --config configs/external-agents.yaml --run-id cli-comparison-v1
```
