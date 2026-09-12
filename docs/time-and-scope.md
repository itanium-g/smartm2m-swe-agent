# Time invested and scope

Updated: 2026-09-12. The PDF asks for actual time invested and reductions in scope. Planned allocations are not actual effort.

## Current record

| Activity | Status | Actual time record |
|---|---|---|
| PDF/source review and reference-repository adaptation | Completed in one assistant-assisted planning session | Exact human active time was not recorded; no hour total is claimed. |
| Primary-source checks and document authoring | Completed as part of that session | Included above; not a measured benchmark or development run. |
| Agent implementation | Not started | No implementation work performed in this revision. |
| Model inference and benchmark evaluation | Not run | No model/test-execution cost or timing result. |
| Deployment/employer submission | Not performed | Not part of the planning request. |

Do not backfill estimated planning time as measured work. Before final submission, add any actual candidate effort separately and explain an unrecorded planning component honestly.

## Future allocation

The [implementation plan](../IMPLEMENTATION_PLAN.md) allocates 34 active hours plus 6 hours of contingency across approximately one week. Image download/build time, model execution, evaluator time, and waiting for access are separately measured elapsed time. This is a planning envelope, not a promised completion time or a supplied deadline.

Record future work with date, activity, active minutes, unattended elapsed minutes, cost if applicable, output/run ID, and blockers. Do not sum parallel elapsed durations into human hours. Report the actual total and uncertainty at handoff.

## Scope decisions

| Item | Decision and reason |
|---|---|
| Tracks 1 and 2 | Not selected; the brief allows one strong track. |
| Website, login, API service, database, deployment URL | Excluded; Track 3 requires a reproducible repository experiment. |
| Model training | Excluded; this track measures harness improvement using the same model. |
| Multiple model/providers in the primary result | Excluded; select one before freeze to preserve comparison and time. |
| Semantic retrieval and multiple-agent search | Deferred until basic validation/recovery has measured evidence. |
| Paired repeat runs and ablations | P1, added only after primary artifacts are complete and budget remains. |
| Confirmed task count, second arm, official tests, failure logs, contamination review | Preserved; cannot be silently cut to meet the timebox. |

No implementation scope reductions have yet occurred because implementation has not started. If future work is incomplete, record exactly what was omitted, why, how much time was spent, and how it affects interpretation. A negative or partial result is preferable to an inflated completeness claim.
