# Track 3 evaluation protocol

Protocol proposal v1, 2026-09-12. **No experiment has run.** Freeze the completed protocol/configuration before primary inference. This document governs scored comparisons; synthetic/development work is labeled separately.

## 1. Task selection and manifest

The PDF requires a fixed set of approximately eight instances. Its three examples are not an authorized final list. Obtain the complete employer list or explicit selection clarification. Never fill gaps by choosing easy issues or available containers.

The future manifest must contain:

| Field | Requirement |
|---|---|
| Authority | Source/date of employer-supplied list or permitted selection procedure. |
| Dataset | Repository ID, immutable revision, split, downloaded-file hashes. |
| Instances | Exact ordered IDs, repository names, base commits, environment/image digests. |
| Expected count | Actual confirmed N; immutable across the two arms and all headline tables. |
| Development split | Disjoint ID list and hash; synthetic fixtures until disjointness can be established. |
| Protocol/code | Experiment schema/version, implementation SHA, reference SHA, evaluator SHA. |

Reject duplicates, unknown IDs, missing pins, mismatched base commits, and evaluation/development overlap before calling a model. Verified Mini is a possible pool, not an evaluator replacement. Do not assume its smaller storage claim applies to the employer's tasks or standard Docker images.

The generation input projection allows only the task identifier, issue/problem statement, base repository snapshot, and operational metadata needed by trusted infrastructure. Keep `patch`, `test_patch`, `FAIL_TO_PASS`, `PASS_TO_PASS`, and `hints_text` outside the agent context and task filesystem. The evaluator may use the official fields after generation is sealed. Hints are excluded from this protocol unless the employer specifies otherwise, in which case both arms must receive exactly the same input policy and the change must be disclosed.

## 2. Baseline integrity

Use mini-swe-agent v2.4.6, inspected commit `a83fcae82d2a08f0ee0c688f9d137b3566c097f8`. Record the shipped SWE-bench config blob `106decd160e72e5164e29d15d23da354c29c309d` and SHA-256 hashes of source/config files at runtime. A later compatible reference pin is permissible only before experiment freeze with an explicit reason.

Run its shipped agent, prompts, parser, and submission behavior without code modification. Allowed configuration overrides: model/endpoint, decoding, budget, Docker/runtime settings, and output paths. Record each override and why it is required. Do not add custom test gating, summarization, repair, task-specific advice, or patch filtering to its generation process.

The custom controller is a separate arm. Sharing the stock model transport/environment does not make reference source editable. Common sandbox provisioning and measurement apply symmetrically and must be documented. Preserve both the raw baseline submission and evaluator input; any required format conversion must be lossless, deterministic, and checked.

## 3. Matched model and budget

The following is the **proposed development starting profile**, not a measured optimal configuration:

| Control | Both arms |
|---|---|
| Provider/model | Same exact provider route, model identifier, service tier, and resolved metadata. First candidate: DeepInfra `openai/gpt-oss-120b`. |
| Attempts | One primary episode per task per arm. Repairs inside an episode are not extra attempts. |
| Seed | Requested model seed 42 if supported; Python/task scheduling seed 42; all other randomness sources recorded. |
| Decoding | Proposed temperature 0, reasoning effort medium, at most 8,192 total completion tokens/call, other parameters explicitly fixed or omitted identically. Verify provider support and actual wire request. |
| Model context | Same provider context limit. Preserve reference context behavior; custom evidence summaries are an experimental change. |
| Turn threshold | 60 model-call turns including format-error turns. Record physical HTTP requests/retries separately. |
| API cost threshold | $0.50 nominal per episode using frozen rates and all available billable usage. This is a between-call threshold, not a guaranteed hard maximum. |
| Wall time | 2,700 seconds from prepared task start through generation/finalization; shared external supervisor stops the process at the deadline. |
| Command timeout | 120 seconds; same environment setting in both arms. |
| Compute | Same host/image policy; one active episode; matched CPU/RAM/PID quotas fixed after preflight. |
| Official scoring | Separate common timeout, initially 1,800 seconds/instance, checked for sufficiency before freeze; no scoring feedback during generation. |

Keep the model snapshot immutable where the provider supports it. Otherwise log requested and returned model identifiers, provider/backend metadata, timestamp, and any available fingerprint; disclose that backend weights are not provably pinned. Run paired arms close in time and never switch routes between them. A 120B model on different providers is not treated as the same served model for the primary comparison.

