# Setup, architecture, compute, and model comparison

Checked: **2026-09-12 UTC**. This is a future runbook for Track 3. **No setup, inference, paid service, or benchmark execution has been performed.** Commands for the `smartm2m` package are proposed interfaces and will not work until implemented.

Recommended starting design: **Python CLI + unmodified mini-swe-agent baseline + custom sequential controller + isolated Docker tasks + official SWE-bench evaluation**. Use an existing suitable x86_64 Linux machine when available. First paid model candidate: DeepInfra `openai/gpt-oss-120b`. Test transport compatibility on synthetic/disjoint development tasks before selecting the final route.

## 1. Architecture decision matrix

| Option | Task fit | Build effort | Operating cost | Decision |
|---|---|---|---|---|
| Small custom controller using mini-swe-agent transport/environment | Direct control over validation/recovery; easy baseline separation | Low to medium | One model and one machine | Selected. |
| Prompt-only variant of mini-swe-agent | Useful development ablation; limited enforcement | Low | Similar inference | Insufficient as the complete planned recovery/verifier design. |
| LangGraph or comparable workflow framework | Can express the same state transitions | Medium; extra concepts/dependencies | Mostly inference/compute | No current need; plain Python is adequate. |
| Heavier SWE-agent reference and custom extension | Allowed by the PDF if declared | Medium to high | Larger operational surface | Keep as an alternative only if mini has a concrete compatibility blocker. |
| Multiple agents/search branches | Greater search breadth, more budget/accounting complexity | High | More model calls | Defer; no uncounted helper model. |
| Full web app with API/database | Adds presentation and hosting | High | Additional services | Not required for a reproducible take-home. |

