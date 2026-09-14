# Time invested and scope

## Actual record

The implementation was completed in an assistant-supported coding session on
2026-09-14. The workspace recorded command outputs and smoke artifacts, but
human active minutes were not separately instrumented. No invented hour total
is reported. Benchmark inference, API spend, and official evaluation time are
zero in the current repository state.

## Completed work

- Python package and CLI;
- provider-neutral model transport;
- custom controller, typed tools, checkpoint/rollback, loop recovery;
- patch capture, clean replay validation, prediction serialization;
- reference/evaluator integration boundaries;
- offline paired reporting, checksums, CI, and documentation.

## Scope reductions

Tracks 1 and 2, model training, a web UI, accounts, database, hosted service,
vector retrieval, multi-agent planning, multiple primary providers, and
best-of-many scoring were excluded. They do not satisfy the highest-value
missing requirement: an honest matched Track 3 comparison on the employer's
fixed IDs.

The custom controller was kept small enough to inspect under the deadline.
Semantic retrieval, richer ablations, repeated primary attempts, and
alternative models are deferred until the fixed manifest, first paired run,
and evidence bundle are complete.

## Remaining time record

Before employer handoff, add dated active minutes, unattended elapsed minutes,
model/provider cost, run ID, blockers, and actual reductions. Keep parallel
elapsed time separate from human active time.
