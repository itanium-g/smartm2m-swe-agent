# Track 3 submission checklist

## Repository acceptance

- [x] Top-level README identifies Track 3 and the exact reproduction command.
- [x] Eight IDs are frozen from the authorized Verified Mini pool before runs.
- [x] Dataset, mini-swe-agent, evaluator, model request, seed, and limits are locked.
- [x] Safe hydration and hidden-field rejection/projection checks exist.
- [x] Custom agent inspects, edits, runs observed tests, recovers, validates, and seals patches.
- [x] Stock mini-swe-agent remains the reference boundary.
- [x] Official evaluator is the only resolution authority.
- [x] Reports use denominator eight and show reference wins and negative lift.
- [x] Logs, patches, trajectories, commands, validation, evaluator output, usage, and checksums have an artifact layout.
- [x] CI runs install, compile, lint, offline smoke, and unit tests; benchmark is not automatic.

## Before publishing a benchmark claim

- [x] Set `GROQ_API_KEY` (or configure in `.env`) in the benchmark environment and verify balance/quota.
- [x] Run the exact one-command primary protocol on a compatible x86_64 Linux/Docker host.
- [x] Confirm `mini-extra swebench --help`, generated argv, output layout, and evaluator artifacts are retained.
- [x] Seal code/config/version/task/model hashes before generation; keep debug runs separate.
- [x] Review every reference and custom trajectory for contamination signals.
- [x] Fill the time-invested record with honest human active hours and unattended elapsed time.
- [x] Re-run the secret/publication scan on the final evidence bundle after a
      real primary run adds new artifacts.
- [x] Repository visibility is public; the assignment thread received the one
      authorized submission. No further email is required for this continuation.

Do not replace a blocked task or present synthetic smoke output as the
eight-task benchmark.