These are engineering judgments, not benchmark measurements. The inspected [mini reference](https://github.com/SWE-agent/mini-swe-agent/tree/a83fcae82d2a08f0ee0c688f9d137b3566c097f8) provides model/environment interfaces and batch SWE-bench tooling; sharing them reduces integration differences. [Usage documentation](https://mini-swe-agent.com/latest/usage/swebench/)

## 2. Compute and hosting comparison

This workload runs arbitrary repository tests and historical dependencies. Compare **temporary experiment compute**, not monthly web-request allowances.

| Route | Incremental cash cost | Fit and limitations | Decision |
|---|---|---|---|
| Existing suitable x86_64 workstation/server | $0 new rental; electricity/storage still have cost | Docker access and sufficient free disk/RAM required | Preferred when available. |
| Authorized university/company machine | Depends on supplied access; may be $0 | Permission, workload policy, Docker availability, and artifact export must fit | Useful if already available; no access assumed. |
| Short-lived Linux x86_64 VM | Quoted hourly CPU/RAM + disk + transfer | Straightforward Docker parity; volume charges may continue after stopping compute | Fallback; quote actual region/spec before provisioning, delete only task-owned resources after exporting results. |
| Official `sb-cli` cloud evaluation | Mini documentation advertises free evaluation; actual token/quota/access must be checked | Scores uploaded predictions; does not supply the agent's interactive execution environment. Verify evaluator version and exportable full logs. | Optional scoring fallback after a compatibility check. |
| Managed sandbox/Modal-style execution | Provider-specific usage and credits | Can help when local Docker is unavailable; adds provider integration and provenance work | P1 if necessary; no assumed free entitlement. |
| GitHub-hosted CI | Account-dependent minutes/storage | Good for small offline checks; full benchmark resource fit and log retention need validation | Not the primary experiment machine. |
| Static website hosting | Often unnecessary incremental spend | Can display a report; is not the planned Docker execution host | Skip for P0. |
| Local model hosting plus task containers | Hardware, memory, electricity, and setup | No per-token API fee, but inference and tests compete for resources | Only if suitable hardware already exists and performance is verified. |

Official SWE-bench guidance recommends x86_64, approximately **120 GB free disk, 16 GB RAM, and 8 CPU cores**, and describes arm64 support as experimental. Treat this as a planning baseline, not a measured minimum for eight tasks. Serial execution may reduce simultaneous demand, but image pulls and layers still need space. [Harness requirements](https://www.swebench.com/SWE-bench/reference/harness/), [Docker setup](https://www.swebench.com/SWE-bench/guides/docker_setup/)

A Windows-on-ARM laptop should not be assumed to run the standard images reliably or cheaply through emulation. Check architecture first; use a suitable x86_64 host if needed. The Mini dataset card's roughly 5 GB storage claim refers to its lighter setup and does not establish the footprint of this project's exact task/image set. [Mini dataset card](https://huggingface.co/datasets/MariusHobbhahn/swe-bench-verified-mini/blob/main/README.md)

For cloud evaluation, inspect access and quota with the selected service before depending on it. The [mini guide](https://mini-swe-agent.com/latest/usage/swebench/) and [sb-cli overview](https://www.swebench.com/sb-cli/) describe prediction submission and result retrieval. Preserve local official evaluation as the primary path until version parity, full evidence, and exact task support are established.

## 3. Model/API comparison

The shortlist is deliberately relevant to a one-week coding-agent experiment; it is not an exhaustive provider market survey. Prices are published USD per million tokens checked September 12. Account eligibility, top-up minimums, taxes, service-tier differences, quota, and model quality remain unverified.

Normalize one illustrative episode to **500,000 total billed input tokens plus 50,000 total billed output tokens**, accumulated over all turns. A transcript is resent repeatedly; input is not just the initial issue text. Count reasoning tokens under the provider's billing rules. Assume no cache discount. A full comparison with N=8 and one attempt has 16 episodes.

| Provider/model route | Input / output per 1M | Illustrative episode | Illustrative 16 episodes | Fit / caution |
|---|---:|---:|---:|---|
| DeepInfra `openai/gpt-oss-120b` | $0.037 / $0.17 | $0.0270 | **$0.432** | First paid candidate; supports a listed 131,072-token context and functions. Transport/settings need a smoke check. [Model](https://deepinfra.com/openai/gpt-oss-120b) |
| DeepInfra `openai/gpt-oss-20b` | $0.03 / $0.14 | $0.0220 | **$0.352** | Cheaper alternative; no measured success-rate comparison. [Model](https://deepinfra.com/openai/gpt-oss-20b) |
| Groq `openai/gpt-oss-120b`, paid | $0.15 / $0.60 | $0.1050 | **$1.680** | Alternative provider route; separately freeze served model identity. [Model list/prices](https://console.groq.com/docs/models) |
| Groq `openai/gpt-oss-20b`, paid | $0.075 / $0.30 | $0.0525 | **$0.840** | Lower paid Groq price; check actual account throughput. [Model list/prices](https://console.groq.com/docs/models) |
| Groq GPT-OSS 120B/20B, free | $0 within quota | $0 cash if admissible | Not a practical promise at this workload | Public limits include 8K tokens/minute and 200K/day; large contexts may be rejected. [Limits](https://console.groq.com/docs/rate-limits) |
| DeepSeek `deepseek-flash` | $0.15 / $0.60 off-peak; $0.30 / $1.20 peak | $0.1050-$0.2100 | **$1.680-$3.360** | Current alias maps to V4.1-Flash; mutable routing and timing affect reproducibility/cost. [Pricing](https://api-docs.deepseek.com/quick_start/pricing/) |
| DeepSeek `deepseek-v4-pro` | $0.66 / $1.98 off-peak; $1.32 / $3.96 peak | $0.4290-$0.8580 | **$6.864-$13.728** | Higher cost; current page identifies V4-Pro-0813. Candidate only before freeze, with its own shared budget feasibility check. [Pricing](https://api-docs.deepseek.com/quick_start/pricing/) |
| Existing local open-weight model | No API token price | Measure power/compute/time | No reliable estimate before profiling | Exact weight/tokenizer/quantization/server pins improve control; hardware and coding quality still matter. |

The dollar rows are **arithmetic scenarios, not predictions, quotes, or measured run costs**. Comparing providers at a normalized workload does not authorize changing provider between baseline and custom. A cheap token price does not establish coding competence. The 20B/120B DeepInfra example differs by only $0.08 over 16 normalized episodes, so transport reliability and development behavior can matter more than that price difference.

DeepSeek's current pricing page shows legacy alias remapping and peak/off-peak billing. Use peak rates for conservative budgeting and capture the resolved identity; do not copy old `deepseek-chat` or V3 prices from another project.

### Free-tier feasibility

The example comparison consumes 8M input + 0.8M output = **8.8M uncached tokens**. At a nominal 200K/day, that is **44 daily allowances**, before other account use. Cached-token treatment can change the actual quota use. An 8K-per-minute allowance can also block an individual long request; merely waiting does not guarantee it becomes admissible. [Groq quota definitions](https://console.groq.com/docs/rate-limits)

Use free access for short synthetic integration checks if it fits. Do not damage the primary comparison by truncating only the reference's context or moving just one arm to paid service. No recurring free allowance is assumed for the paid DeepInfra/DeepSeek rows. No consumer chat subscription is treated as an API budget.

### Selection gate

On synthetic/disjoint development bugs, check actual bash tool calls, observations, multi-turn continuity, decoding support, total output accounting, latency, retry behavior, and end-to-end patch extraction. Use the same test for shortlisted candidates. Select one route based on those checks before primary evaluation; do not run a large model competition on the employer's fixed tasks.

For the first candidate, the documented endpoint is `https://api.deepinfra.com/v1/openai/chat/completions` and raw model name is `openai/gpt-oss-120b`. The stock transport's provider-qualified name and base-URL behavior must be verified against the locked LiteLLM version. Do not confuse a LiteLLM routing prefix with the raw provider model ID. [Endpoint documentation](https://deepinfra.com/openai/gpt-oss-120b/api)

Hosted labels may be mutable. Record provider metadata, available fingerprints, request/response model IDs, and execution timestamps. If a stable version or seed is unavailable, disclose that limitation explicitly instead of inventing a snapshot ID.

## 4. Budget policy and worked calculation

For I billed input tokens and O billed output tokens, with per-million prices p_i and p_o:

```text
episode_cost = I * p_i / 1,000,000 + O * p_o / 1,000,000
comparison_cost = sum(actual episode costs for both arms and all attempts)
total_cash = API + compute + retained disk + transfer + applicable fees
```

Example first-candidate calculation: `0.5 * 0.037 + 0.05 * 0.17 = $0.027` per episode; `16 * 0.027 = $0.432`. Development calls, retries, additional repetitions, failed requests that are billed, and evaluation compute are extra.

The proposed common native threshold is **$0.50/episode**, or **$8 nominal across 16 primary episodes**. This is intentionally separate from the workload estimate. mini-swe-agent checks accumulated cost before the next call, so a call can cross the threshold; its inspected source documents this behavior. Retry billing can complicate the bound. Account controls and an external supervisor provide additional protection, but this plan does not claim a hard $8 maximum. [Pinned reference budget logic](https://github.com/SWE-agent/mini-swe-agent/blob/a83fcae82d2a08f0ee0c688f9d137b3566c097f8/src/minisweagent/agents/default.py)

Record nominal limits, actual billed/estimated usage, unknown charges, peak/off-peak rates if relevant, and overshoot. Keep cost tracking enabled and register current prices through supported configuration when the stock registry is stale. Reconcile provider usage and the report. Do not introduce a paid fallback, automatic top-up, extra model, or invisible retry loop.

A VM estimate is `active hours * hourly compute price + provisioned disk-hours + transfer`. Obtain the real region/spec quotation before provisioning. For illustration only, ten compute-hours at a hypothetical $0.10/hour equals $1 before storage and transfer; this is not a vendor price. Hardware fit takes priority over the cheapest unsuitable machine.

## 5. Future setup sequence

### A. Confirm prerequisites

Inspect host architecture, Docker availability, disk, memory, and task-image compatibility. The baseline is one task at a time. Prepare task dependencies before the episode clock starts, identically for both arms. Keep historical task Python environments intact.

The repository currently contains only Markdown. First implement the package and freeze its dependencies; do not present `uv sync` as a working setup for this revision. Resolve a supported Python 3.12 patch and exact compatible uv/LiteLLM/mini/SWE-bench versions. Pin Git dependencies by full commit, not a moving branch. Inspect source licenses before copying code.

Future clean-checkout steps, **after implementation**:

```sh
git clone https://github.com/itanium-g/smartm2m-swe-agent.git
cd smartm2m-swe-agent
uv sync --frozen
uv run --frozen smartm2m preflight --config configs/experiment.lock.yaml
```

Preflight validates the full task list, model configuration, dependency/prompt/image hashes, writable artifact path, resource fit, and generation/evaluation isolation. Default preflight should be read-only/offline where possible; a live provider probe must be explicit and its usage recorded.

### B. Configure secrets and experiment settings

Keep keys only in local secret storage/environment and outside task containers, logs, and Git. A future ignored local environment file may be used; commit a key-free example only during implementation. The provider endpoint is configurable on the supervisor and cannot be changed by task text.

| Planned setting | Purpose |
|---|---|
| `LLM_API_KEY` | Supervisor-only secret, mapped to the selected stock transport. |
| `LLM_BASE_URL` | Explicit provider endpoint/base URL; validate actual transport conventions. |
| `LLM_MODEL` | Raw/provider-qualified identifiers stored separately in the effective config. |
| `configs/experiment.lock.yaml` | Source of truth for seeds, decoding, budgets, task manifest, versions, and digests. |
| Output root/run ID | Fresh artifact identity; never mounted into task sandboxes. |

CLI/env overrides must either match the frozen config or create a new recorded experiment identity. Unknown/missing configuration is an error. A file named `experiment.lock.yaml` is not proof of pinning: its fields must be concrete and validated.

### C. Establish the reference path

Read the pinned reference's batch CLI help after installation. Current documentation uses `mini-extra swebench` for prediction generation; generation and official scoring are distinct steps. The wrapper must pass the exact ID allowlist, not an approximate slice or regex that accidentally matches extra tasks. Assert prediction IDs against the manifest before scoring.

Preserve shipped prompts/templates and record only permitted configuration overrides. Set effective resource/decoding/budget values equally. Verify that cost registration and retry behavior work before a long run. Never silence billing errors just to get a baseline to start.

### D. Implement and verify the local checks

Planned commands, unavailable today:

```sh
uv run --frozen ruff check .
uv run --frozen pytest
uv run --frozen smartm2m reproduce --config configs/experiment.lock.yaml
```

Ordinary unit/integration tests use synthetic fixtures and do not call a paid model. The reproduction command is an explicit live operation and must print the selected manifest/model/budget before starting without changing the frozen experiment. It runs both arms and official evaluation, then produces the full evidence bundle.

### E. Score and audit

Integrate the pinned official harness, validating its CLI arguments during implementation. Upstream documentation demonstrates the `python -m swebench.harness.run_evaluation` entry point with dataset, predictions, worker count, and run ID. Add exact instance selection and immutable dataset handling in the wrapper. The local loaded dataset used by the evaluator must match the frozen revision; a cached floating `main` load is unacceptable. [Evaluation guide](https://www.swebench.com/SWE-bench/guides/evaluation/)

Future interfaces, **not currently implemented**:

```sh
uv run --frozen smartm2m evaluate --artifacts results/<run-id>
uv run --frozen smartm2m audit --artifacts results/<run-id>
```

`evaluate` executes official tests on sealed patches without inference. `audit` recomputes tables from saved reports without a model key or Docker. Give every evaluation invocation a cache-safe unique run ID. Preserve the original reports even when a rerun differs.

### F. Package and clean up

Commit compact redacted evidence and reports; package large logs as a durable checksum-addressed release archive if necessary. Export artifacts before stopping/removing task-owned containers or cloud resources. Avoid global Docker pruning on a shared machine. Confirm that saved report hashes, patches, and published tables agree.

The final PDF requirement is a public repository with exact tested instructions, full evidence, design, and time/scope summary. Keep the [submission checklist](docs/submission-checklist.md) authoritative for readiness; a plan or an offline report audit does not count as a completed benchmark run.
