# Assignment requirements and evidence

Source: the supplied five-page PDF, cataloged in [assignment/README.md](assignment/README.md). Page 1 establishes the purpose/timebox, page 4 specifies Track 3, and page 5 contains contamination, scoring, and submission requirements. **All functional evidence below is pending.**

## Required outcomes

| ID | Source requirement | Planned implementation or evidence | Gate |
|---|---|---|---|
| R01 | Select at least one track; approximately one week (p.1). | Track 3 only; focused 34-40 active-hour allocation plus separately recorded compute/wait time. | G00, G08 |
| R02 | Improve bug-fix success over the same model under a reference agent (pp.1,4). | Paired official results and percentage-point lift; do not promise positive lift before measurement. | G07 |
| R03 | Any model/API, with model pinned (p.4). | One provider/model identity, resolved metadata, decoding parameters, endpoint, SDK/dependency pins. | G02 |
| R04 | Approximately eight fixed SWE-bench Verified IDs; no additions/substitutions (p.4). | Employer-confirmed manifest, dataset revision, base commits, and invariant task denominator. | G00 |
| R05 | FAIL_TO_PASS passes without breaking PASS_TO_PASS (p.4). | Official evaluator's per-instance report, raw test output, and parser/version provenance. | G06 |
| R06 | Run mini-swe-agent without modification; heavier SWE-agent is an acceptable declared alternative (p.4). | mini-swe-agent selected; pinned source and shipped prompt hashes; allowlisted config-only overrides. | G03 |
| R07 | Find relevant files, edit, run repository tests, and remediate from results (p.4). | Tool events, source diffs, observed tests, and repair trajectory. | G04 |
| R08 | Validate through executed tests before submission (p.4). | Patch-hash-bound visible-test gate in a clean base workspace. | G04 |
| R09 | Recover when a patch breaks the build or the agent loops (p.4). | Checkpoint/rollback and bounded loop recovery demonstrated on synthetic/development cases. | G05 |
| R10 | Per-task and overall percent resolved, reference vs custom, same model/budget (p.4). | Complete paired table with IDs, terminal status, costs, percentages, and lift. | G07 |
| R11 | Diffs and test output for both arms (p.4). | Per-episode patches, transcripts, command logs, official reports, and checksums. | G06, G08 |
| R12 | Identify likely memorization and explain the evidence (p.5). | Per-task contamination assessment, all-task primary score, supplementary flagged/unflagged breakdown. | G07 |
| R13 | Versions and seeds pinned; fair comparison (p.5). | Experiment lock, same schedule/settings, explicit unsupported-seed limitation if applicable. | G02, G07 |
| R14 | Public git repository with top-level README identifying completed tracks and exact commands (p.5). | Public visibility and verified clean-checkout README at final handoff. Current repository is private and contains a plan only. | G08 |
| R15 | One command regenerates both arms' reported numbers (p.5). | Planned `smartm2m reproduce` orchestrates inference, official scoring, and reporting. | G06, G08 |
| R16 | Configurable hosted endpoint and full logs for reproduction or audit without the key (p.5). | Configurable base URL; redacted complete evidence bundle; offline table regeneration. | G02, G08 |
| R17 | Short design: built system, rationale, limitations, next steps (p.5). | Update [DESIGN.md](../DESIGN.md) from proposed to actual behavior. | G08 |
| R18 | Time invested and scope reductions (p.5). | Actual time ledger and explicit cuts, distinct from planned estimates. | G08 |
| R19 | Cite resources used (p.1). | Source catalog, pinned upstream links, AI assistance record, and dependency/license notices as applicable. | G08 |

## Rubric alignment

The PDF describes four criteria weighted **approximately equally**, not an exact numerical scoring formula.

| Criterion | Strong evidence |
|---|---|
| Evaluation rigor and contamination control | Unchanged reference, same tasks/model/budget, isolated official tests, seeds and pins, transparent exposure review. |
| Execution on the track | Direct verification, useful tool interfaces, build and loop recovery. |
| Judgment and communication | Small coherent architecture, justified tradeoffs, short design, concrete next steps. |
| Transparency over score | Failed approaches, unresolved/blocked tasks, negative results, and honest limitations remain visible. |

## Requirements versus project choices

| Item | Classification |
|---|---|
| Three printed IDs | Examples only; the complete scored list is not supplied. |
| Verified Mini | Suitable pool mentioned by the PDF; not authorization to replace the fixed tasks or change the evaluator. |
| Python, Docker, DeepInfra, one worker | Proposed implementation choices, not employer-mandated vendors/languages. |
| One primary attempt and proposed $0.50 episode threshold | Experimental choices to validate on disjoint development tasks, then freeze. |
| Exact test-based resolution and matched comparison | Employer requirements. |
| Web UI, accounts, deployment URL, database, cloud service | Not required. |
| CTF/security benchmarks or bilingual PII training | Other tracks; not part of Track 3. |
| Track 1 pass@k or Track 2 span F1 | Not the Track 3 primary metric. |
| Guaranteed score, minimum lift, or deadline date | Not specified. |

Source interpretation is complete. The missing task manifest is a specific open requirement, not a reason to guess tasks or leave generic planning unfinished.
