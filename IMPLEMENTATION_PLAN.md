# SMARTM2M Track 3 implementation plan

Updated: 2026-09-12 UTC. **Planning only: no implementation or evaluation has been performed.**

Build a focused SWE-agent experiment within the PDF's approximately one-week expectation. The deliverable is a credible comparison and reproducible evidence, supported by a small working agent. [Requirements](docs/requirements.md) owns source interpretation; [evaluation protocol](docs/evaluation-protocol.md) owns experimental rules; [setup/comparison](SETUP_AND_COMPARISON.md) owns provider research and budget arithmetic.

## 1. Decisions and scope

| Decision | Proposed baseline | Reason and tradeoff |
|---|---|---|
| Track | Track 3 only | Concentrate on one rigorous result. |
| Reference | mini-swe-agent v2.4.6, source SHA `a83fcae82d2a08f0ee0c688f9d137b3566c097f8` | Named reference; source and shipped SWE-bench configuration inspected. No reference logic/prompt edits. |
| Evaluator | Official SWE-bench harness, inspected SHA `02e7a74ffd0b707aab73d203fe87bdc7c76afc8e` | Score using the benchmark's test semantics. Validate this pin's compatibility before freezing. |
| Host stack | Python 3.12 line, uv lockfile, Pydantic, pytest, Ruff | Small CLI using the reference ecosystem; resolve exact compatible patches at implementation. |
| Controller | Sequential state machine; reuse stock transport/environment interfaces | Explicit recovery and test gating without a distributed agent framework. |
| Model | First candidate: DeepInfra `openai/gpt-oss-120b` | Low quoted cost for a tool-capable model; actual compatibility and bug-fix quality unmeasured. |
| Execution | One x86_64 Linux Docker host; one active task sandbox | Low operational complexity; disk/image preparation may dominate. |
| Artifacts | JSON/JSONL, unified diffs, full text logs, generated Markdown | Easy inspection and audit; no database or dashboard. |
| Headline experiment | One fixed task set, two arms, one primary attempt each | Paired percent resolved and percentage-point lift; no best-of-many selection. |

Version SHAs above are inspected candidates, not a tested dependency lock. An incompatible pin may change during development with a recorded reason; freeze the final pins before either scored arm runs. Never present a branch name, mutable tag, or model alias alone as proof of immutable execution.

| Priority | Work |
|---|---|
| P0 | Confirm tasks; reproduce reference; custom search/edit/test loop; executed pre-submission validation; rollback and loop recovery; official scoring; paired report; complete evidence; exact reproduction command; design and time record. |
| P1 | One development ablation; paired repeats if affordable; richer failure categorization; resume hardening. |
| P2 | Larger benchmark, multiple providers, semantic retrieval, alternate search strategies, hosted interface, stronger isolation platform. |

Do not add model training, security/PII tracks, vector databases, queues, Kubernetes, accounts, a web service, or public task execution to the submission baseline. No external deployment URL is required.

## 2. Source and task gate G00

The entire PDF was read, with pages 4-5 also visually inspected. It names approximately eight tasks but only three example IDs. The exact manifest remains missing. Preserve this distinction in the README and results schema.

Before any scored inference:

1. Obtain the employer's fixed IDs, or explicit clarification authorizing a selection procedure. Do not select by estimated solvability, available images, or observed scores.
2. Verify all IDs against a pinned SWE-bench Verified dataset revision; record split, base commits, ordered list, and manifest SHA-256. Mini membership is informational unless the employer requires that exact pool.
3. Keep the original expected task count as the denominator. Record every missing/unrunnable task explicitly. Do not quietly shrink the set.
4. Establish disjoint development tasks before tuning. While the real list is unavailable, use synthetic bugs for development to avoid accidental overlap.
5. Prepare the task/evaluator data boundary and confirm that no gold solution or evaluator-only fields reach generation.

No runnable task manifest is created by this plan. The three examples must not become a default scored selection.

## 3. Build sequence and effort

