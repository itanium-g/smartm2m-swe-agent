# SMARTM2M Track 3 implementation and audit record

Updated 2026-09-14. The repository now contains the submission-ready
implementation and a frozen eight-task protocol. The real headline benchmark
remains unrun because this Work environment lacks Docker and a provider key;
that is an explicit infrastructure state, not a fabricated score.

## Acceptance status

| Gate | Status | Evidence |
|---|---|---|
| Track 3 only | PASS | `README.md`, lock protocol, no Track 1/2 code |
| Eight IDs frozen | PASS | `tasks/evaluation.json`, selection fingerprint |
| Deterministic Mini selection | PASS | `scripts/select_verified_mini.py`, seed 42, 50-ID pool |
| Safe manifest hydration | PASS | `scripts/hydrate_manifest.py`, hidden-field rejection/tests |
| Same model/meaningful budget | PASS | locked model/endpoint/temperature/seed/tokens/60 steps |
| Stock reference boundary | PASS | pinned `mini-extra` subprocess, no vendored edits |
| Custom recovery/validation | PASS | typed tools, checkpoints, rollback, loop detection, clean replay |
| Official evaluator boundary | PASS | pinned SWE-bench subprocess and conservative parser |
| Real paired score/lift | BLOCKED | Docker unavailable in this environment |
| Evidence bundle | PARTIAL | synthetic smoke and infrastructure-probe evidence are retained; primary bundle awaits run |
| Public repository | PASS | GitHub visibility verified public at `itanium-g/smartm2m-swe-agent` |

## Reproduction contract

```bash
python -m pip install -e ".[dev]"
python -m pip install -r requirements-evaluation.txt
export GROQ_API_KEY="..."
smartm2m reproduce --config configs/experiment.lock.yaml --run-id track3-primary
```

The command must be run on a compatible x86_64 Linux/Docker host when the
current environment cannot provide the official images. It does not replace
the frozen IDs or change the denominator after a failure.

## Scope cuts

Track 3 only; one model/provider; one stock reference; eight fixed tasks;
pass@1; no UI, training, database, vector store, alternate provider,
multi-agent architecture, or Tracks 1/2.
