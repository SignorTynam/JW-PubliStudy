from __future__ import annotations

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
        model = get_model(self._settings.ai_selected_model_id()) or get_model("small")
        return LLMConfig(
            endpoint_url=endpoint,
            model=model.display_name if model else (fallback.model if fallback else "local-model"),
            temperature=self._settings.ai_temperature(),
            max_tokens=self._settings.ai_max_tokens(),
            timeout_seconds=self._settings.ai_timeout_seconds(),
        )
