import unittest
from uuid import uuid4

from app.settings import AppSettings


class SettingsTest(unittest.TestCase):
    def test_custom_ai_settings_roundtrip(self) -> None:
        settings = AppSettings("JW PubliStudy Tests", "SettingsRoundtrip")
        settings.set_ai_custom_model_path("C:/models/test.gguf")
        settings.set_ai_custom_model_display_name("Test Model")
        settings.set_ai_use_custom_model(True)
        settings.set_ai_custom_runtime_path("C:/runtime/llama-server.exe")
        settings.set_ai_use_custom_runtime(True)

        loaded = AppSettings("JW PubliStudy Tests", "SettingsRoundtrip")
        self.assertEqual(loaded.ai_custom_model_path(), "C:/models/test.gguf")
        self.assertEqual(loaded.ai_custom_model_display_name(), "Test Model")
        self.assertTrue(loaded.ai_use_custom_model())
        self.assertEqual(loaded.ai_custom_runtime_path(), "C:/runtime/llama-server.exe")
        self.assertTrue(loaded.ai_use_custom_runtime())

    def test_ai_startup_timeout_default_and_clamp(self) -> None:
        settings = AppSettings("JW PubliStudy Tests", f"StartupTimeout-{uuid4()}")
        self.assertEqual(settings.ai_startup_timeout_seconds(), 600)

        settings.set_ai_startup_timeout_seconds(30)
        self.assertEqual(settings.ai_startup_timeout_seconds(), 120)

        settings.set_ai_startup_timeout_seconds(9999)
        self.assertEqual(settings.ai_startup_timeout_seconds(), 1800)


if __name__ == "__main__":
    unittest.main()
