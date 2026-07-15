from __future__ import annotations

import threading
from dataclasses import replace
from pathlib import Path
from typing import Callable

from app.ai.adaptive_request_planner import AdaptiveRequestPlan, RequestEnvironment
from app.ai.ai_status import AIStatus
from app.ai.hardware_check import get_hardware_info
from app.ai.model_catalog import get_model
from app.ai.model_manager import ModelManager
from app.ai.runtime_catalog import get_runtime_variant
from app.ai.runtime_launch_plan import RuntimeLaunchPlan
from app.ai.runtime_manager import RuntimeManager
from app.services.local_llm_client import (
    LLMChatResult,
    LLMConfig,
    LLMConnectionError,
    LLMErrorCode,
    LLMErrorDetails,
    LLMHealthResult,
    LocalLLMClient,
)
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

    def chat_detailed(
        self,
        messages: list[dict[str, str]],
        config: LLMConfig,
        *,
        cancellation_event: threading.Event | None = None,
        on_token: Callable[[str], None] | None = None,
        attempt_number: int = 1,
    ) -> LLMChatResult:
        return self._http_client.chat_detailed(
            messages,
            config,
            cancellation_event=cancellation_event,
            on_token=on_token,
            attempt_number=attempt_number,
        )

    def request_environment(self) -> RequestEnvironment:
        selected = get_model(self._settings.ai_selected_model_id()) or get_model("small")
        hardware = get_hardware_info(self._model_manager.models_dir().parent)
        if self._settings.ai_use_custom_model():
            model_id = "custom"
            model_name = self._settings.ai_custom_model_display_name() or Path(self._settings.ai_custom_model_path()).stem or "custom-local-model"
        else:
            model_id = selected.id if selected else "local"
            model_name = selected.display_name if selected else "local-model"
        return RequestEnvironment(
            model_id=model_id,
            model_name=model_name,
            context_window=(
                self._settings.ai_selected_context_tokens()
                if self._settings.ai_mode() != "manual"
                else selected.context_tokens if selected else 4096
            ),
            default_output_tokens=selected.default_max_tokens if selected else 600,
            total_ram_gb=hardware.total_ram_gb,
            available_ram_gb=hardware.available_ram_gb,
            first_request=False,
        )

    def build_request_config(self, plan: AdaptiveRequestPlan) -> LLMConfig:
        active = self._config()
        if active is None:
            raise LLMConnectionError(
                LLMErrorDetails(
                    LLMErrorCode.RUNTIME_STOPPED,
                    "endpoint_not_configured",
                    retryable=True,
                )
            )
        if self._settings.ai_mode() == "manual":
            return replace(
                active,
                connect_timeout_seconds=min(5.0, float(active.connect_timeout_seconds)),
                read_timeout_seconds=float(active.timeout_seconds),
                stream=False,
            )
        return replace(
            active,
            max_tokens=plan.max_tokens,
            timeout_seconds=max(10, int(plan.read_timeout_seconds)),
            connect_timeout_seconds=plan.connect_timeout_seconds,
            read_timeout_seconds=plan.read_timeout_seconds,
            stream=True,
        )

    def check_health(self) -> LLMHealthResult:
        endpoint = self.get_active_endpoint()
        if not endpoint:
            return LLMHealthResult(False, False, False, technical_message="endpoint_not_configured")
        result = self._http_client.health_check(endpoint)
        if self._settings.ai_mode() == "manual":
            return result
        state = self._runtime_manager.get_state()
        return replace(result, runtime_alive=bool(state.process_running or result.runtime_alive))

    def cancel_active_request(self) -> None:
        self._http_client.cancel_active_request()

    def restart_runtime(self, *, cancellation_event: threading.Event | None = None) -> bool:
        if self._settings.ai_mode() == "manual":
            return False
        selected = get_model(self._settings.ai_selected_model_id()) or get_model("small")
        if self._settings.ai_use_custom_model():
            model_path = Path(self._settings.ai_custom_model_path())
            context_tokens = self._settings.ai_selected_context_tokens()
        elif selected is not None:
            model_path = self._model_manager.get_model_path(selected)
            context_tokens = self._settings.ai_selected_context_tokens()
        else:
            return False
        if not self._settings.ai_backend_id():
            state = self._runtime_manager.restart(
                model_path,
                context_tokens,
                self._settings.ai_startup_timeout_seconds(),
                cancellation_event=cancellation_event,
            )
            return self._handle_restart_state(state, cancellation_event)
        executable = self._runtime_manager.find_runtime_executable()
        if executable is None:
            return False
        arguments: list[str] = ["--threads", str(self._settings.ai_selected_cpu_threads())]
        gpu_layers = self._settings.ai_selected_gpu_layers()
        if gpu_layers is not None:
            arguments.extend(("--n-gpu-layers", str(gpu_layers)))
        device_id = self._settings.ai_device_id() or None
        if device_id:
            arguments.extend(("--device", device_id))
        variant = get_runtime_variant(self._settings.ai_runtime_variant_id())
        plan = RuntimeLaunchPlan(
            backend_id=self._settings.ai_backend_id() or "llama_cpp_cpu",
            runtime_variant_id=self._settings.ai_runtime_variant_id() or "legacy",
            executable=executable,
            model_path=model_path,
            host="127.0.0.1",
            port=self._runtime_manager.find_free_port(),
            context_tokens=context_tokens,
            device_id=device_id,
            arguments=tuple(arguments),
            environment={},
            working_directory=executable.parent,
            requires_emulation=self._settings.ai_running_under_emulation(),
            cpu_threads=self._settings.ai_selected_cpu_threads(),
            gpu_layers=gpu_layers,
            host_architecture=self._settings.ai_native_architecture(),
            executable_architecture=variant.architecture if variant else "unknown",
            selection_reasons=("persisted_validated_selection",),
        )
        state = self._runtime_manager.restart_launch_plan(
            plan,
            self._settings.ai_startup_timeout_seconds(),
            cancellation_event=cancellation_event,
        )
        return self._handle_restart_state(state, cancellation_event)

    def _handle_restart_state(self, state, cancellation_event: threading.Event | None) -> bool:
        if cancellation_event is not None and cancellation_event.is_set():
            return False
        if state.status == "ready" and state.endpoint_url:
            self._settings.set_ai_runtime_endpoint(state.endpoint_url)
            self._settings.set_ai_last_status("ready")
            return True
        self._settings.set_ai_last_status("failed")
        return False

    def record_request_event(self, message: str) -> None:
        self._runtime_manager.record_event("chat_request", message)

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
