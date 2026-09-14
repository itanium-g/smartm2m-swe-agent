# Track 3 design

## Built system

The repository now contains a small Python experiment runner with two isolated
arms:

1. Reference: invokes the shipped mini-swe-agent batch runner at the configured
   version. The reference source, prompts, parser, and agent are not imported
   or modified.
2. Custom: runs a separate sequential controller around the same
   OpenAI-compatible model route. It exposes bounded repository tools, records
   every action, executes trusted visible tests, and seals a patch only after
   clean-base replay validation.

The experiment runner creates one fresh workspace and trajectory per task,
preserves empty/failing predictions, runs the official evaluator only after
both arms are sealed, and produces a conservative paired report. The offline
smoke command exercises the same controller, patch capture, clean replay,
artifact, and reporting path on a synthetic fixture.

~~~mermaid
flowchart TD
    LOCK[Experiment lock and fixed manifest] --> BASE[Unmodified mini-swe-agent]
    LOCK --> CUSTOM[Custom controller]
    BASE --> SEALED[Sealed predictions]
    CUSTOM --> SEALED
    SEALED --> EVAL[Official evaluator in fresh runs]
    EVAL --> REPORT[Paired report and checksums]
~~~

## Why this design

The strongest low-cost opportunity in the brief is not a larger prompt; it is
reliable feedback and accounting. The custom arm therefore focuses on:

- search and file identification before editing;
- source-only unified patches;
- a trusted allowlist of test commands;
- observed return codes instead of model claims;
- a checkpoint before each edit;
- automatic rollback for syntax/import/build failures;
- one bounded recovery from repeated action/workspace states; and
- patch identity tied to a clean validation replay.

This keeps the causal difference between the arms legible. The model,
temperature, seed, maximum completion tokens, retry policy, wall-time limit,
nominal cost limit, task set, and official evaluator are intended to be
identical between arms. The custom controller's extra test-gating and recovery
are the measured intervention.

## Data boundary

Only the instance ID, issue statement, repository identity/base commit, and
trusted operational metadata reach generation. Evaluator-only fields such as
patch, test_patch, hints_text, FAIL_TO_PASS, and PASS_TO_PASS are not in the
generation payload. Official reports are read only after prediction files are
sealed. The controller never receives a gold patch or hidden test result.

## Known limitations

- The complete employer task manifest is missing from the supplied PDF, so no
  benchmark number is reported until the exact fixed IDs and pins are filled.
- The default hosted route is configurable and its backend weights are not
  provably immutable. A requested seed is recorded but cannot guarantee
  deterministic hosted output.
- Docker/SWE-bench image preparation and the official harness are external
  prerequisites. Their failures are recorded as infrastructure failures, not
  converted into agent successes.
- The mini-swe-agent command is an integration boundary; its installation and
  exact output layout must be verified during preflight on the evaluation host.
- One attempt per task and approximately eight instances provide limited
  statistical precision. Paired gains/losses are more informative than a
  broad superiority claim.
- Automatic build rollback uses the latest task checkpoint and is intentionally
  conservative; a semantic test failure is returned to the model for repair
  rather than being assumed to be a broken build.

## Next steps before submission

1. Obtain the employer-authorized task manifest and replace the pending
   placeholder without changing the denominator.
2. Freeze the dataset revision, base commits, image digests, model metadata,
   prices, dependency lock, prompt hashes, and evaluator revision.
3. Run an isolated mini-swe-agent smoke task, then the paired primary run.
4. Inspect every trajectory for accidental solution exposure or memorization
   signals and publish the assessment without removing flagged tasks.
5. Publish the repository and durable redacted result bundle; report losses,
   blocked tasks, actual costs, and scope reductions.
