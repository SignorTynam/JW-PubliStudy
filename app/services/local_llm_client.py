from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Callable
from urllib.parse import urlparse, urlsplit, urlunsplit

import requests


class LLMErrorCode(str, Enum):
    CONNECTION_TIMEOUT = "connection_timeout"
    READ_TIMEOUT = "read_timeout"
    CONNECTION_FAILED = "connection_failed"
    CONNECTION_RESET = "connection_reset"
    HTTP_BAD_REQUEST = "http_bad_request"
    CONTEXT_OVERFLOW = "context_overflow"
    SERVER_BUSY = "server_busy"
    SERVER_ERROR = "server_error"
    INVALID_JSON = "invalid_json"
    MISSING_CONTENT = "missing_content"
    EMPTY_CONTENT = "empty_content"
    RUNTIME_STOPPED = "runtime_stopped"
    OUT_OF_MEMORY = "out_of_memory"
    CANCELLED = "cancelled"
    UNKNOWN_ERROR = "unknown_error"


@dataclass(frozen=True)
class LLMErrorDetails:
    code: LLMErrorCode
    technical_message: str
    status_http: int | None = None
    retryable: bool = False
    runtime_alive: bool | None = None
    attempt_number: int = 1
    elapsed_seconds: float = 0.0

    def with_runtime_alive(self, runtime_alive: bool | None) -> "LLMErrorDetails":
        return replace(self, runtime_alive=runtime_alive)


@dataclass(frozen=True)
class LLMConfig:
    endpoint_url: str
    model: str
    temperature: float
    max_tokens: int
    timeout_seconds: int
    connect_timeout_seconds: float = 5.0
    read_timeout_seconds: float | None = None
    stream: bool = False

    def request_timeout(self) -> tuple[float, float]:
        connect = max(1.0, min(15.0, float(self.connect_timeout_seconds)))
        read_value = self.read_timeout_seconds if self.read_timeout_seconds is not None else self.timeout_seconds
        read = max(10.0, min(900.0, float(read_value)))
        return connect, read


@dataclass(frozen=True)
class LLMChatResult:
    content: str
    elapsed_seconds: float
    first_token_seconds: float | None
    output_tokens_estimated: int
    status_http: int


@dataclass(frozen=True)
class LLMHealthResult:
    runtime_alive: bool
    models_available: bool
    health_available: bool
    models_status: int | None = None
    health_status: int | None = None
    technical_message: str = ""


class LLMClientError(Exception):
    """Base exception carrying a structured, user-safe error classification."""

    def __init__(self, details: LLMErrorDetails | str) -> None:
        if isinstance(details, str):
            details = LLMErrorDetails(_legacy_error_code(details), details)
        self.details = details
        super().__init__(details.technical_message)


class LLMConnectionError(LLMClientError):
    """Raised when the local endpoint cannot be reached."""


class LLMResponseError(LLMClientError):
    """Raised when the local endpoint returns an invalid response."""


