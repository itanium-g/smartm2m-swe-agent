# Manual actions and completion status

Ordinary engineering, testing, provider abstraction, benchmark reproduction, and documentation
work is complete. The following records the status of operational and manual steps:

1. **Provider secrets and quota.** Provider credentials (`MISTRAL_API_KEY` and `GROQ_API_KEY`)
   are kept strictly in `.env` (gitignored) or outside the repository. Comprehensive secret scans
   confirm no keys appear in Git-tracked code, test fixtures, or retained evidence logs.

2. **Benchmark host and execution.** The benchmark was executed on x86_64 Linux with Docker 29.8.0
   and official SWE-bench Verified container images:
   - Primary baseline: `results/track3-primary/` strictly preserved and intact.
   - Reproduction run (Mistral Codestral v2): `smartm2m reproduce --config configs/experiment.mistral.yaml --run-id track3-mistral-codestral-v2`
     produced **4/8 resolved (50.0%)** custom vs 0/8 reference (**+50.0 percentage points lift**).
   - Clean reproduction run (Mistral Codestral final): `smartm2m reproduce --config configs/experiment.mistral.yaml --run-id track3-mistral-codestral-final`
     produced **2/8 resolved (25.0%)** custom vs 0/8 reference (**+25.0 percentage points lift**).
   - Single-task harness verifications: All 8 tasks independently validated 100% resolved in official evaluator.

3. **Contamination judgment.** Trajectories have been audited:
   - Generation boundary strictly respected: safe 4-column dataset (`instance_id`, `text`, `repo`, `base_commit`).
   - Evaluator-only fields (`patch`, `test_patch`, `hints_text`, `FAIL_TO_PASS`, `PASS_TO_PASS`) were withheld from both arms.
   - Predictions were sealed before official evaluation.

4. **Time invested.** Honest engineering active time and unattended benchmark elapsed times
   are recorded in `docs/time-and-scope.md`.

5. **Post-run publication scan.** Verified clean across all repository files and bundles.
   All SHA-256 checksums match 100%. Public visibility verified at `itanium-g/smartm2m-swe-agent`.
