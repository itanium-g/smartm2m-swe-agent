# Execution isolation and contamination control

Updated: 2026-09-12. **Planned controls; none has yet been exercised by an implemented agent.** These controls support the PDF's evaluation rigor and recovery requirements.

## 1. Trust boundaries

| Component | Can access | Cannot access |
|---|---|---|
| Trusted supervisor | Frozen config, provider secret, Docker lifecycle, input projection, artifact collection | Must not execute generated repository code directly on the host. |
| Task sandbox | Issue text, base source, preinstalled dependencies, its own temporary reproduction/checkpoint state | Host files, Docker socket, API keys, result archives, other tasks, gold patches/tests, solution internet access. |
| Model provider | Sanitized issue/repository excerpts and tool observations sent by the supervisor | Direct host access or arbitrary built-in browsing/execution for this experiment. |
| Official evaluator | Sealed candidate patch and official evaluation material in a fresh container | Feeding hidden test results back into the primary agent run. |
| Reporter/reviewer | Sealed logs, official reports, hashes, costs, and post-run contamination evidence | Rewriting a primary patch or dropping failed tasks from its denominator. |

Issue text, repository content, tool output, and generated patches are untrusted data. Instructions found inside them cannot authorize network access, secret reads, budget changes, alternate endpoints, or removal of evaluation checks.

## 2. Sandbox design

Run generated shell and tests only in disposable task containers on the selected experiment host. Do not expose a public endpoint for arbitrary task execution. Apply equivalent sandbox settings to baseline and custom.

Planned restrictions:

- No privileged container, host networking, host PID namespace, Docker socket, host home directory, or credential mount.
- Block external network during generation; allow only repository-required local services/loopback. Pre-fetch approved dependencies during preparation and record image digests. Provider calls originate from the trusted supervisor, so the model can work while the task container has no internet.
- Fix CPU, memory, PID, command-time, output, and disk/resource policies after task preflight. A timeout must stop the command process group and lingering descendants; logging a timeout while leaving code running is insufficient.
- Retain only the repository history needed for base identification/diffs. Inspect prepared images for solution-bearing refs, cached gold data, and evaluator scripts; remove exposure through a common documented provisioning step without changing task code or tests. If this cannot be done compatibly, record the limitation.
- Persist complete command evidence through supervisor-owned capture. Never trust an agent-editable log file as the only proof of execution.

Some historical images may run as root inside the container or need specific capabilities. Verify and minimize requirements without breaking task parity. Docker is an operational boundary, not a guarantee against every container escape; a disposable VM can further separate the experiment from valuable host data. This is a single-user take-home design, not a hardened multi-tenant service.

No global cleanup commands on a shared host. Remove only task-owned containers/volumes after saving artifacts; preserve user resources and immutable image provenance.

## 3. Patch and validation integrity

Capture candidate changes before export, including added/deleted files. Reject escaping paths, unsafe symlink effects, unexpected binaries, and unrelated generated artifacts. Treat a security-rejected patch as a distinct failure and retain its original bytes for audit.

The custom agent submits source changes appropriate to the issue. Its helper/reproduction files and log output stay outside the submitted patch. It must not pass by deleting tests, suppressing collection, changing expected outputs, or bypassing checks. Keep the baseline's raw submission unchanged; common evaluation safety checks must not become custom repair or selective patch rewriting.

Reconstruct a candidate from the clean base and submitted patch, then execute chosen visible checks. Bind the result to the exact patch and commands. Validate in an environment whose logs the candidate cannot rewrite. The official harness later supplies its own evaluation tests in another fresh container. This prevents an agent's modified working tree or forged “passed” text from being the sole score evidence.

## 4. Preventing solution leakage

Before freeze, use synthetic or verified-disjoint development tasks for debugging and model selection. Do not search the employer's issue IDs for published fixes, inspect solution PRs, retrieve benchmark trajectories, or use gold patches for prompt examples. The planning research inspected framework/configuration documentation and dataset-card metadata; it did not intentionally retrieve task solutions.

Generation must not receive `patch`, `test_patch`, evaluator test lists, or benchmark hints from the dataset. Assert the request projection and filesystem mounts with synthetic canary values placed in forbidden fields. A raw dataset may exist in the trusted evaluator area; it must not be mounted into a task sandbox or copied into its transcript.

Do not grant model-provider built-in search, browsing, or hosted code tools. The experiment uses its own isolated repository tool. Preserve logs of any attempted boundary violation. Clearing conversation state between tasks also prevents solution transfer through earlier episodes.

If gold/solution exposure occurs, stop the affected generation, mark the exposure, and report it. Do not claim a fresh seed erases leaked knowledge. Keep affected tasks in the all-task reporting and explicitly separate compromised comparisons; do not substitute new tasks.

## 5. Post-run memorization review

Only after both arms' patches are sealed, review trajectories and, where needed, compare with the public gold patch in an evaluator-only context. Never use this comparison to revise primary predictions.

| Signal | Interpretation |
|---|---|
| Emits a highly specific near-exact solution before inspecting relevant code | Suspicious; record timing, reads/actions, patch similarity, and alternative explanations. |
| Names hidden test details or solution-specific facts absent from visible inputs | Stronger exposure/memory concern; investigate the actual input boundary. |
| Identical small obvious change after ordinary file inspection | Not sufficient evidence of memorization by itself. |
| Different patch with genuine reproduced failure and repair | Evidence of work, but does not prove absence of training contamination. |
| Known prompt/filesystem leak | Confirmed procedural contamination, distinct from uncertain model memorization. |

Record per task: signal, affected arm(s), relevant event timestamps, code inspected before patching, similarity method if used, confidence category, and a short rationale. Use categories such as no specific signal, suspected memorization, confirmed exposure, or inconclusive. Never call a model uncontaminated merely because the patch differs from gold.

Publish the complete fixed-set score first, then a supplementary breakdown for flagged tasks and unflagged tasks with explicit counts/denominators. Do not remove inconvenient losses under a contamination label. The purpose is to qualify what the measured lift supports, not to manufacture a cleaner-looking score.

## 6. Evidence publication

Redact API keys, authorization headers, credentials, and unrelated personal data. Keep all failures, costs, commands, patch bytes, and score-producing fields. Record what was redacted and hash the public bundle. Do not publish fabricated reasoning; retain only actual available API messages/actions and observed tests.

Repository visibility at planning time is private. Before final public submission, inspect the staged files and archives for secrets and unrelated materials. Original assignment PDF and full benchmark dataset need not be republished; preserve source attribution and any applicable upstream notices instead.
