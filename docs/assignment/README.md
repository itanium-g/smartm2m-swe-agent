# Assignment provenance and sources

## Supplied brief

| Property | Value |
|---|---|
| Filename | 2026-07-02-smartm2m-ai-takehome-task.pdf |
| Visible title | AI Engineer Take-Home |
| Pages | 5 |
| Track implemented | Track 3: SWE agent |
| Source review | All pages read; Track 3 and shared submission requirements checked |

Track 3 asks for a custom harness that beats the standard reference agent on
the same model across approximately eight fixed SWE-bench Verified instances.
The reference is mini-swe-agent without modification. The custom system must
identify files, edit source, run tests, remediate from results, validate before
submission, and recover from broken builds or loops. The deliverable is
per-task and overall percent resolved, reference-versus-custom lift, diffs,
and test output.

The brief names astropy__astropy-12907, django__django-11790, and
django__django-11848 as examples. It does not provide the complete fixed list.
This repository therefore keeps tasks/evaluation.json pending and refuses a
scored run until the exact employer-authorized manifest is supplied.

## Technical sources

- mini-swe-agent v2.4.6 and candidate source commit
  a83fcae82d2a08f0ee0c688f9d137b3566c097f8:
  https://github.com/SWE-agent/mini-swe-agent
- Candidate SWE-bench evaluator commit
  02e7a74ffd0b707aab73d203fe87bdc7c76afc8e:
  https://github.com/SWE-bench/SWE-bench
- SWE-bench evaluation guide:
  https://www.swebench.com/SWE-bench/guides/evaluation/
- mini-swe-agent SWE-bench usage:
  https://mini-swe-agent.com/latest/usage/swebench/

The implementation uses these sources for invocation and evaluation boundaries,
not for solution patches or task-specific prompt examples. No benchmark gold
patches, hidden test lists, provider keys, or private assignment attachments
are committed.

## Reference and licensing

The reference agent is an external dependency. Its source is not vendored or
modified. Its own license and dependency notices apply when installed in the
evaluation environment. This repository is MIT-licensed for the controller
and experiment code; benchmark repositories, datasets, and employer materials
remain subject to their original terms.
