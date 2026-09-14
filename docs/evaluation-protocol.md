# Track 3 evaluation protocol

## Frozen task set

The SMARTM2M PDF permits the 50-instance SWE-bench Verified Mini subset. The
repository pins `MariusHobbhahn/swe-bench-verified-mini` at revision
`b316c349947c29963fce3f4a65967c9807a4b673`, verifies all 50 IDs against
`tasks/verified_mini_pool.txt`, sorts them, and samples eight with
`random.Random(42)`. The resulting ordered IDs and SHA-256 are committed in
`tasks/evaluation.selection.json`. The three IDs printed in the PDF are
examples; they are not silently forced into the sample. No ID may be replaced
after observing results.

The complete frozen denominator is:

```text
sphinx-doc__sphinx-8551
django__django-11999
django__django-11815
django__django-12304
django__django-12273
django__django-12262
django__django-12039
django__django-11964
```

## Generation boundary

`scripts/hydrate_manifest.py` reads the pinned dataset and writes only:

- instance ID and issue/problem statement;
- repository name, clone URL, and base commit;
- split and official x86_64 image name; and
- a safe repository-native test profile.

It rejects or omits `patch`, `test_patch`, `hints_text`, `FAIL_TO_PASS`, and
`PASS_TO_PASS`. The evaluator-only fields are not present in the custom
prompt, trajectory input, or workspace. They become available only to the
official evaluator after prediction files are sealed.

The reproduction command materializes the pinned revision locally as a
four-column safe dataset for reference/custom generation. After both arms
finish, it materializes the full revision separately for the official
evaluator. This avoids relying on a floating Hugging Face `main` snapshot.

## Matched arms

| Setting | Locked value |
|---|---|
| Model | `openai/gpt-oss-120b` |
| Endpoint | configurable, default `https://api.deepinfra.com/v1` |
| Key env | `DEEPINFRA_API_KEY` |
| Temperature / requested seed | `0` / `42` |
| Max completion | `8192` tokens per call |
| Reference / custom cap | 60 steps / 60 turns |
| Wall limit | 2,700 seconds per arm episode |
| Primary attempts | one per task per arm |
| Dollar budget | not claimed; pricing is unset |

The same model and request settings are used by the custom OpenAI-compatible
transport and stock mini-swe-agent/LiteLLM. Equal turn/token caps are the
enforceable common budget; observed token usage and any provider-reported cost
are retained separately. A requested seed is not claimed to guarantee hosted
determinism.

## Execution and scoring

The reference command is stock `mini-extra swebench` with configuration-only
overlays. Its output directory retains `preds.json`, per-instance trajectory
JSON, exit statuses, and mini-swe-agent logs. The custom arm retains the
trajectory, command JSONL, patch, validation, and sealed prediction per task.

After both arms finish, the pinned SWE-bench evaluator runs independently on
each prediction file. Only its `resolved` result is used for scoring. A task is
resolved only when official FAIL_TO_PASS tests pass and official PASS_TO_PASS
tests remain passing. Missing, blocked, empty, timed-out, or unparsable
records count as unresolved.

```text
reference % = reference_resolved / 8 * 100
custom %    = custom_resolved / 8 * 100
lift        = custom % - reference %
```

The report also counts both solved, custom only, reference only, and neither
verified. A reference win is reported, not hidden.

## One command

```bash
smartm2m reproduce --config configs/experiment.lock.yaml --run-id track3-primary
```

The API key is read only from the environment. `smartm2m audit` rebuilds the
summary from the retained evidence without calling the provider.
