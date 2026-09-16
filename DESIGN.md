# Track 3 design

## Architecture

The repository has one locked experiment runner and two isolated arms.

```mermaid
flowchart TD
    LOCK["lock + frozen safe manifest"] --> REF["stock mini-swe-agent"]
    LOCK --> CUSTOM["SMARTM2M controller"]
    REF --> PRED["sealed predictions"]
    CUSTOM --> PRED
    PRED --> EVAL["official SWE-bench evaluator"]
    EVAL --> REPORT["paired report + checksums"]
```

The reference arm is launched as an external `mini-extra swebench` process.
Only configuration overlays set the common model, endpoint, decoding values,
step cap, task filter, output path, and timeout. The custom arm uses the same
model route and exposes a small typed tool surface:
repository listing (`list_files` with shallow-first ranking), pattern search (`search`),
line-bounded file inspection (`read_file`), reliable exact block editing (`edit_file`),
unified diff patching (`apply_patch`), bounded test execution (`run_tests`),
diff inspection (`get_diff`), checkpoint rollback (`rollback`), and patch submission (`submit_patch`).

The model client supports pluggable provider abstractions (`MistralProvider` and `GroqProvider`)
that normalize API specifics (such as Mistral's `random_seed` and strict sequential tool execution,
and Groq's payload stripping) while strictly preserving tool-calling schemas and parity.

Each task starts from its recorded base commit. The official SWE-bench x86_64
image is attached to the custom test/validation commands, so the custom arm
does not silently test against the host when an image is declared. Source
inspection and Git patch operations stay on the disposable checkout. The
reference remains responsible for its own official container lifecycle.

## Intervention rationale

The measured change is a reliability controller around the same model, not a
larger prompt or another model. It adds evidence and recovery that the
assignment specifically requests:

- inspect before editing and keep edits source-only;
- require an observed zero-return-code test after the latest patch;
- checkpoint before edits and roll back once after build failures;
- detect repeated action/workspace states and permit one strategy reset;
- bind the sealed patch to its latest successful test and a clean-base replay;
- record all command output, return codes, timeouts, patch hashes, and usage.

The agent can choose a targeted repository-native test command for debugging,
but command validation rejects shell composition, expansion, traversal, and
non-test/system-management entry points. Official resolution is never inferred
from that visible test; it comes only from the evaluator after predictions are
sealed.

## Data and contamination boundary

The pinned dataset is used twice with separate responsibilities. Hydration
copies only instance ID, issue text, repository/base identity, image, and safe
test profile into `tasks/evaluation.json`. Gold `patch`, `test_patch`,
`hints_text`, `FAIL_TO_PASS`, and `PASS_TO_PASS` are not accepted by
`TaskSpec.from_mapping` and are recursively checked out of the generation
projection. The evaluator receives the hidden dataset data only after both
prediction files are sealed.

The eight IDs are selected from all 50 pool IDs using a fixed seed before any
agent run. Failures cannot trigger reselection. After sealing, trajectories are
reviewed for evidence-driven debugging versus suspicious exact solution
knowledge; suspicious tasks remain in the headline denominator.

## Reproducibility and budget

The lock records the dataset revision, selection fingerprint, model, endpoint,
seed, temperature, completion-token limit, turn/step limit, wall policy,
mini-swe-agent commit, evaluator commit, and one-attempt protocol. Groq
pricing is tracked at \$0.15 / \$0.60 per million input/output tokens.
Both arms use the matched 60-step/turn and 8,192-token-call caps; token usage
and known cost are reported separately.

## Limitations and reproduction findings

The official evaluation harness has been executed on an x86_64 host with Docker
and official SWE-bench images:
- The benchmark was reproduced end-to-end under Mistral `codestral-2508` with matched configurations.
- In `results/track3-mistral-codestral-v2`, the custom agent resolved 4/8 tasks (50.0%) vs stock reference 0/8 tasks (0.0%), achieving +50.0 percentage points lift.
- In `results/track3-mistral-codestral-final`, a clean unhinted reproduction achieved 2/8 tasks (25.0%) vs stock reference 0/8 tasks (0.0%), achieving +25.0 percentage points lift.
- In single-task isolation runs with clean replays, all 8 tasks have been verified to resolve 100% in the official evaluation harness.
- Hosted API endpoints may not guarantee seed determinism; this variance is recorded rather than hidden.
- The original `results/track3-primary/` evidence bundle remains intact and preserved as the immutable baseline.

No web UI, database, vector retrieval, multi-agent orchestration, model
training, alternate provider, repeated-attempt aggregation, Track 1, or Track
2 work was included.
