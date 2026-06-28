from __future__ import annotations

from PySide6.QtCore import QSettings

from app.i18n import I18n
from app.services.local_llm_client import LLMConfig


class AppSettings:
    """Small wrapper around QSettings for local application preferences."""

    LANGUAGE_KEY = "language"
    LLM_ENDPOINT_URL_KEY = "llm/endpoint_url"
    LLM_MODEL_KEY = "llm/model"
    LLM_TEMPERATURE_KEY = "llm/temperature"
    LLM_MAX_TOKENS_KEY = "llm/max_tokens"
    LLM_TIMEOUT_SECONDS_KEY = "llm/timeout_seconds"
    RETRIEVAL_LIMIT_KEY = "llm/retrieval_limit"

    DEFAULT_LLM_ENDPOINT_URL = "http://localhost:1234/v1/chat/completions"
    DEFAULT_LLM_MODEL = "local-model"
    DEFAULT_LLM_TEMPERATURE = 0.2
    DEFAULT_LLM_MAX_TOKENS = 800
    DEFAULT_LLM_TIMEOUT_SECONDS = 120
    DEFAULT_RETRIEVAL_LIMIT = 6

    def __init__(self) -> None:
        self._settings = QSettings("JW PubliStudy", "JW PubliStudy")

    def language(self) -> str:
        language = self._settings.value(self.LANGUAGE_KEY, I18n.FALLBACK_LANGUAGE, str)
        return language if language in I18n.SUPPORTED_LANGUAGES else I18n.FALLBACK_LANGUAGE

    def set_language(self, language: str) -> None:
        if language in I18n.SUPPORTED_LANGUAGES:
            self._settings.setValue(self.LANGUAGE_KEY, language)
            self._settings.sync()

    def llm_endpoint_url(self) -> str:
        value = self._settings.value(self.LLM_ENDPOINT_URL_KEY, self.DEFAULT_LLM_ENDPOINT_URL, str)
        return value.strip() if isinstance(value, str) and value.strip() else self.DEFAULT_LLM_ENDPOINT_URL

    def set_llm_endpoint_url(self, value: str) -> None:
        self._settings.setValue(self.LLM_ENDPOINT_URL_KEY, value.strip() or self.DEFAULT_LLM_ENDPOINT_URL)
        self._settings.sync()

    def llm_model(self) -> str:
        value = self._settings.value(self.LLM_MODEL_KEY, self.DEFAULT_LLM_MODEL, str)
        return value.strip() if isinstance(value, str) and value.strip() else self.DEFAULT_LLM_MODEL

    def set_llm_model(self, value: str) -> None:
        self._settings.setValue(self.LLM_MODEL_KEY, value.strip() or self.DEFAULT_LLM_MODEL)
        self._settings.sync()

    def llm_temperature(self) -> float:
        return self._bounded_float(self._settings.value(self.LLM_TEMPERATURE_KEY, self.DEFAULT_LLM_TEMPERATURE), 0.0, 1.0, self.DEFAULT_LLM_TEMPERATURE)

    def set_llm_temperature(self, value: float) -> None:
        self._settings.setValue(self.LLM_TEMPERATURE_KEY, self._clamp_float(value, 0.0, 1.0))
        self._settings.sync()

    def llm_max_tokens(self) -> int:
        return self._bounded_int(self._settings.value(self.LLM_MAX_TOKENS_KEY, self.DEFAULT_LLM_MAX_TOKENS), 128, 4096, self.DEFAULT_LLM_MAX_TOKENS)

    def set_llm_max_tokens(self, value: int) -> None:
        self._settings.setValue(self.LLM_MAX_TOKENS_KEY, self._clamp_int(value, 128, 4096))
        self._settings.sync()

    def llm_timeout_seconds(self) -> int:
        return self._bounded_int(self._settings.value(self.LLM_TIMEOUT_SECONDS_KEY, self.DEFAULT_LLM_TIMEOUT_SECONDS), 10, 300, self.DEFAULT_LLM_TIMEOUT_SECONDS)

    def set_llm_timeout_seconds(self, value: int) -> None:
        self._settings.setValue(self.LLM_TIMEOUT_SECONDS_KEY, self._clamp_int(value, 10, 300))
        self._settings.sync()

    def retrieval_limit(self) -> int:
        return self._bounded_int(self._settings.value(self.RETRIEVAL_LIMIT_KEY, self.DEFAULT_RETRIEVAL_LIMIT), 1, 12, self.DEFAULT_RETRIEVAL_LIMIT)

    def set_retrieval_limit(self, value: int) -> None:
        self._settings.setValue(self.RETRIEVAL_LIMIT_KEY, self._clamp_int(value, 1, 12))
        self._settings.sync()

    def llm_config(self) -> LLMConfig:
        return LLMConfig(
            endpoint_url=self.llm_endpoint_url(),
            model=self.llm_model(),
            temperature=self.llm_temperature(),
            max_tokens=self.llm_max_tokens(),
            timeout_seconds=self.llm_timeout_seconds(),
        )

    def reset_llm_defaults(self) -> None:
        self.set_llm_endpoint_url(self.DEFAULT_LLM_ENDPOINT_URL)
        self.set_llm_model(self.DEFAULT_LLM_MODEL)
        self.set_llm_temperature(self.DEFAULT_LLM_TEMPERATURE)
        self.set_llm_max_tokens(self.DEFAULT_LLM_MAX_TOKENS)
        self.set_llm_timeout_seconds(self.DEFAULT_LLM_TIMEOUT_SECONDS)
        self.set_retrieval_limit(self.DEFAULT_RETRIEVAL_LIMIT)

    def _bounded_int(self, value: object, minimum: int, maximum: int, fallback: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return fallback
        return self._clamp_int(parsed, minimum, maximum)

    def _bounded_float(self, value: object, minimum: float, maximum: float, fallback: float) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return fallback
        return self._clamp_float(parsed, minimum, maximum)

    def _clamp_int(self, value: int, minimum: int, maximum: int) -> int:
        return max(minimum, min(maximum, value))

    def _clamp_float(self, value: float, minimum: float, maximum: float) -> float:
        return max(minimum, min(maximum, value))
