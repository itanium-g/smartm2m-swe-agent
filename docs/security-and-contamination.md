# Security and contamination policy

## Workspace boundary

Each task is copied or cloned into a disposable workspace. The custom agent
can list files, search, read bounded files, apply source-only patches, run
trusted manifest commands, inspect its diff, roll back, and submit a patch.
Path traversal, .git paths, test paths, and common build/configuration files
are rejected by the edit tool. Command output is captured by the supervisor;
the agent cannot use an editable log as its only evidence.

The container/workspace is task-owned, not a multi-tenant security boundary.
Use a disposable VM or stronger isolation if the evaluation host contains
valuable data. Do not run broad cleanup commands on a shared host.

## Patch integrity

The controller checkpoints before edits, records attempted patches, and binds
the final patch SHA-256 to a clean-base replay. A model assertion is never
accepted as test evidence. The official evaluator receives a sealed standard
prediction file in a separate run.

The custom agent may not edit tests, delete tests, suppress collection, alter
expected outputs, or use hidden evaluator fields. Setup commands come from the
trusted manifest; visible tests may use a bounded repository-native runner,
with shell composition and destructive commands rejected.

## Leakage controls

Do not search assigned public issues for solution pull requests before the
primary run. Do not retrieve gold patches, hidden test lists, or benchmark
trajectories for prompts. Keep development fixtures synthetic or disjoint.
The supplied PDF's public examples and generic documentation are recorded as
source exposure, not used as solution demonstrations.

If a gold patch or hidden field reaches generation, stop the affected episode,
mark it as compromised, retain it in the denominator, and report the event.
Do not replace the task or claim that a new seed removes exposure.

## Post-run review

After both arms are sealed, inspect trajectories for:

- a specific patch emitted before relevant code inspection;
- hidden test or solution facts absent from the task input;
- ordinary small fixes after genuine reproduction; and
- procedural exposure or suspicious near-exact similarity.

Use categories no specific signal, suspected memorization, confirmed
exposure, or inconclusive. Publish all-task numbers first and any
flagged/unflagged supplementary view second. Never drop inconvenient losses.

## Publication

Redact API keys, bearer headers, credentials, and unrelated personal data.
Preserve commands, failures, costs, patch bytes, score-producing fields, and
redaction notes. Review the repository and evidence archive for secrets
before making it public.