Active-hour allocations assume an engineer comfortable with Python/Linux and access to suitable compute. Waiting for task clarification, API access, image builds, and unattended execution is tracked separately. Day labels describe a one-week allocation, not a supplied deadline.

| Phase | Work | Active hours | Exit evidence |
|---|---|---:|---|
| P00 / day 1 | Task clarification, scope freeze, environment/image preflight | 4 | Approved manifest or explicit open status; host feasibility. |
| P01 / day 2 | Pinned dependencies, reference invocation, lifecycle and artifacts | 5 | Stock reference solves/attempts a synthetic or disjoint smoke task; transcript and diff saved. |
| P02 / day 3 | Custom search/edit loop and checkpoints | 5 | Deterministic tool contracts and an end-to-end synthetic patch. |
| P03 / day 4 | Visible-test selection, exact-patch clean replay, official evaluator integration | 6 | Test-gating and scoring failure cases distinguish true pass from invalid execution. |
| P04 / day 5 | Loop/build recovery, leakage checks, development-only tuning | 4 | Repeat-state and broken-build recovery evidence; frozen controller/config. |
| P05 / day 6 | Run the paired experiment, seal artifacts, score and report | 5 | All fixed IDs accounted for in both arms; machine-readable evidence. |
| P06 / day 7 | Clean-checkout reproduction/audit, design/time record, release preparation | 5 | Verified commands, complete artifacts, and honest submission status. |
| **Core total** | **P00-P06** | **34** | **Focused implementation and evidence.** |
| Contingency | Historical dependencies, compatibility, or packaging failures | **6** | Record actual extra effort and reductions. |
| **Planning envelope** | **Core plus contingency** | **40** | **Estimate, not time already spent.** |

Freeze features after day 5. Remove P1/P2 first. Never save time by modifying the reference, leaking official tests, dropping tasks, fabricating results, or omitting the second arm. If unresolved requirements prevent the scored run, deliver a transparent partial status rather than a successful-looking placeholder table.

## 4. Planned files and interfaces

The following paths are future implementation, not files already created by this revision:

| Path | Responsibility |
|---|---|
| `pyproject.toml`, `uv.lock`, `.python-version` | Package, exact dependency graph, host interpreter pin. |
| `src/smartm2m/cli.py` | `preflight`, `reproduce`, `evaluate`, `audit`, and deliberate resume interfaces. |
| `src/smartm2m/experiment.py` | Manifest validation, paired scheduling, lifecycle, accounting, and phase separation. |
| `src/smartm2m/reference.py` | Invoke stock reference through supported interfaces; no patched reference class. |
| `src/smartm2m/agent.py` | Custom state transitions, budget awareness, testing gate, and bounded recovery. |
| `src/smartm2m/tools.py` | Checked filesystem/edit helpers and command-result schemas. |
| `src/smartm2m/validation.py` | Test selection, log parsing, exact-patch replay, and validation hash. |
| `src/smartm2m/reporting.py` | Official-report normalization, failure accounting, paired metrics, and integrity checks. |
| `configs/experiment.lock.yaml` | Concrete model, tasks, seeds, pins, budgets, image digests, and protocol version. |
| `configs/reference.yaml`, `configs/custom.yaml` | Effective arm settings and declared differences. |
| `tasks/evaluation.json`, `tasks/development.json` | Frozen, non-overlapping manifests; no gold solution content. |
| `tests/fixtures/`, `tests/` | Small synthetic repositories and meaningful controller/evaluator regression checks. |
| `results/<run-id>/` | Auditable published evidence; never mount into an agent container. |

No executable scaffold, lockfile, fake model result, placeholder benchmark data, CI workflow, or runtime configuration is part of this documentation commit.

## 5. Shared infrastructure and baseline integrity

Install the reference from its exact commit in an isolated environment. Preserve the upstream license and record provenance if code is later vendored. Archive the shipped `src/minisweagent/config/benchmarks/swebench.yaml`, its blob hash, and the effective overrides.

