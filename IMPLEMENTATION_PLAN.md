# SMARTM2M Track 3 implementation plan and completion record

Updated 2026-09-14. The planned executable slice is implemented; the scored
benchmark run remains gated on the employer's complete fixed task manifest and
the evaluation environment.

## Delivered

| Area | Implemented evidence |
|---|---|
| Custom agent | src/smartm2m/agent.py |
| Safe tool interface | src/smartm2m/tools.py |
| Provider transport | src/smartm2m/model.py |
| Reference integration | src/smartm2m/reference.py |
| Clean validation | src/smartm2m/validation.py |
| Official evaluator boundary | src/smartm2m/evaluator.py |
| Paired reporting/audit | src/smartm2m/reporting.py and experiment.py |
| Reproducibility | lock config, manifest hashes, run artifacts, checksums |
| End-to-end verification | smartm2m smoke; synthetic custom-only resolution |
| CI | compile, smoke, and unit-test workflow |

## Acceptance gates

- G00 manifest gate: implemented, intentionally fails the placeholder
  evaluation manifest until eight employer-confirmed IDs are supplied.
- G01 generation projection: implemented; forbidden evaluator fields are
  rejected and never placed in the custom prompt.
- G02 matched settings: model, seed, decoding, retry, and budget settings are
  represented in the lock and run manifest; live provider support still needs
  host preflight.
- G03 baseline integrity: implemented as a subprocess call to mini-extra
  swebench; the unmodified package must be installed at the declared version.
- G04 validation gate: implemented with actual trusted command output and
  clean-base patch replay.
- G05 recovery gate: implemented with pre-edit checkpoints, build rollback,
  and repeated-state recovery; covered by controller tests.
- G06 evaluation evidence: implemented as a post-sealing official evaluator
  boundary and parser/report input contract.
- G07 paired score: implemented with fixed denominator arithmetic and explicit
  missing/unresolved statuses.
- G08 packaging: implemented with top-level commands, artifacts, checksums,
  design, scope record, and CI.

## Deliberate non-goals

No Track 1 or Track 2 implementation, model training, web UI, database,
multi-agent planner, vector retrieval, second provider, or production service
was added. These would consume time without improving the required causal
comparison before the task manifest and primary evidence exist.

## Reproduction contract

After filling tasks/evaluation.json:

~~~bash
python -m pip install -e ".[dev]"
python -m pip install "mini-swe-agent==2.4.6" "swebench"
smartm2m preflight --config configs/experiment.lock.yaml
DEEPINFRA_API_KEY=... smartm2m reproduce --config configs/experiment.lock.yaml --run-id track3-primary
smartm2m audit --config configs/experiment.lock.yaml --run-dir results/track3-primary
~~~

The run must be performed only after the final protocol/configuration is
frozen. Do not substitute the PDF's three examples for the missing fixed list.
