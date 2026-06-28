from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests


@dataclass(frozen=True)
class LLMConfig:
    endpoint_url: str
    model: str
    temperature: float
    max_tokens: int
    timeout_seconds: int


class LLMClientError(Exception):
    """Base exception for local LLM client errors."""


class LLMConnectionError(LLMClientError):
    """Raised when the local endpoint cannot be reached."""


class LLMResponseError(LLMClientError):
    """Raised when the local endpoint returns an invalid response."""


class LocalLLMClient:
    def chat(self, messages: list[dict[str, str]], config: LLMConfig) -> str:
        if not config.endpoint_url.strip():
            raise LLMConnectionError("endpoint_not_configured")

        payload = {
            "model": config.model,
            "messages": messages,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
        }
        try:
            response = requests.post(
                config.endpoint_url,
                json=payload,
                timeout=config.timeout_seconds,
            )
        except requests.Timeout as exc:
            raise LLMConnectionError("timeout") from exc
        except requests.RequestException as exc:
            raise LLMConnectionError("connection_failed") from exc

        if not 200 <= response.status_code < 300:
            raise LLMResponseError(f"status_{response.status_code}")

        try:
            data: dict[str, Any] = response.json()
        except ValueError as exc:
            raise LLMResponseError("invalid_json") from exc

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMResponseError("missing_content") from exc

        if not isinstance(content, str) or not content.strip():
            raise LLMResponseError("empty_content")
        return content.strip()

    def test_connection(self, config: LLMConfig) -> bool:
        try:
            self.chat(
                [{"role": "user", "content": "Reply with OK."}],
                config,
            )
        except LLMClientError:
            return False
        return True
