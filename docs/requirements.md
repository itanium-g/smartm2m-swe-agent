# Assignment requirements and evidence

This is the audit matrix for the supplied SMARTM2M PDF. “Blocked” means an
external prerequisite is absent, not that the repository silently skips the
requirement.

| Requirement | State | Evidence |
|---|---|---|
| Track 3 implementation | PASS | custom controller and paired runner |
| Exactly eight frozen tasks | PASS | frozen manifest and selection hash |
| Verified Mini pool/revision | PASS | committed 50 IDs and HF revision |
| No evaluator-field leakage | PASS | hydration allowlist/projection/tests |
| Same model and meaningful budget | PASS | lock and reference overlay |
| Unmodified mini-swe-agent | PASS | external pinned subprocess |
| Actual repository test execution | PASS | bounded commands, container image path, logs |
| Build/loop recovery | PASS | checkpoint, rollback, repeated-state tests |
| Official evaluator | PASS | pinned SWE-bench subprocess/parser fixture |
| Per-task/overall/lift report | PASS | `reporting.py` and generated table |
| Real reference/custom numbers | BLOCKED | Docker and provider secret unavailable in Work |
| Reference/custom full logs | PARTIAL | code retains them; no primary run yet |
| Contamination review | PARTIAL | worksheet/heuristics; human review remains |
| One-command reproduction | PASS | `smartm2m reproduce ...` |
| README/design/limitations | PASS | top-level docs |
| Time invested | PARTIAL | honest placeholder; user must fill hours |
| Public repository | BLOCKED | visibility change is manual |
| Secret scan/publication prep | PARTIAL | local scan required again after real run |
