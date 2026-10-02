# Exploratory External Coding-Agent Benchmark: Codex CLI vs Antigravity CLI

> [!NOTE]
> This exploratory benchmark evaluates OpenAI Codex CLI and Google Antigravity CLI (`agy`) as complete coding-agent harnesses on the same frozen eight-task SWE-bench Verified sample under identical workspace, time, and evaluation conditions. Because each CLI incorporates its own system prompts, tool designs, context handling, and model routing, this is not an apples-to-apples single-model comparison.

## Overall Results

- **Codex CLI (`gpt-6.1-sol`):** **8/8 resolved (100.0%)**
- **Antigravity CLI (`gemini-3.8-flash-high`):** **8/8 resolved (100.0%)**

## Paired Outcomes

| Both solved | Codex only | AGY only | Neither verified |
|---:|---:|---:|---:|
| 8 | 0 | 0 | 0 |

## Task-Level Verification

| Instance | Codex Status | Codex Resolved | AGY Status | AGY Resolved | Notes |
|---|---|---:|---|---:|---|
| sphinx-doc__sphinx-8551 | generated | yes | generated | yes |  |
| django__django-11999 | generated | yes | generated | yes |  |
| django__django-11815 | generated | yes | generated | yes |  |
| django__django-12304 | generated | yes | generated | yes |  |
| django__django-12273 | generated | yes | generated | yes |  |
| django__django-12262 | generated | yes | generated | yes |  |
| django__django-12039 | generated | yes | generated | yes |  |
| django__django-11964 | generated | yes | generated | yes |  |
