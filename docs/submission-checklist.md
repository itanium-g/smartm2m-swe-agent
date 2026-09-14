# Track 3 submission checklist

## Implemented

- [x] Top-level README with exact install, smoke, reproduce, evaluate, and audit commands.
- [x] Separate custom controller and unmodified mini-swe-agent subprocess boundary.
- [x] Typed source-only search/read/edit/test/rollback/submit tools.
- [x] Actual command output, return code, timeout, and duration capture.
- [x] Pre-edit checkpoints and bounded build/loop recovery.
- [x] Patch hash and clean-base replay validation.
- [x] Standard prediction JSONL generation for both arms.
- [x] Official evaluator subprocess integration with unique run IDs.
- [x] Conservative paired rate/lift arithmetic and offline audit.
- [x] Full per-task artifact layout, redaction path, and checksum generation.
- [x] Offline synthetic end-to-end smoke and CI workflow.
- [x] Design, protocol, contamination, source, and scope documentation.

## Required before claiming a benchmark result

- [ ] Obtain the employer-authorized fixed task IDs and expected count.
- [ ] Fill immutable base commits, repository sources, visible commands, image
  digests, and dataset revision in tasks/evaluation.json and the lock.
- [ ] Install and verify mini-swe-agent v2.4.6 and the pinned evaluator.
- [ ] Verify model metadata, seed support, provider pricing, retry behavior,
  and budget controls on the selected host.
- [ ] Freeze code, prompts, task list, model settings, and evaluator before
  generation.
- [ ] Run both arms on every fixed task and preserve empty/failing records.
- [ ] Evaluate sealed predictions using the official harness.
- [ ] Review contamination/memorization and publish the rationale.
- [ ] Add actual time, unattended elapsed time, costs, scope cuts, final
  commit, and evidence-bundle hash.
- [ ] Make the repository and durable evidence archive public if required by
  the employer.

No benchmark rate or positive lift is claimed until those unchecked items
exist as evidence.
