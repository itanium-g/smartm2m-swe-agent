# Manual actions remaining

Only the following actions remain outside the Work environment or require the
user’s judgment. Ordinary engineering, testing, pinning, and documentation
work is complete.

1. **Provider secret and quota.** Set `GROQ_API_KEY` (or configure it in `.env`)
   in the isolated benchmark environment and confirm sufficient Groq balance/quota.
   Never add it to Git or result logs.

2. **Compatible benchmark host — urgent if Work remains Dockerless.** Run on
   x86_64 Linux with Docker and the pinned images available. From the repository
   root, install the pinned dependencies and execute:

   ```bash
   python -m pip install -e ".[dev]"
   python -m pip install -r requirements-evaluation.txt
   export GROQ_API_KEY="..."
   smartm2m reproduce --config configs/experiment.lock.yaml --run-id track3-primary
   ```

   Preserve `results/track3-primary/` as the primary evidence bundle. Do not
   replace tasks if an image, API call, or evaluator run fails.

   The pinned evaluator was also invoked here with a valid empty-patch
   prediction; it stopped before writing an official report because the Docker
   socket is unavailable. No score was inferred from that attempt.

3. **Contamination judgment.** Review the retained reference and custom
   trajectories after sealing and replace the worksheet’s `inconclusive`
   categories with human-supported classifications. Keep flagged tasks in the
   denominator and disclose the rationale.

4. **Time invested.** Fill the honest approximate human active hours and
   unattended benchmark elapsed time in `docs/time-and-scope.md`.

5. **Post-run publication scan.** After any real primary run, re-run the secret
   scan against the complete evidence bundle before committing new artifacts.

The repository visibility is now verified public. The assignment thread has
already received one authorized submission; no additional email is required
for this continuation.
