from __future__ import annotations

from pathlib import Path

from app.ai.ai_status import AIStatus
from app.ai.model_catalog import get_model
from app.ai.model_manager import ModelManager
from app.ai.runtime_manager import RuntimeManager
from app.services.local_llm_client import LLMConfig, LLMConnectionError, LocalLLMClient
from app.settings import AppSettings


class AIClient:
    def __init__(self, settings: AppSettings, model_manager: ModelManager, runtime_manager: RuntimeManager) -> None:
        self._settings = settings
        self._model_manager = model_manager
        self._runtime_manager = runtime_manager
        self._http_client = LocalLLMClient()

    def is_ready(self) -> bool:
        if self._settings.ai_mode() == "manual":
            return bool(self._settings.ai_manual_endpoint_url())
        return self._runtime_manager.get_state().status == "ready" and bool(self.get_active_endpoint())

    def get_active_endpoint(self) -> str | None:
        if self._settings.ai_mode() == "manual":
            return self._settings.ai_manual_endpoint_url()
        return self._runtime_manager.get_state().endpoint_url

    def status(self) -> str:
        if self._settings.ai_mode() == "manual":
            return AIStatus.MANUAL_MODE
        if self._settings.ai_use_custom_model() or self._settings.ai_use_custom_runtime():
            if not self._settings.ai_use_custom_model() or not self._model_manager.is_custom_model_ready(self._settings.ai_custom_model_path()):
                return AIStatus.CUSTOM_MODEL_MISSING
            if not self._settings.ai_use_custom_runtime() or not self._runtime_manager.is_runtime_available():
                return AIStatus.CUSTOM_RUNTIME_MISSING
        model = get_model(self._settings.ai_selected_model_id()) or get_model("small")
        if model is None:
            return AIStatus.NOT_CONFIGURED
        if not self._model_manager.is_model_ready(model):
            return AIStatus.MODEL_MISSING
        if not self._runtime_manager.is_runtime_available():
            return AIStatus.RUNTIME_MISSING
        state = self._runtime_manager.get_state()
        if state.status == "ready":
            return AIStatus.READY
        if state.status == "starting":
            return AIStatus.STARTING
        if state.status == "failed":
            return AIStatus.FAILED
        return AIStatus.NOT_CONFIGURED

    def test_connection(self, config: LLMConfig | None = None) -> tuple[bool, str]:
        active_config = self._config(config)
        if active_config is None:
            return False, self.status()
        return (self._http_client.test_connection(active_config), "ok")

    def chat(self, messages: list[dict[str, str]], config: LLMConfig | None = None) -> str:
        active_config = self._config(config)
        if active_config is None:
            raise LLMConnectionError(self.status())
        return self._http_client.chat(messages, active_config)

    def _config(self, fallback: LLMConfig | None = None) -> LLMConfig | None:
        if self._settings.ai_mode() == "manual":
            return LLMConfig(
                endpoint_url=self._settings.ai_manual_endpoint_url(),
                model=self._settings.ai_manual_model_name(),
                temperature=self._settings.ai_temperature(),
                max_tokens=self._settings.ai_max_tokens(),
                timeout_seconds=self._settings.ai_timeout_seconds(),
            )
        endpoint = self.get_active_endpoint()
        if not endpoint:
            return None
        if self._settings.ai_use_custom_model():
            custom_name = self._settings.ai_custom_model_display_name()
            if not custom_name and self._settings.ai_custom_model_path():
                custom_name = Path(self._settings.ai_custom_model_path()).stem
            model_name = custom_name or "custom-local-model"
        else:
            model = get_model(self._settings.ai_selected_model_id()) or get_model("small")
            model_name = model.display_name if model else (fallback.model if fallback else "local-model")
        return LLMConfig(
            endpoint_url=endpoint,
            model=model_name,
            temperature=self._settings.ai_temperature(),
            max_tokens=self._settings.ai_max_tokens(),
            timeout_seconds=self._settings.ai_timeout_seconds(),
        )
