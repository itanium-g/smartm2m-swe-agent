"""Provider abstraction and robust multi-turn tool calling transport."""

from __future__ import annotations

import abc
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


def _redact_secrets(text: str) -> str:
    """Redact any API key or authorization token from text or error messages."""
    replacements = [
        (r"(?i)(authorization\s*:\s*bearer\s+)[^\s]+", r"\1[REDACTED]"),
        (r"(?i)(api[_-]?key\s*[=:]\s*)[^\s\"']+", r"\1[REDACTED]"),
        (r"(?i)(token\s*[=:]\s*)[^\s\"']+", r"\1[REDACTED]"),
        (r"\bgsk_[A-Za-z0-9_]{20,}\b", "[REDACTED]"),
    ]
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text)
    # Also redact actual env key values if present
    for env_var in ("MISTRAL_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY"):
        val = os.environ.get(env_var)
        if val and len(val) >= 8:
            text = text.replace(val, "[REDACTED]")
    return text


class BaseModelProvider(abc.ABC):
    """Abstract base class for LLM model providers."""

    def __init__(self, config: ModelConfig):
        self.config = config
        self.logical_requests = 0
        self.request_attempts = 0

    @abc.abstractmethod
    def get_api_key(self) -> str:
        """Retrieve and validate the provider API key."""

    @abc.abstractmethod
    def build_payload(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        temperature: float,
        seed: int | None,
        max_tokens: int,
    ) -> dict[str, Any]:
        """Construct the provider-specific HTTP request payload."""

    @abc.abstractmethod
    def get_headers(self, api_key: str) -> dict[str, str]:
        """Construct HTTP headers for this provider."""

    def sanitize_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Normalize messages to prevent provider-specific schema rejections."""
        clean: list[dict[str, Any]] = []
        for msg in messages:
            role = msg.get("role")
            entry: dict[str, Any] = {"role": role}
            if "content" in msg:
                entry["content"] = msg["content"]
            if role == "assistant":
                if msg.get("tool_calls"):
                    entry["tool_calls"] = [
                        {
                            "id": tc.get("id", ""),
                            "type": tc.get("type", "function"),
                            "function": {
                                "name": tc.get("function", {}).get("name", ""),
                                "arguments": (
                                    tc.get("function", {}).get("arguments", "{}")
                                    if isinstance(tc.get("function", {}).get("arguments"), str)
                                    else json.dumps(tc.get("function", {}).get("arguments", {}), ensure_ascii=False)
                                ),
                            },
                        }
                        for tc in msg["tool_calls"]
                    ]
                if entry.get("content") is None and not entry.get("tool_calls"):
                    entry["content"] = ""
            elif role == "tool":
                entry["tool_call_id"] = msg.get("tool_call_id", "")
                if "name" in msg:
                    entry["name"] = msg["name"]
                if "content" not in entry:
                    entry["content"] = ""
            clean.append(entry)
        return clean

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
                except json.JSONDecodeError:
                    cleaned = arguments.strip()
                    if cleaned.startswith("```json"):
                        cleaned = cleaned[7:]
                    if cleaned.startswith("```"):
                        cleaned = cleaned[3:]
                    if cleaned.endswith("```"):
                        cleaned = cleaned[:-3]
                    cleaned = cleaned.strip()
                    try:
                        arguments = json.loads(cleaned)
                    except json.JSONDecodeError:
                        arguments = {"__invalid_json_raw__": arguments}
            if not isinstance(arguments, dict):
                arguments = {"__invalid_args_raw__": str(arguments)}
            calls.append(ToolCall(str(raw_call.get("id", f"call-{index}")), str(function.get("name", "")), arguments))
        return ModelResponse(
            content=str(message.get("content") or ""),
            tool_calls=calls,
            finish_reason=choice.get("finish_reason"),
            usage=_usage(payload.get("usage", {}) or {}, self.config),
            raw=payload,
        )

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
        key = self.get_api_key()
        payload = self.build_payload(messages, tools, temperature=temperature, seed=seed, max_tokens=max_tokens)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            _endpoint(self.config.base_url),
            data=body,
            headers=self.get_headers(key),
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
                safe_error = _redact_secrets(raw_error)
                last_error = ModelError(f"provider HTTP {exc.code}: {safe_error[:1000]}")
                allowed_codes = {408, 409, 429, 500, 502, 503, 504}
                if exc.code not in allowed_codes or attempt >= max_attempts:
                    raise last_error from exc
                sleep_seconds = min(2**attempt, 15)
                if exc.headers and exc.headers.get("Retry-After"):
                    try:
                        sleep_seconds = min(float(exc.headers["Retry-After"]), 60.0)
                    except ValueError:
                        pass
                match = re.search(r"try again in ([0-9.]+)s", safe_error)
                if match:
                    try:
                        sleep_seconds = max(sleep_seconds, float(match.group(1)))
                    except ValueError:
                        pass
                time.sleep(sleep_seconds + 1.0)
                continue
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = ModelError(f"provider transport/JSON error: {_redact_secrets(str(exc))}")
                if attempt >= self.config.max_retries:
                    raise last_error from exc
            time.sleep(min(2**attempt, 8))
        raise last_error or ModelError("provider request failed")

    def preflight(self) -> dict[str, Any]:
        """Execute a live multi-turn tool interaction to verify provider compatibility."""
        tools = [{
            "type": "function",
            "function": {
                "name": "calculate_test_sum",
                "description": "Add two integers for provider preflight validation.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "a": {"type": "integer"},
                        "b": {"type": "integer"},
                    },
                    "required": ["a", "b"],
                },
            },
        }]
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": "You are an assistant. When asked to perform arithmetic, you MUST call the calculate_test_sum tool.",
            },
            {
                "role": "user",
                "content": "Compute the sum of 15 and 27 using the calculate_test_sum tool.",
            },
        ]
        # Turn 1: request tool call
        turn1 = self.complete(
            messages,
            tools,
            temperature=self.config.temperature,
            seed=self.config.seed,
            max_tokens=200,
        )
        if not turn1.tool_calls:
            raise ModelError(
                f"provider preflight failed: model did not emit a tool call; returned content: {turn1.content[:200]!r}"
            )
        first_call = turn1.tool_calls[0]
        if first_call.name != "calculate_test_sum":
            raise ModelError(
                f"provider preflight failed: model called unexpected tool: {first_call.name}"
            )

        # Turn 2: send tool result and request final assistant response
        messages.append({
            "role": "assistant",
            "content": turn1.content or None,
            "tool_calls": [
                {
                    "id": first_call.id,
                    "type": "function",
                    "function": {"name": first_call.name, "arguments": json.dumps(first_call.arguments)},
                }
            ],
        })
        messages.append({
            "role": "tool",
            "tool_call_id": first_call.id,
            "name": first_call.name,
            "content": json.dumps({"result": 42}),
        })

        turn2 = self.complete(
            messages,
            tools,
            temperature=self.config.temperature,
            seed=self.config.seed,
            max_tokens=200,
        )
        return {
            "ok": True,
            "provider": self.config.provider,
            "model": self.config.model,
            "turn1_tool": first_call.name,
            "turn2_response": bool(turn2.content),
            "multi_turn_tool_test": "passed",
        }


class MistralProvider(BaseModelProvider):
    """Native Mistral provider implementation (e.g. codestral-2508)."""

    def get_api_key(self) -> str:
        key = os.environ.get(self.config.api_key_env) or os.environ.get("MISTRAL_API_KEY")
        if not key:
            raise ModelError(f"missing Mistral credential environment variable: {self.config.api_key_env}")
        return key

    def get_headers(self, api_key: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "smartm2m-swe-agent/0.1.0",
        }

    def build_payload(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        temperature: float,
        seed: int | None,
        max_tokens: int,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": self.sanitize_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
            # Prefer sequential tool calls for predictable SWE operations
            payload["parallel_tool_calls"] = False
        # Mistral uses random_seed; sending 'seed' triggers HTTP 422 extra_forbidden!
        if seed is not None:
            payload["random_seed"] = seed
        return payload


class GroqProvider(BaseModelProvider):
    """Groq OpenAI-compatible provider implementation (fallback)."""

    def get_api_key(self) -> str:
        key = os.environ.get(self.config.api_key_env)
        if not key and self.config.api_key_env == "GROQ_API_KEY":
            key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ModelError(f"missing Groq credential environment variable: {self.config.api_key_env}")
        return key

    def get_headers(self, api_key: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "smartm2m-swe-agent/0.1.0",
        }

    def build_payload(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        temperature: float,
        seed: int | None,
        max_tokens: int,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": self.sanitize_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        if seed is not None:
            payload["seed"] = seed
        return payload

    def sanitize_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        clean = super().sanitize_messages(messages)
        # Prevent Groq HTTP 400: remove reasoning and provider_specific_fields from assistant messages
        for msg in clean:
            if msg.get("role") == "assistant":
                msg.pop("reasoning", None)
                msg.pop("provider_specific_fields", None)
        return clean


class OpenAICompatibleProvider(BaseModelProvider):
    """Generic OpenAI-compatible provider."""

    def get_api_key(self) -> str:
        key = os.environ.get(self.config.api_key_env) or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ModelError(f"missing model credential environment variable: {self.config.api_key_env}")
        return key

    def get_headers(self, api_key: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "smartm2m-swe-agent/0.1.0",
        }

    def build_payload(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        temperature: float,
        seed: int | None,
        max_tokens: int,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": self.sanitize_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        if seed is not None:
            payload["seed"] = seed
        return payload


def get_model_provider(config: ModelConfig) -> BaseModelProvider:
    """Factory to instantiate the appropriate provider adapter."""
    provider_name = (config.provider or "").lower()
    base_url = (config.base_url or "").lower()
    if provider_name == "mistral" or "mistral" in base_url or "codestral" in config.model.lower():
        return MistralProvider(config)
    if provider_name == "groq" or "groq" in base_url:
        return GroqProvider(config)
    return OpenAICompatibleProvider(config)


class OpenAICompatibleModel:
    """Delegates to get_model_provider for backwards compatibility."""

    def __init__(self, config: ModelConfig):
        self.provider = get_model_provider(config)
        self.config = config

    @property
    def logical_requests(self) -> int:
        return self.provider.logical_requests

    @logical_requests.setter
    def logical_requests(self, value: int) -> None:
        self.provider.logical_requests = value

    @property
    def request_attempts(self) -> int:
        return self.provider.request_attempts

    @request_attempts.setter
    def request_attempts(self, value: int) -> None:
        self.provider.request_attempts = value

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        temperature: float,
        seed: int | None,
        max_tokens: int,
    ) -> ModelResponse:
        return self.provider.complete(
            messages,
            tools,
            temperature=temperature,
            seed=seed,
            max_tokens=max_tokens,
        )

    def preflight(self) -> dict[str, Any]:
        return self.provider.preflight()


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

    def preflight(self) -> dict[str, Any]:
        return {"ok": True, "provider": "scripted", "model": "scripted"}


def preflight_provider(config: ModelConfig) -> dict[str, Any]:
    """Verify provider connectivity and multi-turn tool calling before benchmarking."""
    provider = get_model_provider(config)
    return provider.preflight()
