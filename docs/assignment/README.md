# Assignment provenance and sources

Source review date: **2026-09-12 UTC**. The user supplied the PDF and requested a plan analogous to their logistics repository, adapted to Track 3 in `itanium-g/smartm2m-swe-agent`.

## Supplied file

| Property | Value |
|---|---|
| Filename | `2026-07-02-smartm2m-ai-takehome-task.pdf` |
| Visible document title | AI Engineer Take-Home |
| Pages | 5 |
| Bytes | 139,480 |
| SHA-256 | `27cd1847ac16eb0b08c2d3e40e3ab6d116a62deba6de9c822d393e827416c8fc` |
| Review | All pages extracted/read; Track 3 and shared requirements on pages 4-5 rendered and visually checked. |
| Repository treatment | Original file is not committed; the requirements are summarized with page references. |

The filename is not treated as the application deadline. The PDF states approximately one week of effort but supplies no calendar submission date. It permits any code/API/framework/model with attribution and prefers focused, reproducible work.

## Page map and open task detail

| Page | Content |
|---|---|
| 1 | Overall purpose, approximately one-week effort, at least one track, emphasis on judgment/rigor. |
| 2 | Track 1 security harness; outside this plan. |
| 3 | Track 2 bilingual PII training; outside this plan. |
| 4 | Track 3: same-model reference comparison, real GitHub issues, tests, recovery, results/evidence. |
| 5 | Contamination, four approximately equally weighted criteria, public repository and reproduction packaging. |

Page 4 names `astropy__astropy-12907`, `django__django-11790`, and `django__django-11848` as **examples**. No complete eight-instance list appears elsewhere in the supplied PDF, and its link annotations point to the SWE-bench site and mini-swe-agent repository rather than a task manifest. Consequently, the final fixed task list must be supplied or clarified before scored runs. No extra IDs have been selected for this plan.

The PDF hyperlinks for Track 3 are [SWE-bench](https://www.swebench.com/) and [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent). The Verified Mini dataset name below was identified through public documentation; it is a candidate pool, not proof of the employer's intended list.

## Planning reference

The reference is [itanium-g/logistics-data-analytics at c261c93b017e78ab180846eedaa87c756ed144a3](https://github.com/itanium-g/logistics-data-analytics/tree/c261c93b017e78ab180846eedaa87c756ed144a3), inspected September 12. Its README, implementation plan, research/design report, requirements, and setup/comparison structure informed this package.

Retained patterns: explicit planning status, source requirements, small prioritized scope, decision matrices, cost assumptions, acceptance gates, and submission checks. Replaced: logistics data semantics, dashboard/forecast features, web hosting, deployment URL, and the 6-10-hour application timebox. No reference application code or private assignment attachments were copied.

## Primary technical sources

All links below were inspected for the claims used in this plan. Mutable documentation/prices are dated snapshots; final dependencies and account behavior remain subject to preflight.

| Source | Use and limitation |
|---|---|
| [mini v2.4.6 release](https://github.com/SWE-agent/mini-swe-agent/releases/tag/v2.4.6) | Observed release, published July 23, 2026; fixes cost accounting for responses that fail parsing. |
| [Pinned mini source](https://github.com/SWE-agent/mini-swe-agent/tree/a83fcae82d2a08f0ee0c688f9d137b3566c097f8) | Candidate reference commit. |
| [Pinned SWE-bench config](https://github.com/SWE-agent/mini-swe-agent/blob/a83fcae82d2a08f0ee0c688f9d137b3566c097f8/src/minisweagent/config/benchmarks/swebench.yaml) | Shipped prompt and budget/environment settings; unchanged baseline template. |
| [Pinned DefaultAgent](https://github.com/SWE-agent/mini-swe-agent/blob/a83fcae82d2a08f0ee0c688f9d137b3566c097f8/src/minisweagent/agents/default.py) | Between-call budget/time checks and model-call accounting. |
| [Pinned LiteLLM transport](https://github.com/SWE-agent/mini-swe-agent/blob/a83fcae82d2a08f0ee0c688f9d137b3566c097f8/src/minisweagent/models/litellm_model.py) | Tool calls, retry wrapper, cost registry, response serialization. |
| [mini SWE-bench usage](https://mini-swe-agent.com/latest/usage/swebench/) | Batch prediction generation, configuration, and local/cloud evaluation routes. Mutable guide; validate against pinned source. |
| [Official SWE-bench revision](https://github.com/SWE-bench/SWE-bench/tree/02e7a74ffd0b707aab73d203fe87bdc7c76afc8e) | Candidate evaluator revision inspected September 12; resource/caching guidance. |
| [Evaluation guide](https://www.swebench.com/SWE-bench/guides/evaluation/) | Official evaluation workflow. |
| [Harness requirements](https://www.swebench.com/SWE-bench/reference/harness/) | CPU/RAM/disk/architecture guidance. |
| [Docker setup](https://www.swebench.com/SWE-bench/guides/docker_setup/) | Container preparation and resource considerations. |
| [HAL Verified Mini](https://hal.cs.princeton.edu/swebench_verified_mini) | Identifies a 50-task subset; leaderboard figures are not this project's baseline. |
| [Mini dataset card](https://huggingface.co/datasets/MariusHobbhahn/swe-bench-verified-mini/blob/main/README.md) | Schema, 50 examples, and lightweight-storage claim. Card only; no solution rows retrieved. |
| [sb-cli overview](https://www.swebench.com/sb-cli/) | Cloud prediction submission/report retrieval; token/quota and version parity not verified. |
| [DeepInfra GPT-OSS 120B](https://deepinfra.com/openai/gpt-oss-120b), [API](https://deepinfra.com/openai/gpt-oss-120b/api) | Listed model price/context/functions and endpoint; no account or live-model check. |
| [DeepInfra GPT-OSS 20B](https://deepinfra.com/openai/gpt-oss-20b) | Alternative paid model price. |
| [Groq models](https://console.groq.com/docs/models), [limits](https://console.groq.com/docs/rate-limits) | Paid prices and public free quota snapshot. Account dashboard controls actual limits. |
| [DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing/) | Current served identities, alias remapping, peak/off-peak rates. |

**Incidental example exposure:** the official evaluation guide displayed a short example diff for `sympy__sympy-20590` while its generic CLI/report documentation was being read. This was not a search for that issue's solution, but it is still possible solution exposure. Check this ID against the employer's eventual manifest, record the exposure if relevant, and never use the example as a prompt fixture or silently drop/substitute an assigned task because of it.

No model/agent benchmark, installed lockfile compatibility, or account entitlement has been independently tested. Dataset solution rows and a gold-patch corpus were not downloaded. The full employer manifest, dataset revision, image digests, model backend pin/support, and implementation tests remain open.

## Attribution and licensing

Keep citations for resources actually used. Inspect upstream licenses when implementation reuses code; preserve applicable notices. Public availability does not grant permission to relicense employer materials or all benchmark repository content. No blanket license over those materials is introduced by this planning revision.
