# SMARTM2M SWE Agent

Plan for **Track 3: SWE agent** in the supplied AI Engineer Take-Home. Updated September 12, 2026.

**Status: documentation only. No agent, benchmark run, result, or executable reproduction command exists yet. No track is completed.**

The goal is to improve bug-fix success over **unmodified mini-swe-agent using the same model and budget** on the employer's fixed SWE-bench Verified instances. A task is resolved only when the official evaluator confirms that its FAIL_TO_PASS and PASS_TO_PASS checks pass. The submission should make that comparison easy to reproduce and audit.

## Start here

| Document | Purpose |
|---|---|
| [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) | Scope, architecture contracts, one-week build sequence, and acceptance gates. |
| [DESIGN.md](DESIGN.md) | Short proposed design, rationale, limitations, and future work. |
| [SETUP_AND_COMPARISON.md](SETUP_AND_COMPARISON.md) | Future setup, architecture/compute/model comparisons, and cost calculations. |
| [Requirements](docs/requirements.md) | PDF requirements mapped to planned evidence. |
| [Evaluation protocol](docs/evaluation-protocol.md) | Task freeze, baseline integrity, budgets, scoring, failure accounting, and artifacts. |
| [Security and contamination](docs/security-and-contamination.md) | Sandbox boundaries, clean evaluation, and memorization review. |
| [Assignment and sources](docs/assignment/README.md) | PDF provenance, missing task-list detail, reference revision, and primary sources. |
| [Submission checklist](docs/submission-checklist.md) | Reproduction, public repository, evidence, and handoff requirements. |
| [Time and scope](docs/time-and-scope.md) | Planned effort, actual-effort recording, and scope reductions. |
| [AI_USAGE.md](AI_USAGE.md) | Assistance used for this planning revision and what was verified. |

## Proposed approach

Build a small Python CLI around a sequential agent controller. Reuse the reference project's model transport and Docker integration where appropriate; keep its baseline agent and prompts unchanged. The custom controller adds evidence-guided file search, bounded edits, executed tests, checkpoints, and recovery from broken patches or repeated actions.

Use one Linux x86_64 machine and one task container at a time. Generate both arms' patches first, seal them, and score them in fresh containers with the pinned official SWE-bench harness. Store diffs, transcripts, test output, configuration, costs, and machine-readable results. A web application, hosted backend, database, and model training are outside this track's planned scope.

The first paid API candidate is **DeepInfra `openai/gpt-oss-120b`**, subject to a development-only compatibility check. The setup guide compares cheaper, free, and alternative routes without assuming measured coding quality. Select one route before evaluation; both arms must use it. No model calls or purchases were made for this plan.

## Prerequisites still open

1. **Complete fixed task list.** Page 4 says approximately eight instances but gives only three example IDs: `astropy__astropy-12907`, `django__django-11790`, and `django__django-11848`. These examples are not a complete authorized manifest. Obtain the employer's exact list or explicit task-selection clarification before scored runs. Do not invent the remaining IDs, substitute convenient tasks, or optimize the selection after seeing results.
2. **Execution machine and provider.** Verify Docker architecture, disk/RAM, endpoint access, tool-call support, model identity, pricing, and actual account quotas.
3. **Final experiment lock.** Freeze dataset revision, exact IDs/base commits, image digests, dependency lockfiles, prompts, model settings, and budgets before either scored arm runs.

These items do not prevent implementing the generic harness and synthetic checks later. They do prevent an honest completed benchmark claim today.

## Future run contract

The following is a **proposed CLI interface, not a working command at this revision**:

```sh
uv run --frozen smartm2m reproduce --config configs/experiment.lock.yaml
```

After implementation, this command must run both agents, evaluate both patch sets, and regenerate the report. Its preflight must reject missing task IDs or unresolved pins. Hosted inference requires a locally supplied key and configurable endpoint.

A second planned command, `uv run --frozen smartm2m audit --artifacts results/<run-id>`, will rebuild tables from recorded official reports without an API key. Auditing saved evidence is distinct from generating fresh patches or rerunning tests.

## Submission status

| Item | Current state |
|---|---|
| Selected/completed tracks | Track 3 selected; none completed. |
| Reference/custom resolved rate and lift | Not measured. |
| Diffs, execution logs, official test output | Not generated. |
| Repository | [itanium-g/smartm2m-swe-agent](https://github.com/itanium-g/smartm2m-swe-agent); private at planning time. The PDF requires a public repository at submission. |
| Deployed app URL | Not required by this PDF. |
| Deadline | No calendar deadline supplied; stated effort is approximately one week. |

The planning structure is adapted from [logistics-data-analytics at c261c93](https://github.com/itanium-g/logistics-data-analytics/tree/c261c93b017e78ab180846eedaa87c756ed144a3). Its application requirements and infrastructure choices do not apply to this assignment.
