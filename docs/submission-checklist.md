# Track 3 submission checklist

Updated: 2026-09-12. **Planning complete; implementation, experimental evidence, and employer submission remain pending.** An unchecked item is not a claimed result.

## Source and experiment freeze

- [x] Read the five-page supplied PDF and visually inspect pages 4-5.
- [x] Select Track 3 and map its requirements separately from other tracks.
- [x] Adapt the reference repository's planning structure.
- [ ] Obtain/confirm the complete fixed task list; record authority and exact count.
- [ ] Pin dataset revision, IDs, base commits, task/image digests, dependencies, prompts, and evaluator.
- [ ] Confirm development/evaluation disjointness and generation data projection.
- [ ] Verify one provider/model route, supported decoding/seed controls, pricing, quotas, and retry accounting.
- [ ] Freeze budgets, implementation, and protocol before primary inference.

## Functional and evaluation evidence

- [ ] Run unmodified mini-swe-agent with only documented configuration changes.
- [ ] Implement custom file identification, edits, executed visible tests, and remediation.
- [ ] Demonstrate exact-patch pre-submission validation in a clean base workspace.
- [ ] Demonstrate build rollback and repeated-state/loop recovery within budget.
- [ ] Keep gold solutions/test material and official scoring feedback out of generation.
- [ ] Generate and seal a prediction for every expected task in both arms, including explicit failures.
- [ ] Run the official evaluator with cache-safe unique run IDs and full test output.
- [ ] Publish per-task and overall percent resolved, paired gains/losses, percentage-point lift, and actual costs.
- [ ] Preserve setup/provider/parser/test failures and missing tasks in the all-task accounting.
- [ ] Review likely memorization/exposure and publish the rationale and supplementary breakdown.
- [ ] Describe failed approaches and avoid claiming a positive result unless measured.

## Reproduction and packaging

- [ ] Top-level README identifies actually completed tracks and the exact tested command.
- [ ] One clean-checkout command regenerates both arms' predictions, official evaluation, and reported numbers.
- [ ] Endpoint is configurable and all effective non-secret settings are recorded.
- [ ] Full redacted logs, diffs, official reports, usage, and integrity hashes are available for both arms.
- [ ] Offline audit regenerates the tables without an API key; distinguish it from fresh inference/test execution.
- [ ] Large evidence archives are durable, downloadable, and checksum-linked; not only expiring CI artifacts.
- [ ] DESIGN.md describes actual behavior, rationale, limitations, and next steps.
- [ ] Time/scope record contains real active hours, unattended elapsed time, and reductions.
- [ ] Resource citations and applicable upstream/license notices are complete.
- [ ] Public files/archives contain no credentials, unrelated private data, or unintended employer attachments.
- [ ] Repository is **public**, as required by the PDF, and accessible from a signed-out session at handoff.
- [ ] Record final source commit and evidence bundle hash; ensure README/report point to them.

## Handoff fields

| Field | Current state |
|---|---|
| Repository | [itanium-g/smartm2m-swe-agent](https://github.com/itanium-g/smartm2m-swe-agent); private at planning time. |
| Completed track(s) | None; Track 3 planned. |
| Exact working reproduction command | Not implemented; proposed interface in README. |
| Implementation/result commit | Not available. |
| Model/provider and episode budget used | Not selected/frozen by a live preflight. |
| Reference/custom percent resolved and lift | Not measured. |
| Result bundle / checksum | Not generated. |
| Actual time and cuts | Planning session recorded without invented hours; implementation pending. |
| Public web app / credentials | Web app not required; no shared provider key. |

Changing repository visibility, buying compute/API credits, running scored inference, and submitting to the employer are future actions, not work performed by this documentation revision. A private repository remains suitable for planning but does not yet meet the final public-submission requirement.
