import unittest
import subprocess
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.ai.runtime_manager import RuntimeManager, parse_runtime_loading_progress
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

    def test_start_uses_explicit_timeout_and_captures_logs(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "runtime" / "llama-server.exe"
            runtime.parent.mkdir(parents=True)
            runtime.write_bytes(b"x" * 2048)
            manager = RuntimeManager(root)
            captured = {}

            def fake_wait(endpoint_base_url, timeout_seconds=None):
                captured["timeout"] = timeout_seconds
                return True

            process = MagicMock()
            process.poll.return_value = None
            process.stdout = None
            process.stderr = None
            with patch.object(manager, "wait_until_ready", side_effect=fake_wait), patch("subprocess.Popen", return_value=process) as popen:
                state = manager.start(root / "model.gguf", 4096, timeout_seconds=777)

            self.assertEqual(state.status, "ready")
            self.assertEqual(captured["timeout"], 777)
            self.assertNotEqual(popen.call_args.kwargs["stdout"], subprocess.DEVNULL)
            self.assertNotEqual(popen.call_args.kwargs["stderr"], subprocess.DEVNULL)

    def test_start_uses_settings_timeout_when_none(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "runtime" / "llama-server.exe"
            runtime.parent.mkdir(parents=True)
            runtime.write_bytes(b"x" * 2048)
            settings = AppSettings("JW PubliStudy Tests", "RuntimeTimeoutSettings")
            settings.set_ai_startup_timeout_seconds(900)
            manager = RuntimeManager(root, settings)
            captured = {}

            def fake_wait(endpoint_base_url, timeout_seconds=None):
                captured["timeout"] = timeout_seconds
                return True

            process = MagicMock()
            process.poll.return_value = None
            process.stdout = None
            process.stderr = None
            with patch.object(manager, "wait_until_ready", side_effect=fake_wait), patch("subprocess.Popen", return_value=process):
                manager.start(root / "model.gguf", 4096)

            self.assertEqual(captured["timeout"], 900)

    def test_parse_runtime_loading_progress(self) -> None:
        self.assertEqual(parse_runtime_loading_progress("loaded 50/100 tensors"), 50)
        self.assertIsNone(parse_runtime_loading_progress("loading model"))
        self.assertIsNone(parse_runtime_loading_progress(""))


if __name__ == "__main__":
    unittest.main()
