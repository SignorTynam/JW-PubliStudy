import unittest
from pathlib import Path

from app.ai.runtime_manager import RuntimeManager
from app.settings import AppSettings


class RuntimeManagerTest(unittest.TestCase):
    def test_find_free_port(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            manager = RuntimeManager(directory)
            port = manager.find_free_port()
            self.assertIsInstance(port, int)
            self.assertGreater(port, 0)

    def test_build_command_localhost_only(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            root = Path(directory)
            manager = RuntimeManager(root)
            command = manager.build_command(root / "model.gguf", 12345, 4096)
            joined = " ".join(command)
            self.assertIn("127.0.0.1", command)
            self.assertNotIn("0.0.0.0", joined)
            self.assertIn("12345", command)
            self.assertIn(str(root / "model.gguf"), command)

    def test_import_runtime_and_find_custom_runtime(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "llama-server.exe"
            source.write_bytes(b"exe")
            settings = AppSettings("JW PubliStudy Tests", "Runtime")
            settings.set_ai_use_custom_runtime(False)
            manager = RuntimeManager(root / "data", settings)
            target = manager.import_runtime_executable(source)
            settings.set_ai_custom_runtime_path(str(target))
            settings.set_ai_use_custom_runtime(True)
            self.assertTrue(target.exists())
            self.assertEqual(manager.find_runtime_executable(), target)


if __name__ == "__main__":
    unittest.main()
