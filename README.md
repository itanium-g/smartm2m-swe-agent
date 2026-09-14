# SMARTM2M SWE Agent

Implementation of Track 3 from the SMARTM2M AI Engineer take-home: a custom
software-engineering agent compared with the unmodified mini-swe-agent on the
same model, budget, task IDs, and evaluation harness.

## Current status

The executable harness and offline end-to-end smoke test are implemented. The
employer's complete fixed task manifest was not present in the supplied PDF:
the three printed IDs are examples, not an authorized eight-task list.
Therefore this repository does not claim a SWE-bench score or positive lift
yet. Replace tasks/evaluation.json with the exact confirmed manifest before
running a scored experiment.

## Quick start

~~~bash
python -m pip install -e ".[dev]"
smartm2m smoke
python -m pytest
~~~

The smoke command creates a disposable synthetic git repository, runs a
scripted custom controller, replays the patch on a clean base, and generates
paired report artifacts. It is plumbing evidence only, not benchmark
evidence.

## Reproduce the real comparison

1. Put the employer-confirmed task IDs, immutable base commits, repository
   sources, and trusted visible test commands in tasks/evaluation.json.
   Do not add patch, test_patch, FAIL_TO_PASS, PASS_TO_PASS, or hints_text to
   the generation manifest.
2. Install the pinned reference and evaluator in isolated environments:

   ~~~bash
   python -m pip install "mini-swe-agent==2.4.6"
   python -m pip install "swebench"
   ~~~

   The reference arm invokes mini-extra swebench and does not import or
   modify its agent code.
3. Run the preflight gate:

   ~~~bash
   smartm2m preflight --config configs/experiment.lock.yaml
   ~~~

4. Supply the API key only through the environment and run both arms:

   ~~~bash
   export DEEPINFRA_API_KEY="..."
   smartm2m reproduce --config configs/experiment.lock.yaml --run-id track3-primary
   ~~~

   The provider/model, decoding settings, seed, retry policy, task order,
   patches, trajectories, commands, validation, official evaluation output,
   usage, and checksums are written under results/track3-primary/.
5. Rebuild the tables without an API key:

   ~~~bash
   smartm2m audit --config configs/experiment.lock.yaml --run-dir results/track3-primary
   ~~~

   Re-evaluate one sealed prediction arm, if needed:

   ~~~bash
   smartm2m evaluate --config configs/experiment.lock.yaml \
     --run-dir results/track3-primary --arm custom
   ~~~

smartm2m reproduce is the one-command real-track entry point. It generates
both prediction files, calls the official evaluator separately for each sealed
arm, and rebuilds the conservative paired summary. Missing or unverified
instances count as unresolved.

## What the custom arm adds

- Bounded list_files, search, read_file, apply_patch, run_tests, get_diff,
  rollback, and submit_patch tools.
- A source-only edit boundary that rejects path traversal, tests, and common
  build/configuration files.
- Trusted test-command allowlisting; the model cannot invent a shell command.
- Checkpoint before every edit, automatic rollback on syntax/import/build
  failures, and one bounded repeated-state recovery.
- Exact patch capture and clean-base replay validation before a prediction is
  sealed.
- Full redacted trajectory/command artifacts and machine-readable statuses.

The baseline is deliberately less constrained: it is the stock mini-swe-agent
reference process with only model, endpoint, budget, runtime, and output
configuration overrides.

## Evaluation rules

The headline metric is official resolved rate:

~~~text
100 * verified_resolved_tasks / confirmed_task_count
~~~

A task is resolved only when every official FAIL_TO_PASS test passes and
every official PASS_TO_PASS test remains passing. The headline lift is custom
rate minus reference rate in percentage points. The report also shows
custom-only gains, reference-only losses, both-solved tasks, and neither-
verified tasks. The official evaluator never feeds results back into primary
generation.

## Repository map

| Path | Purpose |
|---|---|
| src/smartm2m/agent.py | Custom controller and recovery state machine |
| src/smartm2m/tools.py | Checked tools, checkpoints, command evidence |
| src/smartm2m/model.py | Dependency-free OpenAI-compatible transport |
| src/smartm2m/validation.py | Patch hashes and clean-base replay |
| src/smartm2m/reference.py | Unmodified mini-swe-agent integration |
| src/smartm2m/evaluator.py | Official SWE-bench subprocess boundary |
| src/smartm2m/reporting.py | Offline paired metrics and Markdown tables |
| src/smartm2m/experiment.py | Preflight, run lifecycle, artifacts, audit |
| src/smartm2m/smoke.py | No-key synthetic end-to-end verification |
| configs/experiment.lock.yaml | Pinned experiment contract |
| tasks/evaluation.json | Deliberately pending employer manifest |

## Limitations and scope cuts

No model training, web application, database, hosted service, vector store,
multi-agent planner, or alternate-provider benchmark was added. Docker task
provisioning and the official SWE-bench harness remain external prerequisites;
the repository records their exact commands and failures rather than silently
simulating a score. Hosted APIs may ignore a requested seed or change backend
weights; the run manifest records that limitation. No provider key, benchmark
gold patch, or hidden test data is committed.

See DESIGN.md, IMPLEMENTATION_PLAN.md, docs/evaluation-protocol.md, and
docs/security-and-contamination.md.
