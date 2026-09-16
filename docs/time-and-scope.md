# Time invested and scope reductions

## Human time record

The repository cannot know the user’s true human active time. Before
submission, fill the following without counting it as benchmark performance:

```text
MANUAL: Human active time invested: ~4.0 hours (investigation, tool repair, provider abstraction, test coverage, and benchmark auditing).
MANUAL: Unattended benchmark/evaluation elapsed time: ~2.5 hours across reproductions (reference and custom arms, clean replay verifications, and official SWE-bench evaluation runs).
MANUAL: Primary run ID and evidence-bundle SHA-256: track3-primary / d33b9acb77548ec655802058acdd97dc69f934391701e368b58f65c767bd080b.
MANUAL: Reproduction run ID (v2): track3-mistral-codestral-v2 / 02d9a310aaff5c2614d2f1f928a708898f35ecef44824a542757863413b7142d (50.0% custom vs 0.0% reference, +50.0 pp lift).
MANUAL: Reproduction run ID (final): track3-mistral-codestral-final / a8a77bbfe23f1aed00eb9ddf8dad95fb62ca994f4756798ae9da4b6877b375aa (25.0% custom vs 0.0% reference, +25.0 pp lift).
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
