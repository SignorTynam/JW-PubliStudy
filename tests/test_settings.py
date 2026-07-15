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

    def test_hardware_selection_settings_roundtrip(self) -> None:
        settings = AppSettings("JW PubliStudy Tests", f"HardwareSelection-{uuid4()}")
        settings.set_ai_optimization_mode("memory_saver")
        settings.save_ai_backend_selection(
            hardware_fingerprint="abc",
            backend_id="llama_cpp_cpu",
            runtime_variant_id="llama_cpp_cpu_arm64",
            device_id=None,
            native_architecture="arm64",
            process_architecture="x86_64",
            running_under_emulation=True,
            context_tokens=2048,
            cpu_threads=6,
            gpu_layers=None,
        )
        self.assertEqual(settings.ai_optimization_mode(), "memory_saver")
        self.assertEqual(settings.ai_hardware_fingerprint(), "abc")
        self.assertEqual(settings.ai_runtime_variant_id(), "llama_cpp_cpu_arm64")
        self.assertTrue(settings.ai_running_under_emulation())
        self.assertEqual(settings.ai_selected_context_tokens(), 2048)
        self.assertEqual(settings.ai_selected_cpu_threads(), 6)
        self.assertIsNone(settings.ai_selected_gpu_layers())


if __name__ == "__main__":
    unittest.main()