Allowed baseline changes are configuration of model/endpoint, decoding, limits, execution environment, and artifact paths. Do not rewrite its system/instance prompts, action parser, file-search policy, transcript, recovery behavior, or submission strategy. Keep its observation and format-error templates intact. The reference already recommends reproduction and tests; the proposed gain comes from enforced control flow and measured recovery.

Use the same stock model transport for both arms initially. Check native tool calls, full output accounting, retry behavior, provider timeouts, and model-cost registration. Never enable `cost_tracking=ignore_errors` to conceal a missing tariff. Ensure required parameters are actually sent: the upstream example's `drop_params` setting can otherwise hide unsupported decoding controls. Supported configuration changes must be documented; source changes to the reference are not allowed.

Prepare dependencies/images outside generation. Every episode receives the same base snapshot and environment policy. No generated code executes on the host. The supervisor owns Docker and the API key; task containers receive neither. Common sandbox setup may remove unrelated Git refs/caches that expose solutions, but must not alter source semantics, installed dependencies, or test behavior. Record the transformation and apply it identically to both arms.

## 6. Custom agent contract

### State and tool behavior

State contains the current patch hash, files inspected, visible checks, checkpoint hashes, prior failure signatures, remaining budget, and terminal status. Keep one task's state out of every other task. Summaries are controller-owned evidence summaries; do not introduce a second model or uncounted summarization calls.

| State | Action and transition |
|---|---|
| Inspect | Read issue and base-repository context; search literal symbols and nearby tests. |
| Reproduce | Run a bounded reproduction/visible check and record pre-edit behavior. If no reliable reproduction exists, label the limitation. |
| Edit | Save checkpoint; make a bounded source change; invalidate stale validation. |
| Validate | Run syntax/import checks relevant to changed files, then selected visible tests and reproduction. |
| Recover | Restore checkpoint on introduced breakage or repeated-state loop; choose one new hypothesis within budget. |
| Finalize | Export exact source diff; apply it to clean base; rerun selected checks; seal accepted patch or record failure. |

Start with one common `bash` model tool and controller helpers to keep transport comparable. Search/read/edit/test helpers may be called through this interface; richer native schemas are P1. Bound helper paths, bytes, replacement matches, execution time, and returned output. Full logs are saved outside the sandbox even when the model sees a bounded excerpt.

| Helper | Planned checks |
|---|---|
| Search/read | Canonical repository-relative paths; reject traversal and escaping symlinks; bounded matches/line ranges. |
| Replace/apply diff | Require expected old content or old file hash; check applicability; atomic edit; explicit new-file handling. |
| Run command | Isolated sandbox only; record argv/command, cwd, timeout, exit/signal, elapsed time, stdout/stderr, and workspace hash. |
| Checkpoint/restore | Record tracked edits and created files; restore the full candidate state, not just a partial diff. |
| Export patch | Deterministically include intended added/deleted/modified source files; exclude scratch reproductions, logs, secrets, and generated binaries. |

The bash tool is intentionally capable of changing its sandbox. Helper validation is not a security boundary against arbitrary shell; isolation, independent patch inspection, and clean replay are the actual boundaries. Never execute a model-supplied shell string outside that sandbox.

### Validation and recovery

Choose tests from issue text and files visible at the base commit. Do not hard-code a universal `pytest` command: repositories may use their own runners, historical interpreters, or activation scripts. The authoritative task image retains its historical environment; the Python 3.12 host pin does not upgrade it.

Before editing, capture available selected-test results. A new selected-test failure is a visible regression; a pre-existing failure must remain distinguishable. If a valid reproduction was recorded failing, require it to pass after the fix. Test timeout, skipped-only output, zero collected tests, parser failure, or exit-zero output without a real check cannot earn a passing gate.

Checkpoint before each edit. Provisional loop rules: identical normalized command/output/workspace signature three times without progress, or an A-B-A oscillation between patch hashes, triggers recovery. Restore the latest checkpoint that satisfied the checks known at that time; fall back to base if none did. Permit at most two recovery events within the original episode. Clearing context or rolling back never resets model cost, elapsed time, calls, or attempt count.

