# Time invested and scope reductions

## Human time record

The repository cannot know the user’s true human active time. Before
submission, fill the following without counting it as benchmark performance:

```text
MANUAL: Human active time invested: ____ hours.
MANUAL: Unattended benchmark/evaluation elapsed time: ____ hours.
MANUAL: Primary run ID and evidence-bundle SHA-256: ____________________.
```

The current implementation session recorded engineering commands and tests but
does not invent a human-hours total.

## Scope reductions

- Track 3 only; Tracks 1 and 2 excluded.
- One model/provider and one stock reference agent.
- Eight fixed Verified Mini tasks, selected once with seed 42.
- One primary attempt per arm (pass@1).
- No UI, database, hosted service, vector store, model training, or alternate provider.
- No multi-agent orchestration, semantic retrieval, best-of-many scoring, or ablation matrix.

These cuts preserve the deadline-critical paired comparison and its audit
evidence instead of expanding the system around an unrun benchmark.
