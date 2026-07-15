import subprocess
import threading
import unittest
import urllib.error
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from app.ai.runtime_manager import (
    DEFAULT_RUNTIME_SPEC,
    RuntimeManager,
    RuntimeValidationResult,
    parse_runtime_loading_progress,
)
from app.settings import AppSettings


def valid_runtime(path: Path, probe: str = "--version") -> RuntimeValidationResult:
    return RuntimeValidationResult(
        True,
        Path(path).resolve(strict=False),
        probe_argument=probe,
        command=[str(Path(path).resolve(strict=False)), probe],
        working_directory=Path(path).resolve(strict=False).parent,
        stderr="version: test",
        exit_code=0,
        native_exit_code=0,
    )


def invalid_runtime(path: Path, error: str = "runtime_incomplete") -> RuntimeValidationResult:
    return RuntimeValidationResult(
        False,
        Path(path).resolve(strict=False),
        error=error,
        working_directory=Path(path).resolve(strict=False).parent,
    )


class FakeResponse:
    def __init__(self, status: int = 200) -> None:
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def getcode(self) -> int:
        return self.status


class RuntimeManagerTest(unittest.TestCase):
    def _write_runtime_zip(self, zip_path: Path, *, nested: str = "llama/bin") -> None:
        prefix = nested.rstrip("/")
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr(f"{prefix}/llama-server.exe", b"exe")
            archive.writestr(f"{prefix}/ggml.dll", b"ggml")
            archive.writestr(f"{prefix}/llama.dll", b"llama")
            archive.writestr(f"{prefix}/subdirectory/support.file", b"support")
            archive.writestr(f"{prefix}/ignored.part", b"partial")

    def _prepare_start(self, root: Path) -> tuple[RuntimeManager, Path, Path]:
        manager = RuntimeManager(root)
        executable = manager.get_runtime_path()
        executable.parent.mkdir(parents=True, exist_ok=True)
        executable.write_bytes(b"exe")
        (executable.parent / "llama.dll").write_bytes(b"dll")
        model = root / "models" / "model with spaces.gguf"
        model.parent.mkdir(parents=True, exist_ok=True)
        model.write_bytes(b"m" * manager.MIN_PLAUSIBLE_MODEL_BYTES)
        return manager, executable.resolve(), model.resolve()

    def _start_with_mock_process(
        self,
        manager: RuntimeManager,
        executable: Path,
        model: Path,
        process: MagicMock,
        *,
        ready: bool,
    ):
        with (
            patch.object(manager, "find_runtime_executable", return_value=executable),
            patch.object(manager, "validate_runtime_installation", return_value=valid_runtime(executable)),
            patch.object(manager, "validate_runtime_command_flags", return_value=valid_runtime(executable, "--help")),
            patch.object(manager, "wait_until_ready", return_value=ready),
            patch("subprocess.Popen", return_value=process) as popen,
        ):
            state = manager.start(model, 4096, timeout_seconds=777)
        return state, popen

    def test_find_free_port(self) -> None:
        with TemporaryDirectory() as directory:
            manager = RuntimeManager(Path(directory))
            port = manager.find_free_port()
            self.assertIsInstance(port, int)
            self.assertGreater(port, 0)

    def test_build_command_localhost_only_and_no_http_endpoint_argument(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manager = RuntimeManager(root)
            command = manager.build_command(root / "model.gguf", 12345, 4096)
            self.assertEqual(
                command[1:],
                ["--model", str((root / "model.gguf").resolve()), "--host", "127.0.0.1", "--port", "12345", "--ctx-size", "4096"],
            )
            self.assertNotIn("0.0.0.0", command)
            self.assertFalse(any("/v1/chat/completions" in argument for argument in command))

    def test_find_latest_windows_asset_prefers_generic_cpu_and_excludes_gpu(self) -> None:
        manager = RuntimeManager(Path("."))
        release = {
            "assets": [
                {"name": "llama-bin-win-cuda-x64.zip", "browser_download_url": "cuda"},
                {"name": "llama-bin-win-vulkan-x64.zip", "browser_download_url": "vulkan"},
                {"name": "llama-bin-win-avx2-x64.zip", "browser_download_url": "avx2"},
                {"name": "llama-bin-win-cpu-x64.zip", "browser_download_url": "cpu"},
            ]
        }
        with patch.object(manager, "_cpu_supports_avx2", return_value=False):
            self.assertEqual(manager.find_latest_windows_asset(release), "cpu")
        self.assertEqual(manager.last_selected_asset_name(), "llama-bin-win-cpu-x64.zip")

    def test_find_latest_windows_asset_none(self) -> None:
        manager = RuntimeManager(Path("."))
        self.assertIsNone(manager.find_latest_windows_asset({"assets": [{"name": "source.tar.gz"}]}))

    def test_install_runtime_preserves_exe_dlls_subdirectory_and_cleans_temporary_folders(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            zip_path = root / "runtime.zip"
            self._write_runtime_zip(zip_path)
            manager = RuntimeManager(root / "data")
            with patch.object(
                manager,
                "validate_runtime_installation",
                side_effect=lambda path, *args, **kwargs: valid_runtime(Path(path)),
            ):
                target = manager.install_runtime_from_zip(zip_path)
            self.assertEqual(target, manager.get_runtime_path().resolve())
            self.assertTrue(target.is_file())
            self.assertTrue((target.parent / "ggml.dll").is_file())
            self.assertTrue((target.parent / "llama.dll").is_file())
            self.assertTrue((target.parent / "subdirectory" / "support.file").is_file())
            self.assertFalse(any(path.name.endswith(".part") for path in target.parent.rglob("*")))
            self.assertFalse(any(path.name.startswith(("_extracting", "_installing")) for path in manager.managed_runtime_dir().iterdir()))

    def test_install_zip_without_executable_fails(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            zip_path = root / "runtime.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr("llama/bin/llama.dll", b"dll")
            manager = RuntimeManager(root / "data")
            with self.assertRaisesRegex(RuntimeError, "runtime_executable_missing"):
                manager.install_runtime_from_zip(zip_path)

    def test_install_rejects_zip_path_traversal(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            zip_path = root / "runtime.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr("../escaped.dll", b"bad")
                archive.writestr("llama/bin/llama-server.exe", b"exe")
            manager = RuntimeManager(root / "data")
            with self.assertRaisesRegex(RuntimeError, "runtime_zip_unsafe_path"):
                manager.install_runtime_from_zip(zip_path)
            self.assertFalse((manager.managed_runtime_dir() / "escaped.dll").exists())

    def test_install_finds_nested_runtime(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            zip_path = root / "runtime.zip"
            self._write_runtime_zip(zip_path, nested="release/deep/bin")
            manager = RuntimeManager(root / "data")
            with patch.object(
                manager,
                "validate_runtime_installation",
                side_effect=lambda path, *args, **kwargs: valid_runtime(Path(path)),
            ):
                target = manager.install_runtime_from_zip(zip_path)
            self.assertEqual(target.parent.name, "current")
            self.assertTrue((target.parent / "subdirectory" / "support.file").exists())

    def test_previous_installation_is_preserved_when_new_validation_fails(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            zip_path = root / "runtime.zip"
            self._write_runtime_zip(zip_path)
            manager = RuntimeManager(root / "data")
            old_executable = manager.get_runtime_path()
            old_executable.parent.mkdir(parents=True)
            old_executable.write_bytes(b"old executable")
            (old_executable.parent / "old.dll").write_bytes(b"old dll")
            with patch.object(
                manager,
                "validate_runtime_installation",
                side_effect=lambda path, *args, **kwargs: invalid_runtime(Path(path)),
            ):
                with self.assertRaisesRegex(RuntimeError, "runtime_incomplete"):
                    manager.install_runtime_from_zip(zip_path)
            self.assertEqual(old_executable.read_bytes(), b"old executable")
            self.assertEqual((old_executable.parent / "old.dll").read_bytes(), b"old dll")

    def test_previous_installation_is_restored_if_post_swap_validation_fails(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            zip_path = root / "runtime.zip"
            self._write_runtime_zip(zip_path)
            manager = RuntimeManager(root / "data")
            old_executable = manager.get_runtime_path()
            old_executable.parent.mkdir(parents=True)
            old_executable.write_bytes(b"old executable")
            (old_executable.parent / "old.dll").write_bytes(b"old dll")
            validations = [valid_runtime(old_executable), invalid_runtime(old_executable, "runtime_dll_missing")]
            with patch.object(manager, "validate_runtime_installation", side_effect=validations):
                with self.assertRaisesRegex(RuntimeError, "runtime_dll_missing"):
                    manager.install_runtime_from_zip(zip_path)
            self.assertEqual(old_executable.read_bytes(), b"old executable")
            self.assertTrue((old_executable.parent / "old.dll").exists())
            self.assertFalse(any(path.name.startswith("_backup") for path in manager.managed_runtime_dir().iterdir()))

    def test_part_runtime_is_ignored(self) -> None:
        with TemporaryDirectory() as directory:
            manager = RuntimeManager(Path(directory))
            part = manager.get_runtime_path().with_suffix(".exe.part")
            part.parent.mkdir(parents=True)
            part.write_bytes(b"partial")
            self.assertIsNone(manager.find_runtime_executable())

    def test_incomplete_legacy_runtime_is_quarantined(self) -> None:
        with TemporaryDirectory() as directory:
            manager = RuntimeManager(Path(directory))
            legacy = manager.legacy_runtime_path()
            legacy.write_bytes(b"legacy exe without dlls")

            def validate(path, *args, **kwargs):
                path = Path(path)
                if path.resolve(strict=False) == legacy.resolve(strict=False):
                    return invalid_runtime(path, "runtime_dll_missing")
                return invalid_runtime(path, "runtime_missing")

            with patch.object(manager, "validate_runtime_installation", side_effect=validate):
                self.assertIsNone(manager.find_runtime_executable())
            self.assertFalse(legacy.exists())
            quarantined = list((manager.managed_runtime_dir() / "incomplete").glob("*.incomplete"))
            self.assertEqual(len(quarantined), 1)

    def test_manual_import_uses_original_path_without_losing_dlls(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source_dir = root / "manual runtime with spaces"
            source_dir.mkdir()
            executable = source_dir / DEFAULT_RUNTIME_SPEC.executable_name
            executable.write_bytes(b"exe")
            dependency = source_dir / "llama.dll"
            dependency.write_bytes(b"dll")
            settings = AppSettings("JW PubliStudy Tests", "ManualRuntimeOriginalPath")
            settings.set_ai_use_custom_runtime(False)
            manager = RuntimeManager(root / "data", settings)
            with patch.object(manager, "validate_runtime_installation", return_value=valid_runtime(executable)):
                target = manager.import_runtime_executable(executable)
            self.assertEqual(target, executable.resolve())
            self.assertTrue(dependency.exists())
            self.assertEqual(settings.ai_custom_runtime_path(), str(executable.resolve()))
            self.assertTrue(settings.ai_use_custom_runtime())

    def test_start_uses_absolute_paths_list_command_and_executable_working_directory(self) -> None:
        with TemporaryDirectory(prefix="runtime path with spaces ") as directory:
            manager, executable, model = self._prepare_start(Path(directory))
            process = MagicMock()
            process.pid = 4321
            process.poll.return_value = None
            process.stdout = None
            process.stderr = None
            state, popen = self._start_with_mock_process(manager, executable, model, process, ready=True)
            self.assertEqual(state.status, "ready")
            command = popen.call_args.args[0]
            self.assertIsInstance(command, list)
            self.assertEqual(command[0], str(executable))
            self.assertEqual(command[2], str(model))
            self.assertEqual(popen.call_args.kwargs["cwd"], str(executable.parent))
            self.assertFalse(popen.call_args.kwargs["shell"])
            self.assertNotEqual(popen.call_args.kwargs["stdout"], subprocess.DEVNULL)
            self.assertNotEqual(popen.call_args.kwargs["stderr"], subprocess.DEVNULL)
            self.assertEqual(state.diagnostic.pid, 4321)
            self.assertEqual(state.diagnostic.startup_timeout_seconds, 777)

    def test_start_log_contains_required_technical_metadata(self) -> None:
        with TemporaryDirectory() as directory:
            manager, executable, model = self._prepare_start(Path(directory))
            process = MagicMock()
            process.pid = 4321
            process.poll.return_value = None
            process.stdout = None
            process.stderr = None
            self._start_with_mock_process(manager, executable, model, process, ready=True)
            logs = manager.last_runtime_log_text()
            for expected in (
                "application_version=",
                "operating_system=",
                "architecture=",
                "available_ram_gb=",
                f"runtime_executable={executable}",
                f"runtime_directory={executable.parent}",
                f"working_directory={executable.parent}",
                f"model_path={model}",
                "model_size=",
                "command=",
                "pid=4321",
                "host=127.0.0.1",
                "port=",
                "startup_timeout_seconds=777",
                "stdout_lines=0",
                "stderr_lines=0",
                "exit_code=<running>",
                "readiness: ready=true",
            ):
                self.assertIn(expected, logs)

    def test_start_maps_oserror_winerror_and_preserves_details(self) -> None:
        with TemporaryDirectory() as directory:
            manager, executable, model = self._prepare_start(Path(directory))
            error = OSError("not a valid Win32 application")
            error.errno = 8
            error.winerror = 193
            with (
                patch.object(manager, "find_runtime_executable", return_value=executable),
                patch.object(manager, "validate_runtime_installation", return_value=valid_runtime(executable)),
                patch.object(manager, "validate_runtime_command_flags", return_value=valid_runtime(executable, "--help")),
                patch("subprocess.Popen", side_effect=error),
            ):
                state = manager.start(model, 4096)
            self.assertEqual(state.error, "runtime_incompatible")
            self.assertEqual(state.diagnostic.winerror, 193)
            self.assertEqual(state.diagnostic.errno, 8)
            self.assertEqual(state.diagnostic.exception_type, "OSError")

    def test_nonzero_exit_code_and_stderr_are_in_diagnostic(self) -> None:
        with TemporaryDirectory() as directory:
            manager, executable, model = self._prepare_start(Path(directory))
            process = MagicMock()
            process.pid = 9
            process.poll.return_value = 7
            process.stdout = None
            process.stderr = None

            def not_ready(*args, **kwargs):
                manager._append_runtime_log("stderr", "unknown startup failure")
                return False

            with (
                patch.object(manager, "find_runtime_executable", return_value=executable),
                patch.object(manager, "validate_runtime_installation", return_value=valid_runtime(executable)),
                patch.object(manager, "validate_runtime_command_flags", return_value=valid_runtime(executable, "--help")),
                patch.object(manager, "wait_until_ready", side_effect=not_ready),
                patch("subprocess.Popen", return_value=process),
            ):
                state = manager.start(model, 4096)
            self.assertEqual(state.error, "runtime_process_exit_nonzero")
            self.assertEqual(state.diagnostic.exit_code, 7)
            self.assertIn("unknown startup failure", state.diagnostic.stderr)

    def test_windows_missing_dll_exit_code_is_normalized_and_classified(self) -> None:
        with TemporaryDirectory() as directory:
            manager, executable, model = self._prepare_start(Path(directory))
            process = MagicMock()
            process.pid = 10
            process.poll.return_value = 0xC0000135
            process.stdout = None
            process.stderr = None
            state, _ = self._start_with_mock_process(manager, executable, model, process, ready=False)
            self.assertEqual(state.error, "runtime_dll_missing")
            self.assertEqual(state.diagnostic.exit_code, -1073741515)
            self.assertEqual(state.diagnostic.native_exit_code, 0xC0000135)

    def test_validate_runtime_uses_version_with_cwd(self) -> None:
        with TemporaryDirectory() as directory:
            executable = Path(directory) / DEFAULT_RUNTIME_SPEC.executable_name
            executable.write_bytes(b"exe")
            manager = RuntimeManager(Path(directory) / "data")
            completed = subprocess.CompletedProcess([str(executable), "--version"], 0, "llama version 1", "")
            with patch("subprocess.run", return_value=completed) as run:
                result = manager.validate_runtime_installation(executable)
            self.assertTrue(result.valid)
            self.assertEqual(result.probe_argument, "--version")
            self.assertEqual(run.call_args.kwargs["cwd"], str(executable.parent))
            self.assertFalse(run.call_args.kwargs["shell"])

    def test_explicit_validation_allows_installation_staging_directory(self) -> None:
        with TemporaryDirectory() as directory:
            executable = Path(directory) / "_installing-test" / DEFAULT_RUNTIME_SPEC.executable_name
            executable.parent.mkdir()
            executable.write_bytes(b"exe")
            manager = RuntimeManager(Path(directory) / "data")
            completed = subprocess.CompletedProcess([], 0, "llama version 1", "")
            with patch("subprocess.run", return_value=completed):
                result = manager.validate_runtime_installation(executable, use_cache=False)
            self.assertTrue(result.valid)

    def test_validate_runtime_falls_back_to_help_and_accepts_nonzero_help_exit(self) -> None:
        with TemporaryDirectory() as directory:
            executable = Path(directory) / DEFAULT_RUNTIME_SPEC.executable_name
            executable.write_bytes(b"exe")
            manager = RuntimeManager(Path(directory) / "data")
            version = subprocess.CompletedProcess([], 2, "", "unknown option")
            help_result = subprocess.CompletedProcess([], 1, "llama server --model FILE --host HOST", "")
            with patch("subprocess.run", side_effect=[version, help_result]) as run:
                result = manager.validate_runtime_installation(executable)
            self.assertTrue(result.valid)
            self.assertEqual(result.probe_argument, "--help")
            self.assertEqual(run.call_count, 2)

    def test_validate_runtime_timeout_is_diagnostic(self) -> None:
        with TemporaryDirectory() as directory:
            executable = Path(directory) / DEFAULT_RUNTIME_SPEC.executable_name
            executable.write_bytes(b"exe")
            manager = RuntimeManager(Path(directory) / "data")
            timeout = subprocess.TimeoutExpired([str(executable), "--version"], 8, output="partial")
            with patch("subprocess.run", side_effect=timeout):
                result = manager.validate_runtime_installation(executable)
            self.assertFalse(result.valid)
            self.assertEqual(result.error, "runtime_validation_timeout")
            self.assertEqual(result.exception_type, "TimeoutExpired")
            self.assertIn("partial", result.stdout)

    def test_wait_until_ready_handles_slow_server_and_models_after_retries(self) -> None:
        with TemporaryDirectory() as directory:
            manager = RuntimeManager(Path(directory))
            process = MagicMock()
            process.poll.return_value = None
            manager._process = process
            responses = [
                urllib.error.URLError("not ready"),
                urllib.error.URLError("health not ready"),
                FakeResponse(200),
            ]
            with patch("urllib.request.urlopen", side_effect=responses) as urlopen, patch("time.sleep"):
                self.assertTrue(manager.wait_until_ready("http://127.0.0.1:12345", 120))
            self.assertEqual(urlopen.call_count, 3)
            requested_urls = [call.args[0] for call in urlopen.call_args_list]
            self.assertEqual(requested_urls[-1], "http://127.0.0.1:12345/v1/models")
            self.assertEqual(manager._readiness_attempts, 2)

    def test_wait_until_ready_stops_when_process_exits_before_readiness(self) -> None:
        with TemporaryDirectory() as directory:
            manager = RuntimeManager(Path(directory))
            process = MagicMock()
            process.poll.return_value = 3
            manager._process = process
            with patch("urllib.request.urlopen") as urlopen:
                self.assertFalse(manager.wait_until_ready("http://127.0.0.1:12345", 120))
            urlopen.assert_not_called()

    def test_wait_until_ready_honors_cancellation_without_network_probe(self) -> None:
        with TemporaryDirectory() as directory:
            manager = RuntimeManager(Path(directory))
            cancellation_event = threading.Event()
            cancellation_event.set()
            with patch("urllib.request.urlopen") as urlopen:
                self.assertFalse(
                    manager.wait_until_ready(
                        "http://127.0.0.1:12345",
                        120,
                        cancellation_event=cancellation_event,
                    )
                )
            urlopen.assert_not_called()

    def test_stop_terminates_and_waits_for_process(self) -> None:
        with TemporaryDirectory() as directory:
            manager = RuntimeManager(Path(directory))
            process = MagicMock()
            process.pid = 99
            process.poll.return_value = None
            manager._process = process
            manager.stop()
            process.terminate.assert_called_once_with()
            process.wait.assert_called_once_with(timeout=8)
            self.assertEqual(manager.get_state().status, "stopped")

    def test_log_buffer_keeps_at_least_five_hundred_lines(self) -> None:
        with TemporaryDirectory() as directory:
            manager = RuntimeManager(Path(directory))
            for index in range(750):
                manager.record_event("test", f"line={index}")
            self.assertEqual(len(manager.last_runtime_logs()), 750)

    def test_parse_runtime_loading_progress(self) -> None:
        self.assertEqual(parse_runtime_loading_progress("loaded 50/100 tensors"), 50)
        self.assertIsNone(parse_runtime_loading_progress("loading model"))
        self.assertIsNone(parse_runtime_loading_progress(""))


if __name__ == "__main__":
    unittest.main()