Pin seeds wherever supported. Temperature zero is not deterministic execution. If the endpoint rejects/ignores seed, do not let parameter dropping silently hide it: prefer a compatible route before freeze, or explicitly disclose the unseeded hosted limitation. Keep all controllable local seeds fixed. Do not claim exact seed reproducibility if it was not available.

Use identical transport retry/backoff policy. Inspect upstream retry controls and record the resolved policy before running; disabling only SDK retries does not necessarily disable reference retries. Count malformed responses, retry charges, and repair/summarization calls. No free second model, planner, critic, or fallback is allowed. Uncertain billing stays visible rather than being entered as zero.

The reference checks its cost threshold between calls. A request or transport retry may take spend beyond the nominal threshold. Reserve headroom, set provider/account controls when available, and report actual spend and any overshoot. A hard-prepaid/broker budget would require separate implementation and validation; this plan does not claim one.

Tune proposed limits on synthetic/disjoint development tasks only. Freeze one final profile for both arms; avoid a budget that predictably prevents the reference from completing a normal development episode. Once scored execution begins, changing limits creates a separately labeled experiment, not an overwrite.

## 4. Run order and data boundaries

1. Validate the lock and prepare task images/dependencies without generating candidate patches. Cache immutable base layers only.
2. Freeze the custom implementation, prompts, thresholds, primary task list, and report rules.
3. Run the complete paired generation schedule, alternating which arm runs first by task index. Use fresh workspace/transcript state every time. Keep results out of subsequent prompts.
4. Seal both arms' prediction files and artifact hashes. A task may yield an empty prediction with a failure reason. Every expected ID still gets a record.
5. Evaluate both sealed prediction sets with the official pinned harness in new containers. Apply its official test patch and run the prescribed tests. Do not expose results to an agent for more primary-run repair.
6. Generate paired tables from official reports; then conduct contamination/failure review and write the design/result narrative.

Source/issue inspection by the developer for scored tasks can also leak answers. Use the predeclared data boundary, avoid browsing associated solution PRs, and record accidental exposure. All code/prompts must be frozen before seeing either arm's scored outputs for optimization. Post-hoc improvements belong to development or a new disclosed experiment.

## 5. Local validation versus official resolution

The custom agent runs tests available in the base repository and self-written issue reproductions before submission. The controller verifies actual command output, collection, exit status, and patch identity. It cannot see the official gold test patch or evaluator test-ID lists during generation.

After sealing, official success requires both:

- Every required FAIL_TO_PASS test passes.
- Every required PASS_TO_PASS test passes.

Use the pinned evaluator's resolved flag and test-level details. Do not infer resolution from `pytest` exit zero, a model assertion, a successful patch application, or a hand-written test alone. Patch application errors, missing test output, test timeouts, failed setup, or unparseable evaluator results are not successes.

A separate evaluator preflight may check the harness on synthetic fixtures/disjoint development instances. Never copy a gold solution into the scored generation workspace. If an infrastructure diagnosis later requires examining a scored gold patch, perform it only after sealing and record that exposure.

## 6. Status and denominator rules

Keep generation and evaluation statuses separate. Example generation reasons: submitted, verifier_rejected, budget_exhausted, loop_exhausted, provider_error, or sandbox_error. Example evaluation reasons: resolved, tests_failed, patch_apply_failed, test_timeout, parser_error, setup_error, or not_evaluated.

Let N be the complete confirmed task count. Let R_b and R_c be tasks officially verified resolved for baseline/custom:

```text
reference_percent_resolved = 100 * R_b / N
custom_percent_resolved    = 100 * R_c / N
lift_percentage_points    = 100 * (R_c - R_b) / N
```

Unverified, blocked, missing, and not-evaluated tasks contribute no verified resolution to this conservative all-task summary. Report their distinct counts prominently; do not label every infrastructure failure an agent bug. A secondary completed-pairs view may be useful, but must show its denominator and never replace the all-task table.

For the paired outcome table, report both-solved, custom-only gains, reference-only losses, and neither-verified counts. Also provide a separate table restricted to valid evaluated pairs if any tasks were blocked. At N=8, one net additional verified resolution changes the all-task score by 12.5 percentage points. This arithmetic is illustrative, not an observed result.

