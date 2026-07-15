import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from app.ai.ai_client import AIClient
from app.ai.hardware_check import HardwareInfo
from app.ai.model_manager import ModelManager
from app.ai.runtime_manager import RuntimeManager, RuntimeState
from app.services.local_llm_client import LLMClientError, LLMErrorCode, LLMErrorDetails, LLMHealthResult
from app.settings import AppSettings


class AIClientTest(unittest.TestCase):
    def _settings(self, prefix: str) -> AppSettings:
        settings = AppSettings("JW PubliStudy Tests", f"{prefix}-{uuid4().hex}")
        settings._settings.clear()
        return settings

    def test_auto_custom_model_name(self) -> None:
        with TemporaryDirectory() as directory:
            settings = self._settings("AIClientAuto")
            settings.set_ai_mode("auto")
            settings.set_ai_use_custom_model(True)
            settings.set_ai_custom_model_path(str(Path(directory) / "my-model.gguf"))
            settings.set_ai_custom_model_display_name("My Model")
            model_manager = ModelManager(directory)
            runtime_manager = RuntimeManager(directory, settings)
            runtime_manager._state = RuntimeState("ready", "http://127.0.0.1:1234/v1/chat/completions", 1234, True)
            client = AIClient(settings, model_manager, runtime_manager)
            config = client._config()
            self.assertIsNotNone(config)
            self.assertEqual(config.model, "My Model")

    def test_manual_mode_uses_manual_endpoint(self) -> None:
        with TemporaryDirectory() as directory:
            settings = self._settings("AIClientManual")
            settings.set_ai_mode("manual")
            settings.set_ai_manual_endpoint_url("http://127.0.0.1:9999/v1/chat/completions")
            settings.set_ai_manual_model_name("manual-model")
            client = AIClient(settings, ModelManager(directory), RuntimeManager(directory, settings))
            config = client._config()
            self.assertIsNotNone(config)
            self.assertEqual(config.endpoint_url, "http://127.0.0.1:9999/v1/chat/completions")
            self.assertEqual(config.model, "manual-model")

    def test_automatic_request_config_uses_adaptive_limits_and_streaming(self) -> None:
        with TemporaryDirectory() as directory:
            settings = self._settings("AIClientAdaptive")
            settings.set_ai_mode("auto")
            model_manager = ModelManager(directory)
            runtime_manager = RuntimeManager(directory, settings)
            runtime_manager._state = RuntimeState("ready", "http://127.0.0.1:1234/v1/chat/completions", 1234, True)
            client = AIClient(settings, model_manager, runtime_manager)
            plan = SimpleNamespace(max_tokens=444, connect_timeout_seconds=3.0, read_timeout_seconds=87.5)

            config = client.build_request_config(plan)

            self.assertEqual(config.max_tokens, 444)
            self.assertEqual(config.request_timeout(), (3.0, 87.5))
            self.assertTrue(config.stream)

    def test_missing_automatic_endpoint_is_a_structured_runtime_error(self) -> None:
        with TemporaryDirectory() as directory:
            settings = self._settings("AIClientMissingEndpoint")
            settings.set_ai_mode("auto")
            client = AIClient(settings, ModelManager(directory), RuntimeManager(directory, settings))
            plan = SimpleNamespace(max_tokens=300, connect_timeout_seconds=3.0, read_timeout_seconds=60.0)

            with self.assertRaises(LLMClientError) as captured:
                client.build_request_config(plan)

            self.assertEqual(captured.exception.details.code, LLMErrorCode.RUNTIME_STOPPED)
            self.assertTrue(captured.exception.details.retryable)

    def test_manual_request_config_preserves_advanced_values(self) -> None:
        with TemporaryDirectory() as directory:
            settings = self._settings("AIClientManualConfig")
            settings.set_ai_mode("manual")
            settings.set_ai_max_tokens(777)
            settings.set_ai_timeout_seconds(143)
            client = AIClient(settings, ModelManager(directory), RuntimeManager(directory, settings))
            plan = SimpleNamespace(max_tokens=222, connect_timeout_seconds=3.0, read_timeout_seconds=50.0)

            config = client.build_request_config(plan)

            self.assertEqual(config.max_tokens, 777)
            self.assertEqual(config.read_timeout_seconds, 143.0)
            self.assertFalse(config.stream)

    def test_request_environment_uses_model_context_and_available_ram(self) -> None:
        with TemporaryDirectory() as directory:
            settings = self._settings("AIClientEnvironment")
            settings.set_ai_mode("auto")
            client = AIClient(settings, ModelManager(directory), RuntimeManager(directory, settings))
            hardware = HardwareInfo("Windows", "AMD64", 16.0, 100.0, Path(directory), 6.5)

            with patch("app.ai.ai_client.get_hardware_info", return_value=hardware):
                environment = client.request_environment()

            self.assertEqual(environment.context_window, 4096)
            self.assertEqual(environment.default_output_tokens, 800)
            self.assertEqual(environment.total_ram_gb, 16.0)
            self.assertEqual(environment.available_ram_gb, 6.5)

    def test_request_failure_does_not_change_ready_runtime_state(self) -> None:
        with TemporaryDirectory() as directory:
            settings = self._settings("AIClientReadyState")
            settings.set_ai_mode("auto")
            model_manager = ModelManager(directory)
            runtime_manager = RuntimeManager(directory, settings)
            runtime_manager._state = RuntimeState("ready", "http://127.0.0.1:1234/v1/chat/completions", 1234, True)
            model_manager.is_model_ready = lambda _model: True
            runtime_manager.is_runtime_available = lambda: True
            client = AIClient(settings, model_manager, runtime_manager)

            class FailingHTTPClient:
                def chat_detailed(self, *args, **kwargs):
                    raise LLMClientError(LLMErrorDetails(LLMErrorCode.READ_TIMEOUT, "timeout", retryable=True))

            client._http_client = FailingHTTPClient()
            config = client._config()
            with self.assertRaises(LLMClientError):
                client.chat_detailed([], config)

            self.assertEqual(runtime_manager.get_state().status, "ready")
            self.assertEqual(client.status(), "ready")

    def test_health_check_combines_endpoint_probe_with_process_state(self) -> None:
        with TemporaryDirectory() as directory:
            settings = self._settings("AIClientHealth")
            settings.set_ai_mode("auto")
            runtime_manager = RuntimeManager(directory, settings)
            runtime_manager._state = RuntimeState("ready", "http://127.0.0.1:1234/v1/chat/completions", 1234, True)
            client = AIClient(settings, ModelManager(directory), runtime_manager)

            class UnavailableProbe:
                def health_check(self, endpoint):
                    self.endpoint = endpoint
                    return LLMHealthResult(False, False, False, technical_message="offline")

            probe = UnavailableProbe()
            client._http_client = probe
            health = client.check_health()

            self.assertTrue(health.runtime_alive)
            self.assertFalse(health.models_available)
            self.assertEqual(probe.endpoint, "http://127.0.0.1:1234/v1/chat/completions")

    def test_terminated_process_is_reported_as_failed_global_state(self) -> None:
        with TemporaryDirectory() as directory:
            settings = self._settings("AIClientFailedState")
            settings.set_ai_mode("auto")
            model_manager = ModelManager(directory)
            runtime_manager = RuntimeManager(directory, settings)
            model_manager.is_model_ready = lambda _model: True
            runtime_manager.is_runtime_available = lambda: True
            runtime_manager._state = RuntimeState("failed", None, None, False, "process_exited")
            client = AIClient(settings, model_manager, runtime_manager)

            self.assertEqual(client.status(), "failed")
            self.assertFalse(client.is_ready())


if __name__ == "__main__":
    unittest.main()
