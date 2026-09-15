# SMARTM2M Track 3 — SMARTM2M SWE Agent

This is a Track 3 submission: a custom SWE agent compared with the unmodified
mini-swe-agent reference on the same model, endpoint, seed, task set, and
primary attempt budget. Tracks 1 and 2 are intentionally out of scope.

## Status at this checkout

Repository visibility is public at `itanium-g/smartm2m-swe-agent` (verified
2026-09-14). The implementation and frozen protocol are complete. No real
SWE-bench score or lift is claimed yet: this Work environment has no Docker
daemon, so a valid eight-task primary run could not
be completed.
The synthetic `smartm2m smoke` result is plumbing evidence only.

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
Track 3 protocol:

```bash
export GROQ_API_KEY="..."
smartm2m reproduce --config configs/experiment.lock.yaml --run-id track3-primary
```

That command validates the frozen manifest, runs stock mini-swe-agent and the
custom arm once per task, seals predictions, invokes the pinned official
SWE-bench evaluator for both arms, computes the fixed-denominator report, and
writes the evidence bundle under `results/track3-primary/`. Use
`smartm2m audit --config configs/experiment.lock.yaml --run-dir results/track3-primary`
to rebuild the report without a key.

During reproduction the exact dataset revision is materialized locally twice:
first as a safe four-column generation dataset for both agents, then as the
full evaluator dataset only after both prediction files are sealed. This keeps
the stock reference CLI compatible with the pinned revision without passing
gold fields to either generation prompt.

The lock uses `openai/gpt-oss-120b` through Groq's
`https://api.groq.com/openai/v1` OpenAI-compatible endpoint, temperature `0`,
requested seed `42`, 8,192 completion tokens per call, 60 custom turns / 60
reference steps, one primary attempt, and a 2,700-second arm wall limit.
Provider pricing is configured at \$0.15 / \$0.60 per million input/output tokens;
parity is enforced by the matched turn/token caps and observed token usage/cost
is recorded separately.

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

In this audit environment the real pinned evaluator was invoked with a valid
empty-patch prediction and stopped before producing an official report because
the Docker socket is unavailable. That attempt is evidence of an environment
block, not a benchmark score.

See [DESIGN.md](DESIGN.md), [docs/evaluation-protocol.md](docs/evaluation-protocol.md),
and [docs/security-and-contamination.md](docs/security-and-contamination.md).
