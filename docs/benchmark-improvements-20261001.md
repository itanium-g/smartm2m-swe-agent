# Agent improvements and follow-up benchmarks — 2026-10-01

The follow-up implementation is frozen at commit `baa0662`. Both provider runs
use the existing eight-task manifest, dataset revisions, model configurations,
60-turn limits, and 120-second command timeouts. Neither primary results nor
previous Mistral results are overwritten.

## Changes under evaluation

- Repeated failed actions trigger corrective feedback without discarding edits.
  Repeating a successful test no longer causes rollback or loop termination.
- Automatic rollback requires a syntax diagnostic and broken syntax in an edited
  Python file. Test import errors alone no longer discard a valid patch.
- Reading different ranges of one file counts as progress. Source reads are
  bounded and return raw, copyable text with range and continuation metadata.
- Context pruning preserves valid JSON and complete assistant/tool exchanges,
  counts tool-call arguments, and applies a smaller budget for Groq.
- Groq returns unrecognized tool names for local rejection and feedback, using
  its documented `disable_tool_validation` option. Protocol errors receive at
  most two corrective turns; transport retries respect the configured limit.
- The system prompt uses a general repository workflow. Task-specific solution
  rules and instructions to bypass relevant failing tests have been removed.
- New run manifests include a source fingerprint and Git revision. Each run
  retains a snapshot of the Python controller source used for generation.

## Validation and run protocol

The implementation passed 60 unit tests, Ruff checks, compilation, and a fresh
synthetic end-to-end smoke run. Both providers passed live multi-turn tool-use
preflight. Docker 29.8.0 was available on x86_64 Linux. Installed upstream source
metadata matches the locked mini-swe-agent and SWE-bench commit pins.

Commands:

```bash
python3 -m smartm2m reproduce --config configs/experiment.mistral.yaml --run-id track3-mistral-improved-20261001T161703Z
python3 -m smartm2m reproduce --config configs/experiment.groq.yaml --run-id track3-groq-improved-20261001T161703Z
```

The configured protocol executes the stock reference and improved custom agent
on all eight instances, seals predictions, then invokes the official evaluator.
Groq stopped before completing this protocol, as recorded below. Failures remain
in the denominator. Predictions are not replaced with hand-written solutions.
No further controller changes are made while these runs are executing.

## Development exposure

The engineering review inspected previous generation tool failures on this same
frozen task set. It did not retrieve gold patches or hidden tests for prompts.
These are follow-up measurements after development exposure, not an independent
held-out estimate. The previous prompt already contained task-specific advice;
the new prompt removes those rules. Historical scores are retained separately.

## Results

Mistral has completed official evaluation: custom 0/8, reference 0/8. This is a regression from the prior final custom run (2/8). Three custom patches passed selected visible tests and clean replay but failed official regression tests; these are patch failures, not evaluator infrastructure failures. All 108 checksum entries and source snapshot hashes were verified. Groq completed all eight reference episodes with provider errors (one format error and seven rate-limit errors). Custom generation then encountered the account's 200,000-token daily quota. Its first custom episode ended after six rejected attempts. The run was stopped during the next episode and saved as `blocked_provider_quota`: one custom episode completed, one interrupted, six not attempted. Custom predictions were not fully sealed and official evaluation was not run. No Groq score is assigned. This is an operational limitation, not evidence that the model cannot solve the tasks.

## Provider API reference

Groq's documented local-validation option:
https://console.groq.com/docs/api-reference#chat-create

## Runtime cleanup

Completed reference episodes left some task containers alive. Those containers were removed only after a terminal trajectory was retained and the runner had moved to the next task. Active episode containers and source files were not changed.

## Post-run reporting safeguard

A separate fix added after benchmark execution rejects auditing a run whose
record is unfinished or provider blocked. This preserves Groq's incomplete
status instead of turning absent evaluation into a completed 0/8 summary.
The complete current suite passed all 62 tests, including the new regression
tests. Checksums now exclude disposable workspaces, dataset copies, and caches;
official evaluation logs are retained in Git despite the generic logs ignore.
The benchmark source snapshots still identify `baa0662`.

## Retained artifacts

| Provider | Custom resolved | Reference resolved | Status |
|---|---:|---:|---|
| Mistral | 0/8 | 0/8 | Official evaluation completed; regression from prior final custom 2/8 |
| Groq | — | — | Incomplete: daily provider quota exhausted |

The Mistral bundle has 108 verified checksum entries. The Groq partial bundle
has 48. Source snapshots were verified, configured credentials were absent
from retained files, and provider organization identifiers were redacted from
Groq artifacts with a retained redaction note. Earlier result bundles were not
modified. `results/benchmark-comparison-20261001.json` records the distinction
between a completed result and an unavailable score.
