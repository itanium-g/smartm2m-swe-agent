# Assignment provenance and technical sources

## Supplied brief

| Property | Value |
|---|---|
| PDF | `2026-07-02-smartm2m-ai-takehome-task.pdf` |
| Track | Track 3 — SWE agent |
| Review | All five pages read before repository changes |

The brief asks for a custom bug-fixing agent compared with the standard
reference agent on the same model across approximately eight fixed SWE-bench
Verified issues. It explicitly names Verified Mini as a suitable 50-instance
pool and describes the three printed issue IDs as examples. It requires
per-task results, overall rates, lift, diffs, test/evaluation output, a public
README/command, pinned versions/seeds, logs without secrets, a design note,
and time/scope disclosure. It also requires contamination awareness for public
benchmarks.

This repository therefore freezes eight IDs by deterministic sampling from
Verified Mini instead of inventing an additional task-list requirement.

## Authoritative sources used

- SWE-bench Verified overview: https://www.swebench.com/verified.html
- Verified Mini description: https://hal.cs.princeton.edu/swebench_verified_mini
- Frozen dataset revision: https://huggingface.co/datasets/MariusHobbhahn/swe-bench-verified-mini/tree/b316c349947c29963fce3f4a65967c9807a4b673
- mini-swe-agent source: https://github.com/SWE-agent/mini-swe-agent/commit/a83fcae82d2a08f0ee0c688f9d137b3566c097f8
- mini-swe-agent SWE-bench usage: https://mini-swe-agent.com/latest/usage/swebench/
- SWE-bench evaluator source: https://github.com/SWE-bench/SWE-bench/commit/02e7a74ffd0b707aab73d203fe87bdc7c76afc8e
- SWE-bench evaluation guide: https://www.swebench.com/SWE-bench/guides/evaluation/

Pinned commits are in `requirements-evaluation.txt` and the experiment lock.
No gold patch, hidden test list, provider credential, or private assignment
attachment is committed or sent to generation.
