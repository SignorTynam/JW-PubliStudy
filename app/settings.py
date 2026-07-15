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
    AI_MODE_KEY = "ai/mode"
    AI_SELECTED_MODEL_ID_KEY = "ai/selected_model_id"
    AI_MODEL_PATH_KEY = "ai/model_path"
    AI_RUNTIME_PATH_KEY = "ai/runtime_path"
    AI_RUNTIME_ENDPOINT_KEY = "ai/runtime_endpoint"
    AI_LAST_STATUS_KEY = "ai/last_status"
    AI_MANUAL_ENDPOINT_URL_KEY = "ai/manual_endpoint_url"
    AI_MANUAL_MODEL_NAME_KEY = "ai/manual_model_name"
    AI_CUSTOM_MODEL_PATH_KEY = "ai/custom_model_path"
    AI_CUSTOM_MODEL_DISPLAY_NAME_KEY = "ai/custom_model_display_name"
    AI_USE_CUSTOM_MODEL_KEY = "ai/use_custom_model"
    AI_CUSTOM_RUNTIME_PATH_KEY = "ai/custom_runtime_path"
    AI_USE_CUSTOM_RUNTIME_KEY = "ai/use_custom_runtime"
    AI_STARTUP_TIMEOUT_SECONDS_KEY = "ai/startup_timeout_seconds"
    AI_HARDWARE_FINGERPRINT_KEY = "ai/hardware_fingerprint"
    AI_OPTIMIZATION_MODE_KEY = "ai/optimization_mode"
    AI_BACKEND_ID_KEY = "ai/backend_id"
    AI_RUNTIME_VARIANT_ID_KEY = "ai/runtime_variant_id"
    AI_DEVICE_ID_KEY = "ai/device_id"
    AI_NATIVE_ARCHITECTURE_KEY = "ai/native_architecture"
    AI_PROCESS_ARCHITECTURE_KEY = "ai/process_architecture"
    AI_RUNNING_UNDER_EMULATION_KEY = "ai/running_under_emulation"
    AI_SELECTED_CONTEXT_TOKENS_KEY = "ai/selected_context_tokens"
    AI_SELECTED_CPU_THREADS_KEY = "ai/selected_cpu_threads"
    AI_SELECTED_GPU_LAYERS_KEY = "ai/selected_gpu_layers"
    AI_BACKEND_SELECTION_VERSION_KEY = "ai/backend_selection_version"
    AI_LAST_BACKEND_FAILURE_KEY = "ai/last_backend_failure"
    AI_EXPERIMENTAL_BACKENDS_ENABLED_KEY = "ai/experimental_backends_enabled"

    DEFAULT_LLM_ENDPOINT_URL = "http://localhost:1234/v1/chat/completions"
    DEFAULT_LLM_MODEL = "local-model"
    DEFAULT_LLM_TEMPERATURE = 0.2
    DEFAULT_LLM_MAX_TOKENS = 800
    DEFAULT_LLM_TIMEOUT_SECONDS = 120
    DEFAULT_RETRIEVAL_LIMIT = 6
    DEFAULT_AI_MODE = "auto"
    DEFAULT_AI_SELECTED_MODEL_ID = "small"
    DEFAULT_AI_STARTUP_TIMEOUT_SECONDS = 600
    DEFAULT_AI_OPTIMIZATION_MODE = "automatic"
    DEFAULT_AI_SELECTED_CONTEXT_TOKENS = 4096
    BACKEND_SELECTION_VERSION = 1

    def __init__(self, organization: str = "JW PubliStudy", application: str = "JW PubliStudy") -> None:
        self._settings = QSettings(organization, application)

    def language(self) -> str:
        language = self._settings.value(self.LANGUAGE_KEY, I18n.FALLBACK_LANGUAGE, str)
        return language if language in I18n.SUPPORTED_LANGUAGES else I18n.FALLBACK_LANGUAGE

    def set_language(self, language: str) -> None:
        if language in I18n.SUPPORTED_LANGUAGES:
            self._settings.setValue(self.LANGUAGE_KEY, language)
            self._settings.sync()

    def llm_endpoint_url(self) -> str:
        return self.ai_manual_endpoint_url()

    def set_llm_endpoint_url(self, value: str) -> None:
        self.set_ai_manual_endpoint_url(value)

    def llm_model(self) -> str:
        return self.ai_manual_model_name()

    def set_llm_model(self, value: str) -> None:
        self.set_ai_manual_model_name(value)

    def llm_temperature(self) -> float:
        return self.ai_temperature()

    def set_llm_temperature(self, value: float) -> None:
        self.set_ai_temperature(value)

    def llm_max_tokens(self) -> int:
        return self.ai_max_tokens()

    def set_llm_max_tokens(self, value: int) -> None:
        self.set_ai_max_tokens(value)

    def llm_timeout_seconds(self) -> int:
        return self.ai_timeout_seconds()

    def set_llm_timeout_seconds(self, value: int) -> None:
        self.set_ai_timeout_seconds(value)

    def retrieval_limit(self) -> int:
        return self.ai_default_sources_count()

    def set_retrieval_limit(self, value: int) -> None:
        self.set_ai_default_sources_count(value)

    def llm_config(self) -> LLMConfig:
        return LLMConfig(
            endpoint_url=self.llm_endpoint_url(),
            model=self.llm_model(),
            temperature=self.llm_temperature(),
            max_tokens=self.llm_max_tokens(),
            timeout_seconds=self.llm_timeout_seconds(),
        )

    def reset_llm_defaults(self) -> None:
        self.set_ai_mode(self.DEFAULT_AI_MODE)
        self.set_ai_manual_endpoint_url(self.DEFAULT_LLM_ENDPOINT_URL)
        self.set_ai_manual_model_name(self.DEFAULT_LLM_MODEL)
        self.set_ai_temperature(self.DEFAULT_LLM_TEMPERATURE)
        self.set_ai_max_tokens(self.DEFAULT_LLM_MAX_TOKENS)
        self.set_ai_timeout_seconds(self.DEFAULT_LLM_TIMEOUT_SECONDS)
        self.set_ai_default_sources_count(self.DEFAULT_RETRIEVAL_LIMIT)
        self.set_ai_startup_timeout_seconds(self.DEFAULT_AI_STARTUP_TIMEOUT_SECONDS)
        self.set_ai_optimization_mode(self.DEFAULT_AI_OPTIMIZATION_MODE)

    def ai_mode(self) -> str:
        value = self._settings.value(self.AI_MODE_KEY, self.DEFAULT_AI_MODE, str)
        return value if value in {"auto", "manual"} else self.DEFAULT_AI_MODE

    def set_ai_mode(self, value: str) -> None:
        self._settings.setValue(self.AI_MODE_KEY, value if value in {"auto", "manual"} else self.DEFAULT_AI_MODE)
        self._settings.sync()

    def ai_selected_model_id(self) -> str:
        value = self._settings.value(self.AI_SELECTED_MODEL_ID_KEY, self.DEFAULT_AI_SELECTED_MODEL_ID, str)
        return value.strip() if isinstance(value, str) and value.strip() else self.DEFAULT_AI_SELECTED_MODEL_ID

    def set_ai_selected_model_id(self, value: str) -> None:
        self._settings.setValue(self.AI_SELECTED_MODEL_ID_KEY, value.strip() or self.DEFAULT_AI_SELECTED_MODEL_ID)
        self._settings.sync()

    def ai_model_path(self) -> str:
        return self._string_value(self.AI_MODEL_PATH_KEY, "")

    def set_ai_model_path(self, value: str) -> None:
        self._settings.setValue(self.AI_MODEL_PATH_KEY, value.strip())
        self._settings.sync()

    def ai_runtime_path(self) -> str:
        return self._string_value(self.AI_RUNTIME_PATH_KEY, "")

    def set_ai_runtime_path(self, value: str) -> None:
        self._settings.setValue(self.AI_RUNTIME_PATH_KEY, value.strip())
        self._settings.sync()

    def ai_runtime_endpoint(self) -> str:
        return self._string_value(self.AI_RUNTIME_ENDPOINT_KEY, "")

    def set_ai_runtime_endpoint(self, value: str) -> None:
        self._settings.setValue(self.AI_RUNTIME_ENDPOINT_KEY, value.strip())
        self._settings.sync()

    def ai_last_status(self) -> str:
        return self._string_value(self.AI_LAST_STATUS_KEY, "not_configured")

    def set_ai_last_status(self, value: str) -> None:
        self._settings.setValue(self.AI_LAST_STATUS_KEY, value.strip() or "not_configured")
        self._settings.sync()

    def ai_manual_endpoint_url(self) -> str:
        value = self._settings.value(self.AI_MANUAL_ENDPOINT_URL_KEY, None, str)
        if not value:
            value = self._settings.value(self.LLM_ENDPOINT_URL_KEY, self.DEFAULT_LLM_ENDPOINT_URL, str)
        return value.strip() if isinstance(value, str) and value.strip() else self.DEFAULT_LLM_ENDPOINT_URL

    def set_ai_manual_endpoint_url(self, value: str) -> None:
        self._settings.setValue(self.AI_MANUAL_ENDPOINT_URL_KEY, value.strip() or self.DEFAULT_LLM_ENDPOINT_URL)
        self._settings.sync()

    def ai_manual_model_name(self) -> str:
        value = self._settings.value(self.AI_MANUAL_MODEL_NAME_KEY, None, str)
        if not value:
            value = self._settings.value(self.LLM_MODEL_KEY, self.DEFAULT_LLM_MODEL, str)
        return value.strip() if isinstance(value, str) and value.strip() else self.DEFAULT_LLM_MODEL

    def set_ai_manual_model_name(self, value: str) -> None:
        self._settings.setValue(self.AI_MANUAL_MODEL_NAME_KEY, value.strip() or self.DEFAULT_LLM_MODEL)
        self._settings.sync()

    def ai_temperature(self) -> float:
        return self._bounded_float(self._settings.value(self.LLM_TEMPERATURE_KEY, self.DEFAULT_LLM_TEMPERATURE), 0.0, 1.0, self.DEFAULT_LLM_TEMPERATURE)

    def set_ai_temperature(self, value: float) -> None:
        self._settings.setValue(self.LLM_TEMPERATURE_KEY, self._clamp_float(value, 0.0, 1.0))
        self._settings.sync()

    def ai_max_tokens(self) -> int:
        return self._bounded_int(self._settings.value(self.LLM_MAX_TOKENS_KEY, self.DEFAULT_LLM_MAX_TOKENS), 128, 4096, self.DEFAULT_LLM_MAX_TOKENS)

    def set_ai_max_tokens(self, value: int) -> None:
        self._settings.setValue(self.LLM_MAX_TOKENS_KEY, self._clamp_int(value, 128, 4096))
        self._settings.sync()

    def ai_timeout_seconds(self) -> int:
        return self._bounded_int(self._settings.value(self.LLM_TIMEOUT_SECONDS_KEY, self.DEFAULT_LLM_TIMEOUT_SECONDS), 10, 300, self.DEFAULT_LLM_TIMEOUT_SECONDS)

    def set_ai_timeout_seconds(self, value: int) -> None:
        self._settings.setValue(self.LLM_TIMEOUT_SECONDS_KEY, self._clamp_int(value, 10, 300))
        self._settings.sync()

    def ai_default_sources_count(self) -> int:
        return self._bounded_int(self._settings.value(self.RETRIEVAL_LIMIT_KEY, self.DEFAULT_RETRIEVAL_LIMIT), 1, 12, self.DEFAULT_RETRIEVAL_LIMIT)

    def set_ai_default_sources_count(self, value: int) -> None:
        self._settings.setValue(self.RETRIEVAL_LIMIT_KEY, self._clamp_int(value, 1, 12))
        self._settings.sync()

    def ai_startup_timeout_seconds(self) -> int:
        return self._bounded_int(
            self._settings.value(self.AI_STARTUP_TIMEOUT_SECONDS_KEY, self.DEFAULT_AI_STARTUP_TIMEOUT_SECONDS),
            120,
            1800,
            self.DEFAULT_AI_STARTUP_TIMEOUT_SECONDS,
        )

    def set_ai_startup_timeout_seconds(self, value: int) -> None:
        self._settings.setValue(self.AI_STARTUP_TIMEOUT_SECONDS_KEY, self._clamp_int(value, 120, 1800))
        self._settings.sync()

    def ai_hardware_fingerprint(self) -> str:
        return self._string_value(self.AI_HARDWARE_FINGERPRINT_KEY, "")

    def set_ai_hardware_fingerprint(self, value: str) -> None:
        self._set_string(self.AI_HARDWARE_FINGERPRINT_KEY, value)

    def ai_optimization_mode(self) -> str:
        value = self._string_value(self.AI_OPTIMIZATION_MODE_KEY, self.DEFAULT_AI_OPTIMIZATION_MODE)
        return value if value in {"automatic", "memory_saver", "performance"} else self.DEFAULT_AI_OPTIMIZATION_MODE

    def set_ai_optimization_mode(self, value: str) -> None:
        normalized = value if value in {"automatic", "memory_saver", "performance"} else self.DEFAULT_AI_OPTIMIZATION_MODE
        self._set_string(self.AI_OPTIMIZATION_MODE_KEY, normalized)

    def ai_backend_id(self) -> str:
        return self._string_value(self.AI_BACKEND_ID_KEY, "")

    def set_ai_backend_id(self, value: str) -> None:
        self._set_string(self.AI_BACKEND_ID_KEY, value)

    def ai_runtime_variant_id(self) -> str:
        return self._string_value(self.AI_RUNTIME_VARIANT_ID_KEY, "")

    def set_ai_runtime_variant_id(self, value: str) -> None:
        self._set_string(self.AI_RUNTIME_VARIANT_ID_KEY, value)

    def ai_device_id(self) -> str:
        return self._string_value(self.AI_DEVICE_ID_KEY, "")

    def set_ai_device_id(self, value: str) -> None:
        self._set_string(self.AI_DEVICE_ID_KEY, value)

    def ai_native_architecture(self) -> str:
        return self._string_value(self.AI_NATIVE_ARCHITECTURE_KEY, "unknown")

    def set_ai_native_architecture(self, value: str) -> None:
        self._set_string(self.AI_NATIVE_ARCHITECTURE_KEY, value)

    def ai_process_architecture(self) -> str:
        return self._string_value(self.AI_PROCESS_ARCHITECTURE_KEY, "unknown")

    def set_ai_process_architecture(self, value: str) -> None:
        self._set_string(self.AI_PROCESS_ARCHITECTURE_KEY, value)

    def ai_running_under_emulation(self) -> bool:
        return self._bool_value(self.AI_RUNNING_UNDER_EMULATION_KEY, False)

    def set_ai_running_under_emulation(self, value: bool) -> None:
        self._set_bool(self.AI_RUNNING_UNDER_EMULATION_KEY, value)

    def ai_selected_context_tokens(self) -> int:
        return self._bounded_int(
            self._settings.value(self.AI_SELECTED_CONTEXT_TOKENS_KEY, self.DEFAULT_AI_SELECTED_CONTEXT_TOKENS),
            512,
            32768,
            self.DEFAULT_AI_SELECTED_CONTEXT_TOKENS,
        )

    def set_ai_selected_context_tokens(self, value: int) -> None:
        self._set_int(self.AI_SELECTED_CONTEXT_TOKENS_KEY, self._clamp_int(value, 512, 32768))

    def ai_selected_cpu_threads(self) -> int:
        return self._bounded_int(self._settings.value(self.AI_SELECTED_CPU_THREADS_KEY, 1), 1, 512, 1)

    def set_ai_selected_cpu_threads(self, value: int) -> None:
        self._set_int(self.AI_SELECTED_CPU_THREADS_KEY, self._clamp_int(value, 1, 512))

    def ai_selected_gpu_layers(self) -> int | None:
        value = self._settings.value(self.AI_SELECTED_GPU_LAYERS_KEY, "")
        if value in {None, ""}:
            return None
        try:
            return max(0, min(999, int(value)))
        except (TypeError, ValueError):
            return None

    def set_ai_selected_gpu_layers(self, value: int | None) -> None:
        self._settings.setValue(self.AI_SELECTED_GPU_LAYERS_KEY, "" if value is None else max(0, min(999, int(value))))
        self._settings.sync()

    def ai_backend_selection_version(self) -> int:
        return self._bounded_int(
            self._settings.value(self.AI_BACKEND_SELECTION_VERSION_KEY, self.BACKEND_SELECTION_VERSION),
            1,
            999,
            self.BACKEND_SELECTION_VERSION,
        )

    def set_ai_backend_selection_version(self, value: int) -> None:
        self._set_int(self.AI_BACKEND_SELECTION_VERSION_KEY, max(1, int(value)))

    def ai_last_backend_failure(self) -> str:
        return self._string_value(self.AI_LAST_BACKEND_FAILURE_KEY, "")

    def set_ai_last_backend_failure(self, value: str) -> None:
        self._set_string(self.AI_LAST_BACKEND_FAILURE_KEY, value)

    def ai_experimental_backends_enabled(self) -> bool:
        return self._bool_value(self.AI_EXPERIMENTAL_BACKENDS_ENABLED_KEY, False)

    def set_ai_experimental_backends_enabled(self, value: bool) -> None:
        self._set_bool(self.AI_EXPERIMENTAL_BACKENDS_ENABLED_KEY, value)

    def save_ai_backend_selection(
        self,
        *,
        hardware_fingerprint: str,
        backend_id: str,
        runtime_variant_id: str,
        device_id: str | None,
        native_architecture: str,
        process_architecture: str,
        running_under_emulation: bool,
        context_tokens: int,
        cpu_threads: int,
        gpu_layers: int | None,
    ) -> None:
        values = {
            self.AI_HARDWARE_FINGERPRINT_KEY: hardware_fingerprint,
            self.AI_BACKEND_ID_KEY: backend_id,
            self.AI_RUNTIME_VARIANT_ID_KEY: runtime_variant_id,
            self.AI_DEVICE_ID_KEY: device_id or "",
            self.AI_NATIVE_ARCHITECTURE_KEY: native_architecture,
            self.AI_PROCESS_ARCHITECTURE_KEY: process_architecture,
            self.AI_RUNNING_UNDER_EMULATION_KEY: bool(running_under_emulation),
            self.AI_SELECTED_CONTEXT_TOKENS_KEY: int(context_tokens),
            self.AI_SELECTED_CPU_THREADS_KEY: int(cpu_threads),
            self.AI_SELECTED_GPU_LAYERS_KEY: "" if gpu_layers is None else int(gpu_layers),
            self.AI_BACKEND_SELECTION_VERSION_KEY: self.BACKEND_SELECTION_VERSION,
            self.AI_LAST_BACKEND_FAILURE_KEY: "",
        }
        for key, value in values.items():
            self._settings.setValue(key, value)
        self._settings.sync()

    def ai_custom_model_path(self) -> str:
        return self._string_value(self.AI_CUSTOM_MODEL_PATH_KEY, "")

    def set_ai_custom_model_path(self, value: str) -> None:
        self._settings.setValue(self.AI_CUSTOM_MODEL_PATH_KEY, value.strip())
        self._settings.sync()

    def ai_custom_model_display_name(self) -> str:
        return self._string_value(self.AI_CUSTOM_MODEL_DISPLAY_NAME_KEY, "")

    def set_ai_custom_model_display_name(self, value: str) -> None:
        self._settings.setValue(self.AI_CUSTOM_MODEL_DISPLAY_NAME_KEY, value.strip())
        self._settings.sync()

    def ai_use_custom_model(self) -> bool:
        return self._bool_value(self.AI_USE_CUSTOM_MODEL_KEY, False)

    def set_ai_use_custom_model(self, value: bool) -> None:
        self._settings.setValue(self.AI_USE_CUSTOM_MODEL_KEY, bool(value))
        self._settings.sync()

    def ai_custom_runtime_path(self) -> str:
        return self._string_value(self.AI_CUSTOM_RUNTIME_PATH_KEY, "")

    def set_ai_custom_runtime_path(self, value: str) -> None:
        self._settings.setValue(self.AI_CUSTOM_RUNTIME_PATH_KEY, value.strip())
        self._settings.sync()

    def ai_use_custom_runtime(self) -> bool:
        return self._bool_value(self.AI_USE_CUSTOM_RUNTIME_KEY, False)

    def set_ai_use_custom_runtime(self, value: bool) -> None:
        self._settings.setValue(self.AI_USE_CUSTOM_RUNTIME_KEY, bool(value))
        self._settings.sync()

    def _string_value(self, key: str, fallback: str) -> str:
        value = self._settings.value(key, fallback, str)
        return value.strip() if isinstance(value, str) else fallback

    def _bool_value(self, key: str, fallback: bool) -> bool:
        value = self._settings.value(key, fallback)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in {"1", "true", "yes", "on"}
        return bool(value)

    def _set_string(self, key: str, value: str) -> None:
        self._settings.setValue(key, str(value).strip())
        self._settings.sync()

    def _set_bool(self, key: str, value: bool) -> None:
        self._settings.setValue(key, bool(value))
        self._settings.sync()

    def _set_int(self, key: str, value: int) -> None:
        self._settings.setValue(key, int(value))
        self._settings.sync()

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