Do not report Track 1 pass@k as the Track 3 headline. If paired repetitions are added, keep the first predeclared attempt as primary and report all repetitions, paired seeds, extra cost, and a clearly defined mean. Do not quietly replace a failed first attempt with a later success. Eight tasks do not establish broad statistical superiority; gains and losses are more useful than overstated significance claims.

## 7. Failure and rerun policy

| Event | Treatment |
|---|---|
| Image/preparation failure before inference | Record task blocked; repair environment without changing task IDs. Retain incident evidence. |
| Rejected API request with no generation | Retry only under the fixed shared transport policy; record request IDs and time. |
| Ambiguous timeout/billing after a request | Preserve it; charge observed/uncertain usage explicitly. No invisible reset or success-only retry selection. |
| Agent error, looping, invalid patch, or failed tests | Primary episode failure. No replacement attempt in headline results. |
| Evaluator infrastructure failure | Re-evaluate the identical sealed patch after infrastructure repair; preserve all attempts and new evaluation run IDs. No new inference. |
| Genuine flaky tests | Predeclare any diagnostic rerun rule; publish every result, first-run status, and flakiness. Do not cherry-pick a pass. |
| Controller/model/protocol changes after freeze | Separate experiment identity and full disclosure; do not overwrite the primary run. |

Official harness caching can reuse a result by run ID and instance ID even when a patch changes. Use unique run IDs for distinct arms, configurations, attempts, and re-evaluations. Include a digest of manifest, code/config, and prediction bytes plus an invocation identifier; preserve rather than overwrite prior logs. [Official caching guidance](https://github.com/SWE-bench/SWE-bench/tree/02e7a74ffd0b707aab73d203fe87bdc7c76afc8e)

## 8. Evidence contract

Each future result bundle contains:

| Artifact | Contents |
|---|---|
| `manifest.json` | Run ID, code/protocol hashes, expected task/arm records, environment, pins, seed support, timestamps. |
| `configs/` | Effective reference/custom configurations, prompt hashes, allowed override diff, price snapshot. |
| `reference/predictions.jsonl`, `custom/predictions.jsonl` | One standard SWE-bench prediction per expected ID: `instance_id`, `model_name_or_path`, `model_patch`. |
| `<arm>/<instance>/trajectory.json` | Actual prompts, returned model messages/tool calls, observations, and terminal status, with secrets redacted. |
| `<arm>/<instance>/commands.jsonl`, `logs/` | Full commands, outputs, exit/signal/timeout, tests collected, durations, and observation truncation metadata. |
| `<arm>/<instance>/candidate.patch`, `attempted/` | Exact submitted diff, including empty diff where applicable; failed/intermediate candidates retained separately. |
| `<arm>/<instance>/validation.json` | Base/image/patch/check hashes, pre/post visible checks, final clean replay, and limitations. Baseline entries may be N/A for custom-only checks. |
| `evaluation/<arm>/` | Original official reports and full test/build output; exact command and harness revision. |
| `usage.jsonl`, `summary.json`, `summary.md` | All available token categories, cost basis, retries, paired metrics, failure counts, and complete per-task table. |
| `contamination.md`, `checksums.sha256` | Exposure assessment and public artifact integrity. |

Do not request or fabricate inaccessible private reasoning. Preserve whatever the selected external API actually returns and is appropriate to publish, plus commands, actions, and tests. Redact credentials/authorization headers while retaining the technical evidence and a redaction manifest. Redaction must not erase failures or change score-producing fields.

For large logs, use a durable downloadable release archive with checksum and retain the report/index in Git. Expiring CI artifacts alone are insufficient. Neither provider keys nor the original assignment PDF are necessary in the public result bundle.

## 9. Reproduction and audit acceptance

The planned `reproduce` command must validate pins, generate both arms, score with the official harness, and regenerate every published number. A fresh invocation gets new artifact/run IDs and records its real costs. Resume may reuse an episode only when the full input/config/code identity matches and the operation is explicitly recorded.

The planned `evaluate` command reruns official tests on existing sealed patches without model calls. The planned `audit` command validates hashes/schema/completeness and recomputes tables from saved official reports without API keys or Docker. Auditing reports is not independent test execution and must be described accordingly.

Acceptance: clean-checkout invocation works; all expected records exist; hashes bind tests to patches; all-task denominators remain fixed; one regression fails resolution; stale cached reports are rejected; and the published numbers can be independently recomputed. Positive lift is a measured objective, not a prerequisite for honest reporting.
