# Track 3 evaluation protocol

The code implements the following protocol. Freeze the completed task
manifest and lock before primary inference.

## Fixed set and input boundary

The employer's exact ordered instance IDs are the denominator. The three IDs
printed in the supplied PDF are examples only. Reject duplicates, missing
base commits, unknown IDs, and evaluation/development overlap before a scored
run. The current tasks/evaluation.json is intentionally pending.

Generation receives only:

- instance ID and issue statement;
- repository identity and base commit; and
- trusted operational metadata needed to prepare the workspace.

Patch, test_patch, hints_text, FAIL_TO_PASS, and PASS_TO_PASS stay in the
trusted evaluator area and are never mounted into generation or placed in the
custom prompt.

## Matched arms

The reference arm invokes mini-swe-agent v2.4.6 through mini-extra swebench
without source or prompt modification. The custom arm is separate code. Both
arms use the same model route, service tier, seed request, temperature,
completion limit, retry policy, task IDs, task order policy, wall-time
limit, nominal cost limit, and host/image policy.

The current starting profile is:

| Setting | Value |
|---|---|
| Model | openai/gpt-oss-120b through configurable OpenAI-compatible API |
| Temperature | 0 |
| Requested seed | 42 |
| Maximum completion | 8,192 tokens per model call |
| Turns | 60 per episode |
| Nominal API threshold | 0.50 USD per episode |
| Wall time | 2,700 seconds per episode |
| Test command timeout | 120 seconds |
| Primary attempts | 1 per task per arm |

The values are starting settings, not a measured optimum. The run manifest
records the effective configuration and known provider limitations.

## Run order and scoring

The runner prepares clean workspaces, generates both arms, seals prediction
files and artifact hashes, and only then invokes the official evaluator for
each arm with unique run IDs. Evaluation output never returns to primary
generation.

A task is resolved only if all official FAIL_TO_PASS tests pass and all
official PASS_TO_PASS tests pass. The report uses the complete confirmed N:

~~~text
reference rate = 100 * reference resolved / N
custom rate    = 100 * custom resolved / N
lift           = custom rate - reference rate
~~~

Missing, blocked, unparseable, or unevaluated instances count as unresolved in
the conservative headline. Pair categories show both-solved, custom-only,
reference-only, and neither-verified outcomes.

## Reproduction

~~~bash
smartm2m reproduce --config configs/experiment.lock.yaml --run-id track3-primary
smartm2m audit --config configs/experiment.lock.yaml --run-dir results/track3-primary
~~~

The API key is supplied only through the environment. Audit reads saved
records and needs no key.
