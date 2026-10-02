# SMARTM2M Track 3 — SMARTM2M SWE Agent

This is a Track 3 submission: a custom SWE agent compared with the unmodified
mini-swe-agent reference on the same model, endpoint, seed, task set, and
primary attempt budget. Tracks 1 and 2 are intentionally out of scope.

## Status at this checkout

The 2026-10-01 follow-up adds safer recovery, bounded source reads and context,
and retained controller source snapshots. It passed 60 unit tests, lint,
compilation, and an offline end-to-end smoke run. Its Mistral run resolved
**0/8 custom and 0/8 reference**, a regression from the previous final custom
result of 2/8. The new Groq run encountered provider request errors and then
exhausted its 200,000-token daily quota during custom generation. It is saved as
an incomplete quota-blocked attempt with no completed score. Auditing unfinished
runs is now rejected. See
[the follow-up record](docs/benchmark-improvements-20261001.md) for results and
limitations; historical results below are preserved.

Repository visibility is public at `itanium-g/smartm2m-swe-agent` (verified
2026-09-14). The implementation, dual-provider abstraction (Groq and Mistral),
frozen protocol, unit test suite (62/62 passing), and benchmark reproduction runs
are complete:

- **Strict Primary Run Preservation:** `results/track3-primary/` remains strictly preserved and read-only.
- **Mistral Codestral Benchmark Reproduction (`track3-mistral-codestral-v2`):**
  - Custom Agent: **4/8 resolved (50.0%)**
  - Reference Arm (`mini-swe-agent`): **0/8 resolved (0.0%)**
  - Lift: **+50.0 percentage points**
- **Clean End-to-End Reproduction (`track3-mistral-codestral-final`):**
  - Custom Agent: **2/8 resolved (25.0%)**
  - Reference Arm (`mini-swe-agent`): **0/8 resolved (0.0%)**
  - Lift: **+25.0 percentage points**
- **Harness Verifications:** All 8 frozen benchmark tasks have been verified to resolve 100% in the official SWE-bench evaluation harness under candidate solutions.

## Frozen evaluation set

The assignment explicitly permits the 50-instance SWE-bench Verified Mini pool.
This repository uses the immutable Hugging Face revision
`b316c349947c29963fce3f4a65967c9807a4b673` of
`MariusHobbhahn/swe-bench-verified-mini` (`test` split). The committed pool is
`tasks/verified_mini_pool.txt`; its sorted-ID SHA-256 is
`ee9f2273637b18488018603dfa222f6cca73e6f62ede44b2ef6cf9245ccc471f`.

The eight IDs were selected before benchmarking with `random.Random(42).sample`
from the lexicographically sorted 50-ID pool. The ordered frozen sample and
fingerprint are recorded in `tasks/evaluation.selection.json` and
`tasks/evaluation.json`:

| Order | Instance |
|---:|---|
| 1 | `sphinx-doc__sphinx-8551` |
| 2 | `django__django-11999` |
| 3 | `django__django-11815` |
| 4 | `django__django-12304` |
| 5 | `django__django-12273` |
| 6 | `django__django-12262` |
| 7 | `django__django-12039` |
| 8 | `django__django-11964` |

The selected-ID SHA-256 is
`395f2adfaf4b9b2c5a129b7de83fe886d4f3b281fb9588d5802e2dfcaa717dfb`.
The PDF’s three printed IDs are treated as illustrative examples, not as a
mandatory manifest. These eight remain the denominator even if an arm or task
is blocked; substitution after freezing is prohibited.

`scripts/select_verified_mini.py` rechecks the complete pool and selection.
`scripts/hydrate_manifest.py` downloads the pinned dataset and writes only
generation-safe fields. Neither script copies gold patches, test patches,
hints, FAIL_TO_PASS, or PASS_TO_PASS into the agent manifest.

## Reproduce the paired experiment

Install the project and pinned external source commits:

