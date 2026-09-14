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

- [ ] Set `DEEPINFRA_API_KEY` in the isolated benchmark environment and verify account balance/quota.
- [ ] Run the exact one-command primary protocol on a compatible x86_64 Linux/Docker host.
- [ ] Confirm `mini-extra swebench --help`, generated argv, output layout, and evaluator artifacts are retained.
- [ ] Seal code/config/version/task/model hashes before generation; keep debug runs separate.
- [ ] Review every reference and custom trajectory for contamination signals.
- [ ] Fill the time-invested record with honest human active hours and unattended elapsed time.
- [ ] Re-run the secret/publication scan on the final evidence bundle.
- [ ] Make the repository public and submit its URL to SMARTM2M.

Do not replace a blocked task or present synthetic smoke output as the
eight-task benchmark.
