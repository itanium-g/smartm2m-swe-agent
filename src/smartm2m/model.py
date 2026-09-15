"""OpenAI-compatible transport plus deterministic development models."""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from collections.abc import Iterable
from typing import Any

from .config import ModelConfig, load_env_file
from .protocol import ModelResponse, ToolCall, Usage


class ModelError(RuntimeError):
    """A provider or response-protocol failure."""


def _usage(raw: dict[str, Any], config: ModelConfig) -> Usage:
    prompt = int(raw.get("prompt_tokens", raw.get("input_tokens", 0)) or 0)
    completion = int(raw.get("completion_tokens", raw.get("output_tokens", 0)) or 0)
    total = int(raw.get("total_tokens", prompt + completion) or prompt + completion)
    cost: float | None = None
    if config.input_usd_per_million is not None and config.output_usd_per_million is not None:
        cost = (prompt * config.input_usd_per_million + completion * config.output_usd_per_million) / 1_000_000
    return Usage(prompt, completion, total, cost, raw)


def _endpoint(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return base + "/chat/completions"


class OpenAICompatibleModel:
    """Minimal dependency-free Chat Completions client.

    The request is deliberately explicit: the exact payload is written into
    the trajectory by the caller, while authorization headers are never logged.
    """

    def __init__(self, config: ModelConfig):
        self.config = config
        self.logical_requests = 0
        self.request_attempts = 0

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        temperature: float,
        seed: int | None,
        max_tokens: int,
    ) -> ModelResponse:
        self.logical_requests += 1
        load_env_file()
        key = os.environ.get(self.config.api_key_env)
        if not key and self.config.api_key_env == "GROQ_API_KEY":
            key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ModelError(f"missing model credential environment variable: {self.config.api_key_env}")
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        if seed is not None:
            payload["seed"] = seed
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            _endpoint(self.config.base_url),
            data=body,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "smartm2m-swe-agent/0.1.0",
            },
            method="POST",
        )
        last_error: Exception | None = None
        max_attempts = max(self.config.max_retries, 15) if self.config.provider == "groq" else self.config.max_retries
        for attempt in range(max_attempts + 1):
            self.request_attempts += 1
            try:
                with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                    decoded = json.loads(response.read().decode("utf-8"))
                return self._parse(decoded)
            except urllib.error.HTTPError as exc:
                raw_error = exc.read().decode("utf-8", errors="replace")
                last_error = ModelError(f"provider HTTP {exc.code}: {raw_error[:1000]}")
                allowed_codes = {408, 409, 429, 500, 502, 503, 504}
                if exc.code not in allowed_codes or attempt >= max_attempts:
                    raise last_error from exc
                sleep_seconds = min(2**attempt, 15)
                if exc.headers and exc.headers.get("Retry-After"):
                    try:
                        sleep_seconds = min(float(exc.headers["Retry-After"]), 60.0)
                    except ValueError:
                        pass
                match = re.search(r"try again in ([0-9.]+)s", raw_error)
                if match:
                    try:
                        sleep_seconds = max(sleep_seconds, float(match.group(1)))
                    except ValueError:
                        pass
                time.sleep(sleep_seconds + 1.0)
                continue
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = ModelError(f"provider transport/JSON error: {exc}")
                if attempt >= self.config.max_retries:
                    raise last_error from exc
            time.sleep(min(2**attempt, 8))
        raise last_error or ModelError("provider request failed")

    def _parse(self, payload: dict[str, Any]) -> ModelResponse:
        try:
            choice = payload["choices"][0]
            message = choice.get("message", {})
        except (KeyError, IndexError, TypeError) as exc:
            raise ModelError("provider response has no choices[0].message") from exc
        calls: list[ToolCall] = []
        for index, raw_call in enumerate(message.get("tool_calls", []) or []):
            function = raw_call.get("function", {})
            arguments = function.get("arguments", {})
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError as exc:
                    raise ModelError(f"tool call {index} has invalid JSON arguments") from exc
            if not isinstance(arguments, dict):
                raise ModelError(f"tool call {index} arguments must be an object")
            calls.append(ToolCall(str(raw_call.get("id", f"call-{index}")), str(function.get("name", "")), arguments))
        return ModelResponse(
            content=str(message.get("content") or ""),
            tool_calls=calls,
            finish_reason=choice.get("finish_reason"),
            usage=_usage(payload.get("usage", {}) or {}, self.config),
            raw=payload,
        )


class ScriptedModel:
    """Deterministic model used by tests and the offline smoke run."""

    def __init__(self, responses: Iterable[ModelResponse]):
        self.responses = iter(responses)
        self.calls = 0
        self.logical_requests = 0
        self.request_attempts = 0

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        temperature: float,
        seed: int | None,
        max_tokens: int,
    ) -> ModelResponse:
        del messages, tools, temperature, seed, max_tokens
        self.calls += 1
        self.logical_requests += 1
        self.request_attempts += 1
        try:
            return next(self.responses)
        except StopIteration as exc:
            raise ModelError("scripted model ran out of responses") from exc