```bash
python -m pip install -e ".[dev]"
python -m pip install -r requirements-evaluation.txt
```

Set the provider secret outside the repository (or in `.env`), then run the one-command
Track 3 protocol for your selected provider:

### Mistral Reproduction (codestral-2508)
```bash
export MISTRAL_API_KEY="..."
smartm2m reproduce --config configs/experiment.mistral.yaml --run-id track3-mistral-codestral-final
```

### Groq Reproduction (gpt-oss-120b)
```bash
export GROQ_API_KEY="..."
smartm2m reproduce --config configs/experiment.groq.yaml --run-id track3-primary
```

That command validates the frozen manifest, runs stock mini-swe-agent and the
custom arm once per task, seals predictions, invokes the pinned official
SWE-bench evaluator for both arms, computes the fixed-denominator report, and
writes the evidence bundle under `results/<run-id>/`. Use
`smartm2m audit --run-dir results/track3-mistral-codestral-final` to rebuild
the report without an API key. Audit uses the task set saved in that run and
refreshes its checksums.

During reproduction the exact task dataset revision is materialized locally
twice: first as a safe four-column generation dataset for both agents, then as
the full evaluator dataset only after both prediction files are sealed. The
locked evaluator metadata dataset revision supplies image and grading fields
when the task dataset does not contain them. Task IDs, repositories, and base
commits are checked before the metadata is joined. Neither source passes gold
fields to either generation prompt.

The repository includes matched configurations for both providers:
- **Mistral:** `codestral-2508` via `https://api.mistral.ai/v1`, temperature `0.0`, seed `42`, 2,048 max tokens, 60 turns/steps, \$0.30 / \$0.90 per million input/output tokens.
- **Groq:** `openai/gpt-oss-120b` via `https://api.groq.com/openai/v1`, temperature `0.0`, seed `42`, 8,192 max tokens, 60 turns/steps, \$0.15 / \$0.60 per million input/output tokens.
Parity is strictly enforced by matched turn/token caps, and observed token usage and cost are recorded separately in `usage.jsonl`.

## What was built

The custom intervention is operational rather than a second model: inspect
first, bounded source-only patches, observed repository test output, patch
identity, pre-edit checkpoints, automatic build-break rollback, one bounded
loop recovery, and clean-base replay before sealing a prediction. `run_tests`
accepts declared commands or bounded targeted repository test runners, rejects
shell composition/destructive commands, records stdout/stderr, return codes,
timeouts, and the task container image, and runs in the official x86_64 image
when Docker is available.

The reference is a subprocess call to stock mini-swe-agent 2.4.6 at source
commit `a83fcae82d2a08f0ee0c688f9d137b3566c097f8`; its prompts, parser, loop,
tools, and source are not modified. The official evaluator is pinned to SWE-
bench commit `02e7a74ffd0b707aab73d203fe87bdc7c76afc8e` and is the only
authority for resolved status.

## Results and evidence

When a real run exists, `summary.md` contains all eight rows with reference and
custom status, patch SHA-256, notes, paired outcomes, percentages, and lift:

```text
reference % = resolved_reference / 8 * 100
custom %    = resolved_custom / 8 * 100
lift        = custom % - reference %
```

Reference trajectories/logs, custom trajectories, command history, patches,
clean validation, official evaluator output, usage, contamination worksheet,
and `checksums.sha256` are retained in the run directory. Missing or
unparseable evaluator records count as unresolved. No benchmark result is
presented in this repository until those artifacts exist.

## Layout and limitations

- `src/smartm2m/` — controller, safe tools, model transport, reference/evaluator boundaries, validation, reporting.
- `tasks/` — frozen safe manifest, deterministic selection record, and 50-ID pool.
- `configs/` — locked model, endpoint, versions, seed, evaluator, and limits.
- `scripts/` — exact-revision pool selection and safe manifest hydration.
- `docs/` — protocol, provenance, contamination policy, acceptance checklist, and scope record.
- `MANUAL_ACTIONS.md` — only environment/submission actions that cannot be completed here.

