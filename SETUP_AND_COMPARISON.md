# Setup and comparison

```bash
python -m pip install -e ".[dev]"
python -m pip install -r requirements-evaluation.txt
python -m compileall -q src
ruff check .
python -m pytest
smartm2m smoke
```

The evaluation requirements pin mini-swe-agent, SWE-bench, and the tested
Python runtime dependencies. The locked dataset revision and selection
fingerprint are checked by the manifest; the hydration script is the canonical
way to refresh safe metadata before freezing a new protocol.

## Reference command shape

The runner generates a stock invocation equivalent to:

```bash
mini-extra swebench -c swebench.yaml -c configs/reference-overrides.yaml \
  --model openai/gpt-oss-120b \
  --subset results/<run>/dataset-generation --split test \
  --workers 1 --filter '^(?:...)$' --output results/<run>/reference
```

The exact argv, stdout/stderr, `preds.json`, per-task `.traj.json`, exit
statuses, and `minisweagent.log` are retained. The upstream reference source,
prompt, parser, loop, and tool semantics are not modified.

The runner materializes the local four-column generation dataset from the
immutable revision before invoking this stock command.

## Evaluator command shape

```bash
python -m swebench.harness.run_evaluation \
  --dataset_name results/<run>/dataset-evaluation --split test \
  --predictions_path results/<run>/<arm>/predictions.jsonl \
  --max_workers 1 --run_id <unique-run-id>
```

The evaluator is invoked only after both prediction files are sealed. Its
`resolved` field and tests-status report are the only scoring authority.

## Budget and endpoint

Both arms use the same model, endpoint, temperature, requested seed,
completion-token limit, and one-attempt/60-step or turn cap. Provider pricing
is configured for Groq ($0.15/$0.60 per million input/output tokens); known
observed spend and token counts are written separately. The API key is supplied
through `GROQ_API_KEY` (or `.env`).