class LocalLLMClient:
    def __init__(self) -> None:
        self._active_response: requests.Response | None = None
        self._response_lock = threading.Lock()

    def chat(self, messages: list[dict[str, str]], config: LLMConfig) -> str:
        return self.chat_detailed(messages, config).content

    def chat_detailed(
        self,
        messages: list[dict[str, str]],
        config: LLMConfig,
        *,
        cancellation_event: threading.Event | None = None,
        on_token: Callable[[str], None] | None = None,
        attempt_number: int = 1,
    ) -> LLMChatResult:
        if not config.endpoint_url.strip():
            raise LLMConnectionError(
                LLMErrorDetails(LLMErrorCode.CONNECTION_FAILED, "endpoint_not_configured", attempt_number=attempt_number)
            )
        if cancellation_event is not None and cancellation_event.is_set():
            raise self._cancelled_error(attempt_number, 0.0)

        payload = {
            "model": config.model,
            "messages": messages,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "stream": bool(config.stream),
        }
        started = time.monotonic()
        response: requests.Response | None = None
        try:
            response = requests.post(
                config.endpoint_url,
                json=payload,
                timeout=config.request_timeout(),
                stream=bool(config.stream),
            )
            with self._response_lock:
                self._active_response = response
            self._raise_for_status(response, attempt_number, started)
            if config.stream:
                content, first_token = self._read_stream(
                    response,
                    cancellation_event=cancellation_event,
                    on_token=on_token,
                    attempt_number=attempt_number,
                    started=started,
                )
            else:
                content = self._read_json_content(response, attempt_number, started)
                first_token = time.monotonic() - started
                if on_token is not None:
                    on_token(content)
            elapsed = time.monotonic() - started
            return LLMChatResult(
                content=content,
                elapsed_seconds=elapsed,
                first_token_seconds=first_token,
                output_tokens_estimated=max(1, (len(content) + 3) // 4),
                status_http=response.status_code,
            )
        except LLMClientError:
            raise
        except requests.ConnectTimeout as exc:
            raise LLMConnectionError(
                self._error_details(LLMErrorCode.CONNECTION_TIMEOUT, exc, attempt_number, started, retryable=True)
            ) from exc
        except requests.ReadTimeout as exc:
            raise LLMConnectionError(
                self._error_details(LLMErrorCode.READ_TIMEOUT, exc, attempt_number, started, retryable=True)
            ) from exc
        except requests.Timeout as exc:
            raise LLMConnectionError(
                self._error_details(LLMErrorCode.READ_TIMEOUT, exc, attempt_number, started, retryable=True)
            ) from exc
        except requests.ConnectionError as exc:
            message = str(exc).lower()
            code = LLMErrorCode.CONNECTION_RESET if any(term in message for term in ("reset", "aborted", "broken pipe")) else LLMErrorCode.CONNECTION_FAILED
            raise LLMConnectionError(self._error_details(code, exc, attempt_number, started, retryable=True)) from exc
        except requests.RequestException as exc:
            raise LLMConnectionError(
                self._error_details(LLMErrorCode.CONNECTION_FAILED, exc, attempt_number, started, retryable=True)
            ) from exc
        except (OSError, ValueError, TypeError) as exc:
            raise LLMResponseError(
                self._error_details(LLMErrorCode.UNKNOWN_ERROR, exc, attempt_number, started, retryable=False)
            ) from exc
        finally:
            with self._response_lock:
                if self._active_response is response:
                    self._active_response = None
            if response is not None:
                try:
                    response.close()
                except requests.RequestException:
                    pass

    def test_connection(self, config: LLMConfig) -> bool:
        try:
            lightweight = replace(
                config,
                max_tokens=min(config.max_tokens, 4),
                connect_timeout_seconds=min(config.connect_timeout_seconds, 3.0),
                read_timeout_seconds=min(config.read_timeout_seconds or config.timeout_seconds, 30.0),
                stream=False,
            )
            self.chat([{"role": "user", "content": "Reply with OK."}], lightweight)
        except LLMClientError:
            return False
        return True

    def health_check(self, endpoint_url: str, connect_timeout: float = 2.0, read_timeout: float = 4.0) -> LLMHealthResult:
        base_url = _endpoint_base_url(endpoint_url)
        models_status: int | None = None
        health_status: int | None = None
        messages: list[str] = []
        for path in ("/v1/models", "/health"):
            url = base_url + path
            try:
                response = requests.get(url, timeout=(connect_timeout, read_timeout))
                status = int(response.status_code)
                response.close()
                if path == "/v1/models":
                    models_status = status
                else:
                    health_status = status
            except requests.RequestException as exc:
                messages.append(f"{path}:{type(exc).__name__}")
        models_available = models_status is not None and 200 <= models_status < 300
        health_available = health_status is not None and 200 <= health_status < 300
        return LLMHealthResult(
            runtime_alive=models_available or health_available,
            models_available=models_available,
            health_available=health_available,
            models_status=models_status,
            health_status=health_status,
            technical_message=",".join(messages),
        )

    def cancel_active_request(self) -> None:
        with self._response_lock:
            response = self._active_response
        if response is not None:
            try:
                response.close()
            except requests.RequestException:
                pass

    def _read_stream(
        self,
        response: requests.Response,
        *,
        cancellation_event: threading.Event | None,
        on_token: Callable[[str], None] | None,
        attempt_number: int,
        started: float,
    ) -> tuple[str, float | None]:
        parts: list[str] = []
        first_token: float | None = None
        try:
            for raw_line in response.iter_lines(decode_unicode=True):
                if cancellation_event is not None and cancellation_event.is_set():
                    raise self._cancelled_error(attempt_number, time.monotonic() - started)
                line = raw_line.decode("utf-8", errors="replace") if isinstance(raw_line, bytes) else str(raw_line or "")
                event = parse_sse_data_line(line)
                if event is None:
                    continue
                if event == "[DONE]":
                    break
                try:
                    data = json.loads(event)
                except json.JSONDecodeError as exc:
                    raise LLMResponseError(
                        self._error_details(LLMErrorCode.INVALID_JSON, exc, attempt_number, started, retryable=False)
                    ) from exc
                token = _stream_content(data)
                if token:
                    if first_token is None:
                        first_token = time.monotonic() - started
                    parts.append(token)
                    if on_token is not None:
                        on_token(token)
        except LLMClientError:
            raise
        except requests.ReadTimeout as exc:
            raise LLMConnectionError(
                self._error_details(LLMErrorCode.READ_TIMEOUT, exc, attempt_number, started, retryable=True)
            ) from exc
        except requests.ConnectionError as exc:
            raise LLMConnectionError(
                self._error_details(LLMErrorCode.CONNECTION_RESET, exc, attempt_number, started, retryable=True)
            ) from exc
        content = "".join(parts).strip()
        if not content:
            raise LLMResponseError(
                LLMErrorDetails(
                    LLMErrorCode.EMPTY_CONTENT,
                    "empty_stream_content",
                    status_http=response.status_code,
                    attempt_number=attempt_number,
                    elapsed_seconds=time.monotonic() - started,
                )
            )
        return content, first_token

    def _read_json_content(self, response: requests.Response, attempt_number: int, started: float) -> str:
        try:
            data: dict[str, Any] = response.json()
        except ValueError as exc:
            raise LLMResponseError(
                self._error_details(LLMErrorCode.INVALID_JSON, exc, attempt_number, started, retryable=False, status=response.status_code)
            ) from exc
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMResponseError(
                self._error_details(LLMErrorCode.MISSING_CONTENT, exc, attempt_number, started, retryable=False, status=response.status_code)
            ) from exc
        if not isinstance(content, str) or not content.strip():
            raise LLMResponseError(
                LLMErrorDetails(
                    LLMErrorCode.EMPTY_CONTENT,
                    "empty_content",
                    status_http=response.status_code,
                    attempt_number=attempt_number,
                    elapsed_seconds=time.monotonic() - started,
                )
            )
        return content.strip()

    def _raise_for_status(self, response: requests.Response, attempt_number: int, started: float) -> None:
        status = int(response.status_code)
        if 200 <= status < 300:
            return
        body = (response.text or "")[:2000].lower()
        if any(term in body for term in ("out of memory", "failed to allocate", "cannot allocate memory")):
            code = LLMErrorCode.OUT_OF_MEMORY
            retryable = True
        elif status == 400 and any(term in body for term in ("context", "too long", "token limit", "n_ctx")):
            code = LLMErrorCode.CONTEXT_OVERFLOW
            retryable = True
        elif status == 400:
            code = LLMErrorCode.HTTP_BAD_REQUEST
            retryable = False
        elif status in {429, 503}:
            code = LLMErrorCode.SERVER_BUSY
            retryable = True
        elif status in {500, 502, 504}:
            code = LLMErrorCode.SERVER_ERROR
            retryable = True
        else:
            code = LLMErrorCode.SERVER_ERROR if status >= 500 else LLMErrorCode.HTTP_BAD_REQUEST
            retryable = status >= 500
        raise LLMResponseError(
            LLMErrorDetails(
                code,
                f"http_status_{status}",
                status_http=status,
                retryable=retryable,
                attempt_number=attempt_number,
                elapsed_seconds=time.monotonic() - started,
            )
        )

    def _error_details(
        self,
        code: LLMErrorCode,
        exc: BaseException,
        attempt_number: int,
        started: float,
        *,
        retryable: bool,
        status: int | None = None,
    ) -> LLMErrorDetails:
        return LLMErrorDetails(
            code,
            f"{type(exc).__name__}: {exc}",
            status_http=status,
            retryable=retryable,
            attempt_number=attempt_number,
            elapsed_seconds=time.monotonic() - started,
        )

    def _cancelled_error(self, attempt_number: int, elapsed: float) -> LLMClientError:
        return LLMClientError(
            LLMErrorDetails(
                LLMErrorCode.CANCELLED,
                "request_cancelled",
                retryable=False,
                attempt_number=attempt_number,
                elapsed_seconds=elapsed,
            )
        )


def parse_sse_data_line(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or stripped.startswith(":"):
        return None
    if stripped.startswith("data:"):
        return stripped[5:].strip()
    if stripped.startswith("{"):
        return stripped
    return None


def _stream_content(data: dict[str, Any]) -> str:
    try:
        choice = data["choices"][0]
    except (KeyError, IndexError, TypeError):
        return ""
    if isinstance(choice, dict):
        delta = choice.get("delta")
        if isinstance(delta, dict) and isinstance(delta.get("content"), str):
            return delta["content"]
        message = choice.get("message")
        if isinstance(message, dict) and isinstance(message.get("content"), str):
            return message["content"]
        if isinstance(choice.get("text"), str):
            return choice["text"]
    return ""


def _endpoint_base_url(endpoint_url: str) -> str:
    parsed = urlsplit(endpoint_url.strip())
    path = parsed.path.rstrip("/")
    suffix = "/v1/chat/completions"
    if path.endswith(suffix):
        path = path[: -len(suffix)]
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", "")).rstrip("/")


def _legacy_error_code(value: str) -> LLMErrorCode:
    mapping = {
        "timeout": LLMErrorCode.READ_TIMEOUT,
        "connection_failed": LLMErrorCode.CONNECTION_FAILED,
        "invalid_json": LLMErrorCode.INVALID_JSON,
        "missing_content": LLMErrorCode.MISSING_CONTENT,
        "empty_content": LLMErrorCode.EMPTY_CONTENT,
    }
    return mapping.get(value, LLMErrorCode.UNKNOWN_ERROR)


def is_local_endpoint(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    return host in {"localhost", "127.0.0.1", "::1"}