Before final submission, apply only the exact exported patch in a clean workspace with the same image digest. Recreate the visible reproduction/checks separately, execute them, and bind validation to `(base_commit, image_digest, patch_hash, check_set_hash)`. Any patch/check change requires new validation. Keep the original outputs; model-written summaries do not replace them.

If no eligible patch passes the custom gate, submit an empty prediction with a structured reason and preserve attempted diffs separately. Do not force a claimed success. The baseline's submitted patch must remain unchanged; never run custom repair or gate-driven patch selection on it. Both arms still receive the same official scoring procedure.

## 7. Evaluation and artifacts

Follow [docs/evaluation-protocol.md](docs/evaluation-protocol.md) exactly. The pipeline is: preflight/freeze -> generate both arms -> seal -> official scoring in fresh containers -> metrics -> contamination review -> report. Official output cannot feed a primary-run retry.

The proposed common episode profile is one attempt, seed 42 where supported, 60 model-call turns, a $0.50 nominal API cost threshold, 45 minutes of wall time, and a 120-second per-command timeout. All are project proposals, subject to development-only feasibility checks. Finalization/visible tests use the custom arm's original time budget. Official evaluation gets a separate equal allocation for both arms. The reference cost threshold is checked between calls and can overshoot; the setup guide explains this limit rather than calling it a hard cap.

Every expected task/arm gets an artifact record even if it never produces a patch. Preserve raw submission, attempted diffs, terminal reason, effective configuration, usage, timestamps, test output, evaluator status, contamination review, and hashes. Keep a supplemental list of infrastructure incidents; the headline denominator never silently changes.

## 8. Acceptance gates

| Gate | Required evidence | Current state |
|---|---|---|
| G00 Source/tasks | PDF interpreted; complete fixed task list confirmed and pinned. | Source review complete; task list open. |
| G01 Environment | Each fixed task can be prepared or is explicitly diagnosed; architecture and data isolation verified. | Pending. |
| G02 Model/config | Supported tool calls/settings, endpoint, seed policy, prices, retries, and full experiment lock. | Pending. |
| G03 Reference | Exact reference SHA/prompts and allowed override diff; clean baseline invocation. | Pending. |
| G04 Agent/verifier | Search/edit/test behavior; clean exact-patch gate; no false pass on empty/failed test execution. | Pending. |
| G05 Recovery/isolation | Broken build, repeated action, rollback-created-file case, budget exhaustion, and forbidden-data canaries. | Pending. |
| G06 Evaluation | Official harness path; FAIL_TO_PASS/PASS_TO_PASS evidence; invalid patch/parser failures handled; unique cache-safe run IDs. | Pending. |
| G07 Comparison | All tasks and both arms, paired counts/lift, actual budget usage, failed approaches, contamination assessment. | Pending. |
| G08 Handoff | Verified reproduction/audit, evidence integrity, actual time, updated short design/README, public repository at submission. | Pending. |

Meaningful tests should exercise remaining risks: false green from no tests, stale validation after an edit, regression despite a fixed reproduction, partial rollback leaving a created file, cost lost on a malformed tool call, omitted task changing the denominator, and cached evaluator output reused for a different patch. Do not spend the timebox on large suites that merely mirror helper implementations.

## 9. Release and completion

Record the generated-code commit independently of the planning commit, exact command, model route, dataset manifest hash, and result-bundle hash. Run from a clean checkout and verify that saved artifacts regenerate the published tables without a key. Fresh inference with a hosted model may differ; distinguish reproducibility of procedure/evidence from identical stochastic outputs.

Update the README and design to describe only completed behavior. Record active work and unattended run time separately. Complete the [submission checklist](docs/submission-checklist.md), including the PDF's public-repository requirement. Original assignment files are cataloged, not silently relicensed or republished.

**Implementation done** means a working agent and auditable comparison under the agreed protocol. **Objective achieved** additionally requires measured positive lift. A sound partial or negative result must be described honestly. This revision completes the planning package only.
