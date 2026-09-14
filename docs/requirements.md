# Assignment requirements and evidence

This table distinguishes implemented plumbing from evidence that requires the
employer's missing fixed task list and a live evaluation environment.

| ID | Requirement | Current evidence | State |
|---|---|---|---|
| R01 | Select and execute at least one track | Track 3 selected; controller implemented | done |
| R02 | Beat the same-model reference | Paired runner and report arithmetic | benchmark pending |
| R03 | Pin a model/API | Lock fields and redacted run manifest | live pin pending |
| R04 | Use the fixed approximately eight IDs | Strict manifest gate; placeholder has zero tasks | blocked until manifest |
| R05 | FAIL_TO_PASS and PASS_TO_PASS resolution | Official evaluator boundary; no inferred score | benchmark pending |
| R06 | Run unmodified mini-swe-agent | mini-extra subprocess wrapper | runtime verification pending |
| R07 | Identify files, edit, test, and remediate | Typed custom tools and controller | implemented |
| R08 | Validate by executed tests | Clean-base replay bound to patch hash | implemented |
| R09 | Recover broken builds/loops | Checkpoint, rollback, repeated-state recovery | implemented |
| R10 | Per-task/overall reference vs custom rate and lift | Offline paired reporter | implemented |
| R11 | Diffs and test output for both arms | Artifact layout and prediction files | implemented |
| R12 | Contamination/memorization disclosure | Policy and per-run note path | implemented |
| R13 | Versions and seeds pinned | Lock and manifest fields | live support pending |
| R14 | Public git repository and exact commands | README and reproducible CLI | repository publication pending |
| R15 | One command regenerates both numbers | smartm2m reproduce | implemented |
| R16 | Configurable hosted endpoint and audit logs | OpenAI-compatible URL and redacted artifacts | implemented |
| R17 | Short design document | DESIGN.md | implemented |
| R18 | Actual time and scope reductions | docs/time-and-scope.md | active minutes pending |
| R19 | Cite resources used | docs/assignment/README.md | implemented |

The current repository makes no positive benchmark or lift claim. This is
deliberate: an honest partial result is preferred by the brief to an invented
task list or score.