The custom arm does not silently fall back to a host environment when a task
image is declared: without Docker it records an infrastructure failure. Hosted
providers may ignore a requested seed or vary backend weights; that limitation
is recorded rather than described as determinism. No UI, database, vector
store, multi-agent planner, model training, alternate provider, or Track 1/2
implementation was added.

An earlier infrastructure audit was blocked by an unavailable Docker socket.
Docker was available for the 2026-10-01 follow-up, and both Mistral arms completed
official evaluation. Provider quota failures in the Groq follow-up remain
explicit rather than being treated as evidence about patch quality.

## Exploratory Codex CLI vs Antigravity CLI Benchmark

In addition to the primary Track 3 custom vs reference evaluation, this repository includes an exploratory external coding-agent benchmark comparing:
1. **OpenAI Codex CLI** (`codex-cli 0.159.3`, model `gpt-6.1-sol`)
2. **Google Antigravity CLI** (`agy 1.2.14`, model `gemini-3.8-flash-high`)

on the **exact same frozen eight SWE-bench Verified tasks** (`tasks/evaluation.selection.json`).

### Why this benchmark exists and why it is separate
The primary Track 3 experiment measures the lift of a reliability controller around the *same model* under *matched budgets*. In contrast, this exploratory benchmark asks:
> *"How do modern autonomous coding-agent CLIs perform as complete systems on fixed SWE-bench tasks under identical process, workspace, time, and evaluation protocols?"*

This is **not** a same-model comparison. Each agent brings its own proprietary system prompts, context management routines, tool definitions, reasoning configuration, and execution loops. It does not replace or modify historical Track 3 runs.

### Architectural Highlights
- **Native Headless Execution (No ACP for V1):** Directly invokes `codex exec` and `agy -p` subprocesses without translation layers.
- **One Process Per Task:** Every task runs in a fresh, isolated subprocess with no conversation persistence across tasks.
- **Strict Workspace Isolation:** Disposable clones checked out at exact task base commits with empty git status verified before launch.
- **Patch Authority:** Predictions are extracted directly via `git diff --binary <base_commit>` from the working tree. Model prose is never trusted.
- **Container Test Helper (`./.benchmark/test`):** Injected helper allows both agents to run targeted tests in the official SWE-bench x86_64 task container without exposing evaluation gold labels. Excluded via `.git/info/exclude`.
- **Incomplete Run Safety:** Quota/auth blockers report `provider_blocked` or `incomplete` without calculating headline 0/8 scores. `--resume` continues pending tasks.

### Benchmark Commands
```bash
# 1. Dry run validation (verifies manifest, docker, and CLI versions)
smartm2m external-benchmark --dry-run --config configs/external-agents.yaml

# 2. Integration smoke test on a synthetic repository (no benchmark tasks consumed)
smartm2m external-benchmark --smoke --agent all

# 3. Benchmark Codex CLI arm (8 frozen tasks)
smartm2m external-benchmark --agent codex --config configs/external-agents.yaml --run-id cli-comparison-v1

# 4. Benchmark Antigravity CLI arm (8 frozen tasks)
smartm2m external-benchmark --agent agy --config configs/external-agents.yaml --run-id cli-comparison-v1

# 5. Benchmark both arms sequentially and run official SWE-bench evaluation
smartm2m external-benchmark --agent all --config configs/external-agents.yaml --run-id cli-comparison-v1

# 6. Resume an interrupted benchmark run
smartm2m external-benchmark --resume --config configs/external-agents.yaml --run-id cli-comparison-v1
```

See [docs/external-agent-benchmark.md](docs/external-agent-benchmark.md) for full protocol, freeze manifest, and limitations.

See [DESIGN.md](DESIGN.md), [docs/evaluation-protocol.md](docs/evaluation-protocol.md),
and [docs/security-and-contamination.md](docs/security-and-contamination.md).
