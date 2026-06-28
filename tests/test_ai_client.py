import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.ai.ai_client import AIClient
from app.ai.model_manager import ModelManager
from app.ai.runtime_manager import RuntimeManager, RuntimeState
from app.settings import AppSettings


class AIClientTest(unittest.TestCase):
    def test_auto_custom_model_name(self) -> None:
        with TemporaryDirectory() as directory:
            settings = AppSettings("JW PubliStudy Tests", "AIClientAuto")
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
            settings = AppSettings("JW PubliStudy Tests", "AIClientManual")
            settings.set_ai_mode("manual")
            settings.set_ai_manual_endpoint_url("http://127.0.0.1:9999/v1/chat/completions")
            settings.set_ai_manual_model_name("manual-model")
            client = AIClient(settings, ModelManager(directory), RuntimeManager(directory, settings))
            config = client._config()
            self.assertIsNotNone(config)
            self.assertEqual(config.endpoint_url, "http://127.0.0.1:9999/v1/chat/completions")
            self.assertEqual(config.model, "manual-model")


if __name__ == "__main__":
    unittest.main()
