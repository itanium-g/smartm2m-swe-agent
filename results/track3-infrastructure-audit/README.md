# Infrastructure audit evidence

These files are retained evidence from two pre-primary probes run on
2026-09-14 UTC. They are not benchmark results and must not be used as the
Track 3 headline score.

The reference probe used the frozen task `sphinx-doc__sphinx-8551`, the pinned
local safe dataset, stock mini-swe-agent 2.4.6, and the locked model settings.
It loaded the 50-row generation dataset and filtered it to one task, then
stopped before model execution because `docker` is unavailable. Its valid
prediction row is therefore an empty patch and its exit-status file records
the infrastructure error.

The evaluator probe passed a valid empty-patch prediction to the pinned
SWE-bench evaluator. It stopped before writing a score/report because the
Docker socket is unavailable. No resolution was inferred.

The complete eight-task primary command remains:

```bash
smartm2m reproduce --config configs/experiment.lock.yaml --run-id track3-primary
```

Run it only after setting the provider key on a compatible x86_64 Docker host.
