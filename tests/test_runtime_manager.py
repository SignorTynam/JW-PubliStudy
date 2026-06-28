import unittest
import zipfile
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

    def test_find_latest_windows_asset(self) -> None:
        manager = RuntimeManager(Path("."))
        release = {
            "assets": [
                {"name": "llama-b999-bin-ubuntu-x64.zip", "browser_download_url": "linux"},
                {"name": "llama-b999-bin-win-avx2-x64.zip", "browser_download_url": "avx2"},
                {"name": "llama-b999-bin-win-cpu-x64.zip", "browser_download_url": "cpu"},
            ]
        }
        self.assertEqual(manager.find_latest_windows_asset(release), "cpu")

    def test_find_latest_windows_asset_none(self) -> None:
        manager = RuntimeManager(Path("."))
        self.assertIsNone(manager.find_latest_windows_asset({"assets": [{"name": "source.tar.gz"}]}))

    def test_install_runtime_from_zip(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            root = Path(directory)
            zip_path = root / "runtime.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr("llama/bin/llama-server.exe", b"x" * 2048)
            manager = RuntimeManager(root / "data")
            target = manager.install_runtime_from_zip(zip_path)
            self.assertTrue(target.exists())
            self.assertTrue(manager.is_runtime_ready_file(target))


if __name__ == "__main__":
    unittest.main()
