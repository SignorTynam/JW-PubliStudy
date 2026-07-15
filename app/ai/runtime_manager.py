from __future__ import annotations

import ctypes
import json
import os
import platform
import re
import shutil
import socket
import stat
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from app.settings import AppSettings
from app.ai.runtime_launch_plan import BackendCapabilities, RuntimeLaunchPlan
from app.version import APP_VERSION


@dataclass(frozen=True)
class RuntimeSpec:
    id: str
    display_name: str
    executable_name: str
    download_url: str | None
    sha256: str | None


@dataclass
class RuntimeValidationResult:
    valid: bool
    executable: Path
    error: str | None = None
    probe_argument: str | None = None
    command: list[str] = field(default_factory=list)
    working_directory: Path | None = None
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    native_exit_code: int | None = None
    exception_type: str | None = None
    exception_message: str | None = None
    errno: int | None = None
    winerror: int | None = None


@dataclass
class RuntimeDiagnostic:
    error: str | None = None
    command: list[str] = field(default_factory=list)
    executable_path: str | None = None
    runtime_directory: str | None = None
    working_directory: str | None = None
    model_path: str | None = None
    model_size: int | None = None
    host: str = "127.0.0.1"
    port: int | None = None
    pid: int | None = None
    started_at: str | None = None
    duration_seconds: float | None = None
    startup_timeout_seconds: int | None = None
    readiness_attempts: int = 0
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    native_exit_code: int | None = None
    exception_type: str | None = None
    exception_message: str | None = None
    errno: int | None = None
    winerror: int | None = None
    backend_id: str = "llama_cpp_cpu"
    runtime_variant_id: str = "legacy"
    device_id: str | None = None
    host_architecture: str = "unknown"
    executable_architecture: str = "unknown"
    requires_emulation: bool = False
    cpu_threads: int | None = None
    gpu_layers: int | None = None
    environment_keys: tuple[str, ...] = ()
    selection_reasons: tuple[str, ...] = ()


@dataclass
class RuntimeState:
    status: str
    endpoint_url: str | None
    port: int | None
    process_running: bool
    error: str | None = None
    diagnostic: RuntimeDiagnostic | None = None


DEFAULT_RUNTIME_SPEC = RuntimeSpec(
    id="llama_cpp_server",
    display_name="llama.cpp server",
    executable_name="llama-server.exe" if sys.platform.startswith("win") else "llama-server",
    download_url="https://api.github.com/repos/ggml-org/llama.cpp/releases/latest",
    sha256=None,
)


class RuntimeManager:
    DEFAULT_STARTUP_TIMEOUT_SECONDS = 600
    RUNTIME_VALIDATION_TIMEOUT_SECONDS = 8
    MIN_PLAUSIBLE_MODEL_BYTES = 1024 * 1024
    LOG_BUFFER_LINES = 5000

    def __init__(self, data_dir: Path, settings: AppSettings | None = None) -> None:
        self._data_dir = Path(data_dir)
        self._settings = settings
        self._process: subprocess.Popen[str] | None = None
        self._state = RuntimeState("not_installed", None, None, False)
        self._log_lock = threading.Lock()
        self._runtime_logs: deque[str] = deque(maxlen=self.LOG_BUFFER_LINES)
        self._stdout_lines: deque[str] = deque(maxlen=250)
        self._stderr_lines: deque[str] = deque(maxlen=250)
        self._log_threads: list[threading.Thread] = []
        self._process_started_monotonic: float | None = None
        self._readiness_attempts = 0
        self._last_validation: RuntimeValidationResult | None = None
        self._last_selected_asset_name: str | None = None
        self._validation_cache: dict[tuple[str, int, int], RuntimeValidationResult] = {}

    def find_runtime_executable(self) -> Path | None:
        candidates: list[tuple[Path, bool]] = []
        if self._settings is not None and self._settings.ai_use_custom_runtime():
            custom_value = self._settings.ai_custom_runtime_path()
            if not custom_value:
                return None
            custom_path = Path(custom_value).expanduser()
            return self._validated_candidate(custom_path, quarantine_legacy=False)

        configured = self._settings.ai_runtime_path() if self._settings is not None else ""
        if configured:
            candidates.append((Path(configured).expanduser(), True))
        active_runtime = self._active_runtime_path()
        if active_runtime is not None:
            candidates.append((active_runtime, False))
        candidates.extend(
            [
                (self.get_runtime_path(), False),
                (self.legacy_runtime_path(), True),
                (Path.cwd() / "runtime" / "llama.cpp" / "current" / DEFAULT_RUNTIME_SPEC.executable_name, False),
                (Path.cwd() / "runtime" / DEFAULT_RUNTIME_SPEC.executable_name, False),
            ]
        )

        seen: set[str] = set()
        for candidate, quarantine_legacy in candidates:
            absolute = candidate.resolve(strict=False)
            key = os.path.normcase(str(absolute))
            if key in seen or self._is_ignored_runtime_path(absolute):
                continue
            seen.add(key)
            validated = self._validated_candidate(absolute, quarantine_legacy=quarantine_legacy)
            if validated is not None:
                return validated
        return None

    def _active_runtime_path(self) -> Path | None:
        active_path = self.runtime_dir() / "active.json"
        try:
            payload = json.loads(active_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        value = payload.get("executable") if isinstance(payload, dict) else None
        return Path(value).expanduser() if isinstance(value, str) and value.strip() else None

    def _validated_candidate(self, path: Path, quarantine_legacy: bool) -> Path | None:
        validation = self.validate_runtime_installation(path)
        self._last_validation = validation
        if validation.valid:
            return path.resolve(strict=False)
        self.record_event(
            "validation",
            f"runtime_rejected path={path.resolve(strict=False)} error={validation.error} "
            f"exit_code={validation.exit_code} winerror={validation.winerror}",
        )
        if quarantine_legacy and self._is_legacy_runtime_path(path) and path.exists():
            self._quarantine_legacy_runtime(path, validation.error or "runtime_incomplete")
        return None

    def is_runtime_available(self) -> bool:
        return self.find_runtime_executable() is not None

    def runtime_dir(self) -> Path:
        path = self._data_dir / "runtime"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def managed_runtime_dir(self) -> Path:
        path = self.runtime_dir() / "llama.cpp"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_runtime_path(self) -> Path:
        return self.managed_runtime_dir() / "current" / DEFAULT_RUNTIME_SPEC.executable_name

    def legacy_runtime_path(self) -> Path:
        return self.runtime_dir() / DEFAULT_RUNTIME_SPEC.executable_name

    def supports_runtime_download(self) -> bool:
        return sys.platform.startswith("win")

    def find_latest_windows_asset(self, release_json: dict) -> str | None:
        assets = release_json.get("assets")
        if not isinstance(assets, list):
            return None

        ranked: list[tuple[int, str, str]] = []
        avx2_supported = self._cpu_supports_avx2()
        excluded = re.compile(
            r"(?:^|[-_.])(cuda|vulkan|rocm|hip|sycl|arm|arm64|aarch64|x86|win32|source|experimental)(?:[-_.]|$)",
            re.IGNORECASE,
        )
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            name = str(asset.get("name") or "")
            url = str(asset.get("browser_download_url") or "")
            lowered = name.lower()
            if not url or not lowered.endswith(".zip") or "win" not in lowered:
                continue
            if "x64" not in lowered and "amd64" not in lowered:
                continue
            if ("cpu" not in lowered and "avx2" not in lowered) or excluded.search(lowered):
                continue
            is_avx2 = "avx2" in lowered
            if is_avx2 and not avx2_supported:
                continue
            if re.search(r"bin-win-cpu-x64\.zip$", lowered):
                rank = 0
            elif not any(token in lowered for token in ("avx", "avx2", "avx512")):
                rank = 1
            elif is_avx2:
                rank = 2
            else:
                continue
            ranked.append((rank, name, url))

        if not ranked:
            return None
        _, name, url = sorted(ranked, key=lambda item: (item[0], item[1].lower()))[0]
        self._last_selected_asset_name = name
        self.record_event("download", f"selected_asset={name}")
        return url

    def last_selected_asset_name(self) -> str | None:
        return self._last_selected_asset_name

    def install_runtime_from_zip(self, zip_path: Path) -> Path:
        managed_root = self.managed_runtime_dir()
        operation_id = uuid.uuid4().hex
        extract_root = managed_root / f"_extracting-{operation_id}"
        staging = managed_root / f"_installing-{operation_id}"
        current = managed_root / "current"
        backup = managed_root / f"_backup-{operation_id}"
        extract_root.mkdir(parents=True, exist_ok=False)
        replaced_old_installation = False

        try:
            with zipfile.ZipFile(zip_path) as archive:
                self._safe_extract_zip(archive, extract_root)
            executable = self._find_extracted_executable(extract_root)
            if executable is None:
                raise RuntimeError("runtime_executable_missing")

            shutil.copytree(executable.parent, staging)
            staged_executable = staging / executable.name
            validation = self.validate_runtime_installation(staged_executable, use_cache=False)
            self._last_validation = validation
            self._log_validation(validation, "installation_validation")
            if not validation.valid:
                raise RuntimeError(validation.error or "runtime_incomplete")

            if current.exists():
                self._replace_path_with_retry(current, backup)
                replaced_old_installation = True
            try:
                self._replace_path_with_retry(staging, current)
                target = (current / executable.name).resolve(strict=False)
                final_validation = self.validate_runtime_installation(target, use_cache=False)
                self._log_validation(final_validation, "installed_runtime_validation")
                if not final_validation.valid:
                    raise RuntimeError(final_validation.error or "runtime_incomplete")
                self._store_validation_cache(target, final_validation)
                if self._settings is not None:
                    self._settings.set_ai_runtime_path(str(target))
            except BaseException:
                if current.exists():
                    shutil.rmtree(current, ignore_errors=True)
                if replaced_old_installation and backup.exists():
                    self._replace_path_with_retry(backup, current)
                raise
            if backup.exists():
                shutil.rmtree(backup, ignore_errors=True)
            self._remove_invalid_legacy_after_install()
            self.record_event("installation", f"runtime_installed path={target}")
            return target
        finally:
            shutil.rmtree(extract_root, ignore_errors=True)
            shutil.rmtree(staging, ignore_errors=True)
            if backup.exists() and not current.exists():
                self._replace_path_with_retry(backup, current)

    def install_runtime_variant_from_zip(self, zip_path: Path, variant_id: str, release_tag: str) -> Path:
        """Install a complete distribution side-by-side without changing the active runtime."""
        safe_variant = self._safe_directory_component(variant_id)
        safe_release = self._safe_directory_component(release_tag or "unknown")
        variant_root = self.runtime_dir() / safe_variant
        target_directory = variant_root / safe_release
        operation_id = uuid.uuid4().hex
        extract_root = variant_root / f"_extracting-{operation_id}"
        staging = variant_root / f"_installing-{operation_id}"
        backup = variant_root / f"_backup-{operation_id}"
        variant_root.mkdir(parents=True, exist_ok=True)
        extract_root.mkdir(parents=True, exist_ok=False)
        replaced = False
        try:
            with zipfile.ZipFile(zip_path) as archive:
                self._safe_extract_zip(archive, extract_root)
            executable = self._find_extracted_executable(extract_root)
            if executable is None:
                raise RuntimeError("runtime_executable_missing")
            shutil.copytree(executable.parent, staging)
            staged_executable = staging / executable.name
            validation = self.validate_runtime_installation(staged_executable, use_cache=False)
            self._log_validation(validation, "variant_installation_validation")
            if not validation.valid:
                raise RuntimeError(validation.error or "runtime_incomplete")
            if target_directory.exists():
                self._replace_path_with_retry(target_directory, backup)
                replaced = True
            try:
                self._replace_path_with_retry(staging, target_directory)
                target = (target_directory / executable.name).resolve(strict=False)
                final_validation = self.validate_runtime_installation(target, use_cache=False)
                self._log_validation(final_validation, "variant_installed_validation")
                if not final_validation.valid:
                    raise RuntimeError(final_validation.error or "runtime_incomplete")
                self._store_validation_cache(target, final_validation)
            except BaseException:
                if target_directory.exists():
                    shutil.rmtree(target_directory, ignore_errors=True)
                if replaced and backup.exists():
                    self._replace_path_with_retry(backup, target_directory)
                raise
            shutil.rmtree(backup, ignore_errors=True)
            self.record_event(
                "installation",
                f"runtime_variant_installed variant={safe_variant} release={safe_release} path={target}",
            )
            return target
        finally:
            shutil.rmtree(extract_root, ignore_errors=True)
            shutil.rmtree(staging, ignore_errors=True)
            if backup.exists() and not target_directory.exists():
                self._replace_path_with_retry(backup, target_directory)

    def runtime_variant_path(self, variant_id: str, release_tag: str) -> Path:
        return (
            self.runtime_dir()
            / self._safe_directory_component(variant_id)
            / self._safe_directory_component(release_tag or "unknown")
            / DEFAULT_RUNTIME_SPEC.executable_name
        )

    def activate_runtime(self, executable: Path, metadata: dict[str, object]) -> None:
        path = Path(executable).expanduser().resolve(strict=False)
        validation = self.validate_runtime_installation(path)
        if not validation.valid:
            raise RuntimeError(validation.error or "runtime_incomplete")
        payload = {"executable": str(path), **metadata}
        active_path = self.runtime_dir() / "active.json"
        temporary = active_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        temporary.replace(active_path)
        if self._settings is not None:
            self._settings.set_ai_runtime_path(str(path))
        self.record_event("configuration", f"runtime_activated path={path} variant={metadata.get('runtime_variant_id')}")

    def migrate_legacy_runtime(self, variant_id: str = "llama_cpp_cpu_x86_64_generic") -> Path | None:
        source = self.get_runtime_path()
        if not source.is_file() or not self.validate_runtime_installation(source).valid:
            return None
        target_directory = self.runtime_dir() / self._safe_directory_component(variant_id) / "legacy"
        target = target_directory / source.name
        if target.is_file() and self.validate_runtime_installation(target).valid:
            return target.resolve(strict=False)
        temporary = target_directory.with_name(f"_installing-migration-{uuid.uuid4().hex}")
        shutil.copytree(source.parent, temporary)
        temporary.replace(target_directory)
        self.record_event("migration", f"legacy_runtime_copied source={source} target={target}")
        return target.resolve(strict=False)

    def _safe_extract_zip(self, archive: zipfile.ZipFile, destination: Path) -> None:
        root = destination.resolve()
        for member in archive.infolist():
            normalized_name = member.filename.replace("\\", "/")
            pure_path = PurePosixPath(normalized_name)
            if (
                pure_path.is_absolute()
                or ".." in pure_path.parts
                or (pure_path.parts and re.match(r"^[A-Za-z]:", pure_path.parts[0]))
            ):
                raise RuntimeError("runtime_zip_unsafe_path")
            if any(part.lower().endswith(".part") for part in pure_path.parts):
                continue
            unix_mode = (member.external_attr >> 16) & 0xFFFF
            if unix_mode and stat.S_ISLNK(unix_mode):
                raise RuntimeError("runtime_zip_unsafe_path")
            target = (root / Path(*pure_path.parts)).resolve()
            if target != root and root not in target.parents:
                raise RuntimeError("runtime_zip_unsafe_path")
            if member.is_dir() or normalized_name.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)

    def _replace_path_with_retry(self, source: Path, destination: Path, timeout_seconds: float = 5.0) -> None:
        deadline = time.monotonic() + timeout_seconds
        while True:
            try:
                source.replace(destination)
                return
            except OSError as exc:
                winerror = getattr(exc, "winerror", None)
                if winerror not in {5, 32} or time.monotonic() >= deadline:
                    raise
                time.sleep(0.1)

    def _find_extracted_executable(self, extract_root: Path) -> Path | None:
        names = {DEFAULT_RUNTIME_SPEC.executable_name.lower(), "llama-server.exe", "llama-server"}
        candidates = sorted(
            (
                path
                for path in extract_root.rglob("*")
                if path.is_file() and path.name.lower() in names
            ),
            key=lambda path: (len(path.relative_to(extract_root).parts), str(path).lower()),
        )
        return candidates[0] if candidates else None

    def is_runtime_ready_file(self, path: Path) -> bool:
        return self.validate_runtime_installation(path).valid

    def validate_runtime_installation(
        self,
        executable: Path,
        timeout_seconds: int | float | None = None,
        *,
        use_cache: bool = True,
    ) -> RuntimeValidationResult:
        path = Path(executable).expanduser().resolve(strict=False)
        working_directory = path.parent
        if path.name.lower().endswith(".part"):
            return RuntimeValidationResult(False, path, "runtime_incomplete", working_directory=working_directory)
        try:
            if not path.exists():
                return RuntimeValidationResult(False, path, "runtime_missing", working_directory=working_directory)
            if not path.is_file():
                return RuntimeValidationResult(False, path, "runtime_incomplete", working_directory=working_directory)
            stat_result = path.stat()
        except OSError as exc:
            return self._validation_from_oserror(path, working_directory, [], exc)
        cache_key = (os.path.normcase(str(path)), stat_result.st_size, stat_result.st_mtime_ns)
        if use_cache and cache_key in self._validation_cache:
            return self._validation_cache[cache_key]
        if sys.platform.startswith("win") and path.suffix.lower() != ".exe":
            return RuntimeValidationResult(False, path, "runtime_incompatible", working_directory=working_directory)

        timeout = timeout_seconds or self.RUNTIME_VALIDATION_TIMEOUT_SECONDS
        version_result = self._run_runtime_probe(path, "--version", timeout)
        if isinstance(version_result, RuntimeValidationResult):
            return version_result
        version_code, version_stdout, version_stderr = version_result
        version_text = f"{version_stdout}\n{version_stderr}".lower()
        if version_code == 0 and any(marker in version_text for marker in ("llama", "version", "built with")):
            result = RuntimeValidationResult(
                True,
                path,
                probe_argument="--version",
                command=[str(path), "--version"],
                working_directory=working_directory,
                stdout=version_stdout,
                stderr=version_stderr,
                exit_code=_normalize_windows_exit_code(version_code),
                native_exit_code=version_code,
            )
            self._validation_cache[cache_key] = result
            return result

        help_result = self._run_runtime_probe(path, "--help", timeout)
        if isinstance(help_result, RuntimeValidationResult):
            return help_result
        help_code, help_stdout, help_stderr = help_result
        help_text = f"{help_stdout}\n{help_stderr}".lower()
        help_is_meaningful = "--model" in help_text and ("--host" in help_text or "llama" in help_text)
        normalized_help_code = _normalize_windows_exit_code(help_code)
        if help_is_meaningful and not self._is_fatal_runtime_exit(normalized_help_code):
            result = RuntimeValidationResult(
                True,
                path,
                probe_argument="--help",
                command=[str(path), "--help"],
                working_directory=working_directory,
                stdout=help_stdout,
                stderr=help_stderr,
                exit_code=normalized_help_code,
                native_exit_code=help_code,
            )
            self._validation_cache[cache_key] = result
            return result

        combined_stdout = "\n".join(part for part in (version_stdout, help_stdout) if part)
        combined_stderr = "\n".join(part for part in (version_stderr, help_stderr) if part)
        normalized_code = _normalize_windows_exit_code(help_code if help_code is not None else version_code)
        return RuntimeValidationResult(
            False,
            path,
            self._classify_runtime_failure(normalized_code, combined_stderr, combined_stdout),
            probe_argument="--help",
            command=[str(path), "--help"],
            working_directory=working_directory,
            stdout=combined_stdout,
            stderr=combined_stderr,
            exit_code=normalized_code,
            native_exit_code=help_code,
        )

    def _run_runtime_probe(
        self,
        executable: Path,
        argument: str,
        timeout_seconds: int | float,
    ) -> tuple[int, str, str] | RuntimeValidationResult:
        command = [str(executable), argument]
        try:
            creationflags = subprocess.CREATE_NO_WINDOW if sys.platform.startswith("win") else 0
            completed = subprocess.run(
                command,
                cwd=str(executable.parent),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds,
                shell=False,
                creationflags=creationflags,
                check=False,
            )
            return int(completed.returncode), completed.stdout or "", completed.stderr or ""
        except subprocess.TimeoutExpired as exc:
            return RuntimeValidationResult(
                False,
                executable,
                "runtime_validation_timeout",
                probe_argument=argument,
                command=command,
                working_directory=executable.parent,
                stdout=_coerce_text(exc.stdout),
                stderr=_coerce_text(exc.stderr),
                exception_type=type(exc).__name__,
                exception_message=str(exc),
            )
        except OSError as exc:
            return self._validation_from_oserror(executable, executable.parent, command, exc, argument)

    def validate_runtime_command_flags(self, executable: Path) -> RuntimeValidationResult:
        path = Path(executable).expanduser().resolve(strict=False)
        probe = self._run_runtime_probe(path, "--help", self.RUNTIME_VALIDATION_TIMEOUT_SECONDS)
        if isinstance(probe, RuntimeValidationResult):
            return probe
        exit_code, stdout, stderr = probe
        help_text = f"{stdout}\n{stderr}".lower()
        required_flags = ("--model", "--host", "--port", "--ctx-size")
        normalized_code = _normalize_windows_exit_code(exit_code)
        valid = all(flag in help_text for flag in required_flags) and not self._is_fatal_runtime_exit(normalized_code)
        return RuntimeValidationResult(
            valid,
            path,
            None if valid else "runtime_flag_unsupported",
            probe_argument="--help",
            command=[str(path), "--help"],
            working_directory=path.parent,
            stdout=stdout,
            stderr=stderr,
            exit_code=normalized_code,
            native_exit_code=exit_code,
        )

    def _validation_from_oserror(
        self,
        executable: Path,
        working_directory: Path,
        command: list[str],
        exc: OSError,
        probe_argument: str | None = None,
    ) -> RuntimeValidationResult:
        error = self._classify_oserror(exc)
        return RuntimeValidationResult(
            False,
            executable,
            error,
            probe_argument=probe_argument,
            command=command,
            working_directory=working_directory,
            exception_type=type(exc).__name__,
            exception_message=str(exc),
            errno=getattr(exc, "errno", None),
            winerror=getattr(exc, "winerror", None),
        )

    def import_runtime_executable(self, source_path: Path) -> Path:
        source = Path(source_path).expanduser().resolve(strict=False)
        if sys.platform.startswith("win") and source.suffix.lower() != ".exe":
            raise ValueError("invalid_runtime_file")
        if not source.is_file():
            raise FileNotFoundError("runtime_file_missing")
        validation = self.validate_runtime_installation(source, use_cache=False)
        self._last_validation = validation
        self._log_validation(validation, "manual_runtime_validation")
        if not validation.valid:
            raise RuntimeError(validation.error or "invalid_runtime_file")
        if self._settings is not None:
            self._settings.set_ai_custom_runtime_path(str(source))
            self._settings.set_ai_use_custom_runtime(True)
        self._store_validation_cache(source, validation)
        self.record_event("configuration", f"manual_runtime_path={source} working_directory={source.parent}")
        return source

    def find_free_port(self) -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    def build_command(self, model_path: Path, port: int, context_tokens: int) -> list[str]:
        executable = self.find_runtime_executable()
        if executable is None:
            executable = self.get_runtime_path()
        return self._build_command(executable, model_path, port, context_tokens)

    def probe_backend_capabilities(self, executable: Path) -> BackendCapabilities:
        path = Path(executable).expanduser().resolve(strict=False)
        probe = self._run_runtime_probe(path, "--help", self.RUNTIME_VALIDATION_TIMEOUT_SECONDS)
        if isinstance(probe, RuntimeValidationResult):
            return BackendCapabilities()
        _code, stdout, stderr = probe
        help_text = f"{stdout}\n{stderr}"
        supported_flags = frozenset(re.findall(r"(?<!\w)(--[a-z0-9][a-z0-9-]*)", help_text.lower()))
        devices: tuple[str, ...] = ()
        if "--list-devices" in supported_flags:
            devices = self._probe_runtime_devices(path)
        return BackendCapabilities(
            supports_device_selection="--device" in supported_flags,
            supports_gpu_layers="--n-gpu-layers" in supported_flags,
            available_devices=devices,
            supported_flags=supported_flags,
        )

    def build_launch_command(
        self,
        plan: RuntimeLaunchPlan,
        capabilities: BackendCapabilities | None = None,
    ) -> list[str]:
        capabilities = capabilities or BackendCapabilities()
        command = self._build_command(plan.executable, plan.model_path, plan.port, plan.context_tokens)
        arguments = list(plan.arguments)
        index = 0
        while index < len(arguments):
            flag = arguments[index]
            next_value = arguments[index + 1] if index + 1 < len(arguments) else None
            value = next_value if next_value is not None and (
                not next_value.startswith("-") or re.fullmatch(r"-?\d+(?:\.\d+)?", next_value)
            ) else None
            advance = 2 if value is not None else 1
            if not flag.startswith("-"):
                index += 1
                continue
            canonical = {"-ngl": "--n-gpu-layers", "-t": "--threads"}.get(flag, flag)
            if canonical not in capabilities.supported_flags:
                self.record_event("launch_plan", f"flag_skipped flag={flag} reason=unsupported")
                index += advance
                continue
            if canonical == "--device" and (
                not plan.device_id or plan.device_id not in capabilities.available_devices
            ):
                self.record_event("launch_plan", f"flag_skipped flag={flag} reason=device_not_listed")
                index += advance
                continue
            if value is not None and ("/v1/chat/completions" in value or value.startswith(("http://", "https://"))):
                self.record_event("launch_plan", f"argument_skipped flag={flag} reason=endpoint_not_allowed")
                index += advance
                continue
            if canonical in {"--threads", "--n-gpu-layers"} and (
                value is None or not re.fullmatch(r"-?\d+", value)
            ):
                self.record_event("launch_plan", f"flag_skipped flag={flag} reason=invalid_numeric_value")
                index += advance
                continue
            command.append(flag)
            if value is not None:
                command.append(value)
            index += advance
        return command

    def _build_command(self, executable: Path, model_path: Path, port: int, context_tokens: int) -> list[str]:
        return [
            str(Path(executable).resolve(strict=False)),
            "--model",
            str(Path(model_path).resolve(strict=False)),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--ctx-size",
            str(context_tokens),
        ]

    def start(
        self,
        model_path: Path,
        context_tokens: int,
        timeout_seconds: int | None = None,
        *,
        cancellation_event: threading.Event | None = None,
        launch_plan: RuntimeLaunchPlan | None = None,
    ) -> RuntimeState:
        if self._process is not None and self._process.poll() is None and self._state.endpoint_url:
            if launch_plan is not None:
                # Recalculation must actually exercise the new plan (including
                # context/device flags) before it can become active.
                self.stop()
            else:
                self._state.status = "ready"
                self._state.process_running = True
                return self._state

        self._clear_runtime_logs()
        self._process_started_monotonic = time.monotonic()
        self._readiness_attempts = 0
        resolved_model = Path(launch_plan.model_path if launch_plan else model_path).expanduser().resolve(strict=False)
        model_error, model_size = self._validate_model(resolved_model)
        if model_error:
            diagnostic = RuntimeDiagnostic(error=model_error, model_path=str(resolved_model), model_size=model_size)
            self.record_event("error", f"error={model_error} model_path={resolved_model} model_size={model_size}")
            self._state = RuntimeState("failed", None, None, False, model_error, diagnostic)
            return self._state

        executable = Path(launch_plan.executable) if launch_plan else self.find_runtime_executable()
        if executable is None:
            error = self._last_validation.error if self._last_validation is not None else "runtime_missing"
            diagnostic = self._diagnostic_from_validation(self._last_validation, error, resolved_model, model_size)
            self.record_event("error", f"error={error} runtime_executable=not_found")
            self._state = RuntimeState("not_installed", None, None, False, error, diagnostic)
            return self._state

        executable = executable.resolve(strict=False)
        validation = self.validate_runtime_installation(executable, use_cache=False)
        self._last_validation = validation
        self._log_validation(validation, "preflight_validation")
        if not validation.valid:
            error = validation.error or "runtime_incomplete"
            diagnostic = self._diagnostic_from_validation(validation, error, resolved_model, model_size)
            self._state = RuntimeState("failed", None, None, False, error, diagnostic)
            return self._state

        flags_validation = self.validate_runtime_command_flags(executable)
        self._log_validation(flags_validation, "runtime_flags_validation")
        if not flags_validation.valid:
            error = flags_validation.error or "runtime_flag_unsupported"
            diagnostic = self._diagnostic_from_validation(flags_validation, error, resolved_model, model_size)
            self._state = RuntimeState("failed", None, None, False, error, diagnostic)
            return self._state

        port = int(launch_plan.port) if launch_plan else self.find_free_port()
        endpoint_base = f"http://127.0.0.1:{port}"
        capabilities = self.probe_backend_capabilities(executable) if launch_plan else None
        command = (
            self.build_launch_command(launch_plan, capabilities)
            if launch_plan
            else self._build_command(executable, resolved_model, port, context_tokens)
        )
        working_directory = Path(launch_plan.working_directory) if launch_plan else executable.parent
        startup_timeout = self._resolve_startup_timeout(timeout_seconds)
        started_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        diagnostic = RuntimeDiagnostic(
            command=command,
            executable_path=str(executable),
            runtime_directory=str(executable.parent),
            working_directory=str(working_directory),
            model_path=str(resolved_model),
            model_size=model_size,
            port=port,
            started_at=started_at,
            startup_timeout_seconds=startup_timeout,
            backend_id=launch_plan.backend_id if launch_plan else "llama_cpp_cpu",
            runtime_variant_id=launch_plan.runtime_variant_id if launch_plan else "legacy",
            device_id=launch_plan.device_id if launch_plan else None,
            host_architecture=launch_plan.host_architecture if launch_plan else platform.machine() or "unknown",
            executable_architecture=launch_plan.executable_architecture if launch_plan else platform.machine() or "unknown",
            requires_emulation=launch_plan.requires_emulation if launch_plan else False,
            cpu_threads=launch_plan.cpu_threads if launch_plan else None,
            gpu_layers=launch_plan.gpu_layers if launch_plan else None,
            environment_keys=tuple(sorted(launch_plan.environment)) if launch_plan else (),
            selection_reasons=launch_plan.selection_reasons if launch_plan else (),
        )
        self._log_startup_metadata(diagnostic)

        try:
            creationflags = subprocess.CREATE_NO_WINDOW if sys.platform.startswith("win") else 0
            process_environment = os.environ.copy()
            if launch_plan:
                process_environment.update(launch_plan.environment)
            self._process = subprocess.Popen(
                command,
                cwd=str(working_directory),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=creationflags,
                shell=False,
                env=process_environment,
            )
            diagnostic.pid = self._process.pid
            self.record_event("process", f"pid={self._process.pid}")
            self._start_log_readers(self._process)
        except OSError as exc:
            error = self._classify_oserror(exc)
            diagnostic.error = error
            diagnostic.exception_type = type(exc).__name__
            diagnostic.exception_message = str(exc)
            diagnostic.errno = getattr(exc, "errno", None)
            diagnostic.winerror = getattr(exc, "winerror", None)
            diagnostic.duration_seconds = self._startup_duration()
            self.record_event(
                "error",
                f"error={error} exception_type={type(exc).__name__} message={exc} "
                f"errno={diagnostic.errno} winerror={diagnostic.winerror} command={subprocess.list2cmdline(command)} "
                f"working_directory={working_directory}",
            )
            self.record_event("diagnostic", "stdout=<process_not_started> stderr=<process_not_started> exit_code=<not_available>")
            self._state = RuntimeState("failed", None, None, False, error, diagnostic)
            return self._state

        self._state = RuntimeState("starting", endpoint_base + "/v1/chat/completions", port, True, diagnostic=diagnostic)
        if self.wait_until_ready(endpoint_base, startup_timeout, cancellation_event=cancellation_event):
            diagnostic.readiness_attempts = self._readiness_attempts
            diagnostic.duration_seconds = self._startup_duration()
            diagnostic.stdout = self._tail_text(self._stdout_lines)
            diagnostic.stderr = self._tail_text(self._stderr_lines)
            self.record_event("readiness", f"ready=true attempts={self._readiness_attempts}")
            self._log_stream_summary(diagnostic)
            self._state = RuntimeState("ready", endpoint_base + "/v1/chat/completions", port, True, diagnostic=diagnostic)
            return self._state

        if cancellation_event is not None and cancellation_event.is_set():
            diagnostic.readiness_attempts = self._readiness_attempts
            diagnostic.duration_seconds = self._startup_duration()
            diagnostic.error = "startup_cancelled"
            self.record_event("readiness", f"cancelled=true attempts={self._readiness_attempts}")
            self.stop()
            self._state = RuntimeState("stopped", None, port, False, "startup_cancelled", diagnostic)
            return self._state

        if self._process is not None and self._process.poll() is not None:
            return self._process_exit_state(endpoint_base, diagnostic)

        diagnostic.readiness_attempts = self._readiness_attempts
        diagnostic.duration_seconds = self._startup_duration()
        diagnostic.stdout = self._tail_text(self._stdout_lines)
        diagnostic.stderr = self._tail_text(self._stderr_lines)
        diagnostic.error = "startup_timeout"
        self.record_event("error", f"error=startup_timeout attempts={self._readiness_attempts}")
        self._log_stream_summary(diagnostic)
        self.stop()
        self._state = RuntimeState("failed", None, port, False, "startup_timeout", diagnostic)
        return self._state

    def start_launch_plan(
        self,
        plan: RuntimeLaunchPlan,
        timeout_seconds: int | None = None,
        *,
        cancellation_event: threading.Event | None = None,
    ) -> RuntimeState:
        return self.start(
            plan.model_path,
            plan.context_tokens,
            timeout_seconds,
            cancellation_event=cancellation_event,
            launch_plan=plan,
        )

    def stop(self) -> None:
        if self._process is not None and self._process.poll() is None:
            self.record_event("process", f"terminating_pid={self._process.pid}")
            self._process.terminate()
            try:
                self._process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self.record_event("process", f"killing_pid={self._process.pid}")
                self._process.kill()
                try:
                    self._process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
        self._join_log_readers(0.25)
        self._state = RuntimeState("stopped", None, None, False)

    def restart(
        self,
        model_path: Path,
        context_tokens: int,
        timeout_seconds: int | None = None,
        *,
        cancellation_event: threading.Event | None = None,
    ) -> RuntimeState:
        self.stop()
        return self.start(model_path, context_tokens, timeout_seconds, cancellation_event=cancellation_event)

    def restart_launch_plan(
        self,
        plan: RuntimeLaunchPlan,
        timeout_seconds: int | None = None,
        *,
        cancellation_event: threading.Event | None = None,
    ) -> RuntimeState:
        self.stop()
        return self.start_launch_plan(plan, timeout_seconds, cancellation_event=cancellation_event)

    def get_state(self) -> RuntimeState:
        if self._process is not None and self._process.poll() is not None and self._state.status in {"starting", "ready"}:
            diagnostic = self._state.diagnostic or RuntimeDiagnostic(port=self._state.port)
            endpoint_base = f"http://127.0.0.1:{self._state.port}" if self._state.port else ""
            return self._process_exit_state(endpoint_base, diagnostic)
        return self._state

    def wait_until_ready(
        self,
        endpoint_base_url: str,
        timeout_seconds: int | None = None,
        *,
        cancellation_event: threading.Event | None = None,
    ) -> bool:
        timeout = self._resolve_startup_timeout(timeout_seconds)
        deadline = time.monotonic() + timeout
        urls = (
            endpoint_base_url.rstrip("/") + "/v1/models",
            endpoint_base_url.rstrip("/") + "/health",
        )
        while time.monotonic() < deadline:
            if cancellation_event is not None and cancellation_event.is_set():
                self.record_event("readiness", f"cancelled=true attempts={self._readiness_attempts}")
                return False
            if self._process is not None and self._process.poll() is not None:
                self.record_event("readiness", f"process_exited_before_ready attempts={self._readiness_attempts}")
                return False
            self._readiness_attempts += 1
            for url in urls:
                try:
                    with urllib.request.urlopen(url, timeout=2) as response:
                        status_value = getattr(response, "status", None)
                        if status_value is None:
                            status_value = response.getcode()
                        status_code = int(status_value)
                        self.record_event(
                            "readiness",
                            f"attempt={self._readiness_attempts} url={url} status={status_code}",
                        )
                        if 200 <= status_code < 300 and url.endswith("/v1/models"):
                            return True
                except (urllib.error.URLError, TimeoutError, OSError) as exc:
                    self.record_event(
                        "readiness",
                        f"attempt={self._readiness_attempts} url={url} result={type(exc).__name__}",
                    )
            if cancellation_event is not None:
                if cancellation_event.wait(1):
                    self.record_event("readiness", f"cancelled=true attempts={self._readiness_attempts}")
                    return False
            else:
                time.sleep(1)
        return False

    def last_runtime_logs(self) -> list[str]:
        with self._log_lock:
            return list(self._runtime_logs)

    def last_runtime_log_text(self) -> str:
        return "\n".join(self.last_runtime_logs())

    def last_validation_result(self) -> RuntimeValidationResult | None:
        return self._last_validation

    def latest_loading_progress(self) -> int | None:
        for line in reversed(self.last_runtime_logs()):
            progress = parse_runtime_loading_progress(line)
            if progress is not None:
                return progress
        return None

    def record_event(self, source: str, message: str) -> None:
        self._append_runtime_log(source, message)

    def _resolve_startup_timeout(self, timeout_seconds: int | None) -> int:
        if timeout_seconds is not None:
            try:
                parsed = int(timeout_seconds)
            except (TypeError, ValueError):
                parsed = self.DEFAULT_STARTUP_TIMEOUT_SECONDS
            return max(120, min(1800, parsed))
        if self._settings is not None:
            return self._settings.ai_startup_timeout_seconds()
        return self.DEFAULT_STARTUP_TIMEOUT_SECONDS

    def _clear_runtime_logs(self) -> None:
        with self._log_lock:
            self._runtime_logs.clear()
            self._stdout_lines.clear()
            self._stderr_lines.clear()

    def _append_runtime_log(self, source: str, line: str) -> None:
        cleaned = str(line).rstrip()
        if not cleaned:
            return
        timestamp = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        with self._log_lock:
            self._runtime_logs.append(f"{timestamp} {source}: {cleaned}")
            if source == "stdout":
                self._stdout_lines.append(cleaned)
            elif source == "stderr":
                self._stderr_lines.append(cleaned)

    def _start_log_readers(self, process: subprocess.Popen[str]) -> None:
        self._log_threads = []
        for source, stream in (("stdout", process.stdout), ("stderr", process.stderr)):
            if stream is None:
                continue
            thread = threading.Thread(
                target=self._read_runtime_stream,
                args=(source, stream),
                name=f"RuntimeLogReader-{source}",
                daemon=True,
            )
            self._log_threads.append(thread)
            thread.start()

    def _read_runtime_stream(self, source: str, stream) -> None:
        try:
            for line in iter(stream.readline, ""):
                self._append_runtime_log(source, line)
        except OSError as exc:
            self._append_runtime_log("logging", f"stream={source} exception={type(exc).__name__}: {exc}")
        finally:
            try:
                stream.close()
            except OSError:
                pass

    def _join_log_readers(self, timeout_per_thread: float) -> None:
        for thread in self._log_threads:
            if thread.is_alive():
                thread.join(timeout=timeout_per_thread)

    def _process_exit_state(self, endpoint_base: str, diagnostic: RuntimeDiagnostic) -> RuntimeState:
        self._join_log_readers(0.25)
        native_exit_code = self._process.poll() if self._process is not None else None
        exit_code = _normalize_windows_exit_code(native_exit_code)
        stdout = self._tail_text(self._stdout_lines)
        stderr = self._tail_text(self._stderr_lines)
        error = self._classify_runtime_failure(exit_code, stderr, stdout)
        diagnostic.error = error
        diagnostic.exit_code = exit_code
        diagnostic.native_exit_code = native_exit_code
        diagnostic.duration_seconds = self._startup_duration()
        diagnostic.readiness_attempts = self._readiness_attempts
        diagnostic.stdout = stdout
        diagnostic.stderr = stderr
        self.record_event(
            "error",
            f"error={error} exit_code={exit_code} native_exit_code={native_exit_code} "
            f"duration_seconds={diagnostic.duration_seconds:.3f} readiness_attempts={self._readiness_attempts} "
            f"port={diagnostic.port} model={diagnostic.model_path} command={subprocess.list2cmdline(diagnostic.command)}",
        )
        self._log_stream_summary(diagnostic)
        self._state = RuntimeState("failed", endpoint_base + "/v1/chat/completions" if endpoint_base else None, diagnostic.port, False, error, diagnostic)
        return self._state

    def _validate_model(self, model_path: Path) -> tuple[str | None, int | None]:
        try:
            if not model_path.exists() or not model_path.is_file():
                return "model_missing", None
            size = model_path.stat().st_size
        except OSError:
            return "model_missing", None
        if model_path.name.lower().endswith(".part") or model_path.suffix.lower() != ".gguf":
            return "model_incomplete", size
        if size < self.MIN_PLAUSIBLE_MODEL_BYTES:
            return "model_incomplete", size
        return None, size

    def _diagnostic_from_validation(
        self,
        validation: RuntimeValidationResult | None,
        error: str,
        model_path: Path,
        model_size: int | None,
    ) -> RuntimeDiagnostic:
        if validation is None:
            return RuntimeDiagnostic(error=error, model_path=str(model_path), model_size=model_size)
        return RuntimeDiagnostic(
            error=error,
            command=validation.command,
            executable_path=str(validation.executable),
            runtime_directory=str(validation.executable.parent),
            working_directory=str(validation.working_directory or validation.executable.parent),
            model_path=str(model_path),
            model_size=model_size,
            stdout=validation.stdout,
            stderr=validation.stderr,
            exit_code=validation.exit_code,
            native_exit_code=validation.native_exit_code,
            exception_type=validation.exception_type,
            exception_message=validation.exception_message,
            errno=validation.errno,
            winerror=validation.winerror,
        )

    def _log_validation(self, validation: RuntimeValidationResult, label: str) -> None:
        self.record_event(
            "validation",
            f"{label} valid={validation.valid} error={validation.error} executable={validation.executable} "
            f"working_directory={validation.working_directory} probe={validation.probe_argument} "
            f"exit_code={validation.exit_code} native_exit_code={validation.native_exit_code} "
            f"exception_type={validation.exception_type} errno={validation.errno} winerror={validation.winerror}",
        )
        if validation.stdout:
            for line in validation.stdout.splitlines()[-20:]:
                self.record_event("validation_stdout", line)
        else:
            self.record_event("validation_stdout", "<empty>")
        if validation.stderr:
            for line in validation.stderr.splitlines()[-20:]:
                self.record_event("validation_stderr", line)
        else:
            self.record_event("validation_stderr", "<empty>")

    def _log_startup_metadata(self, diagnostic: RuntimeDiagnostic) -> None:
        self.record_event("system", f"timestamp={diagnostic.started_at}")
        self.record_event("system", f"application_version={APP_VERSION}")
        self.record_event("system", f"operating_system={platform.platform()}")
        self.record_event("system", f"architecture={platform.machine() or 'unknown'}")
        self.record_event("system", f"available_ram_gb={self._available_ram_gb():.2f}")
        if self._last_selected_asset_name:
            self.record_event("system", f"runtime_asset={self._last_selected_asset_name}")
        self.record_event("system", f"runtime_executable={diagnostic.executable_path}")
        self.record_event("system", f"runtime_directory={diagnostic.runtime_directory}")
        self.record_event("system", f"working_directory={diagnostic.working_directory}")
        self.record_event("system", f"model_path={diagnostic.model_path}")
        self.record_event("system", f"model_size={diagnostic.model_size}")
        self.record_event("system", f"command={subprocess.list2cmdline(diagnostic.command)}")
        self.record_event("system", f"host={diagnostic.host}")
        self.record_event("system", f"port={diagnostic.port}")
        self.record_event("system", f"startup_timeout_seconds={diagnostic.startup_timeout_seconds}")
        self.record_event(
            "selection",
            f"backend={diagnostic.backend_id} runtime_variant={diagnostic.runtime_variant_id} "
            f"host_architecture={diagnostic.host_architecture} executable_architecture={diagnostic.executable_architecture} "
            f"emulation={diagnostic.requires_emulation} device={diagnostic.device_id} "
            f"cpu_threads={diagnostic.cpu_threads} gpu_layers={diagnostic.gpu_layers} "
            f"environment_keys={','.join(diagnostic.environment_keys) or 'none'} "
            f"reasons={','.join(diagnostic.selection_reasons) or 'legacy'}",
        )

    def _log_stream_summary(self, diagnostic: RuntimeDiagnostic) -> None:
        stdout_lines = diagnostic.stdout.splitlines()
        stderr_lines = diagnostic.stderr.splitlines()
        stdout_tail = stdout_lines[-1] if stdout_lines else "<empty>"
        stderr_tail = stderr_lines[-1] if stderr_lines else "<empty>"
        exit_code = diagnostic.exit_code if diagnostic.exit_code is not None else "<running>"
        error = diagnostic.error or "<none>"
        self.record_event(
            "diagnostic",
            f"stdout_lines={len(stdout_lines)} stdout_tail={stdout_tail} "
            f"stderr_lines={len(stderr_lines)} stderr_tail={stderr_tail} exit_code={exit_code} error={error}",
        )

    def _classify_oserror(self, exc: OSError) -> str:
        winerror = getattr(exc, "winerror", None)
        errno_value = getattr(exc, "errno", None)
        text = str(exc).lower()
        if winerror in {5} or errno_value in {13} or "access is denied" in text or "permission denied" in text:
            return "runtime_access_denied"
        if winerror in {126, 127} or "dll" in text and ("not found" in text or "missing" in text):
            return "runtime_dll_missing"
        if winerror in {193, 216} or "not a valid win32" in text or "exec format" in text:
            return "runtime_incompatible"
        if winerror in {2, 3} or errno_value in {2}:
            return "runtime_missing"
        return "start_failed"

    def _classify_runtime_failure(self, exit_code: int | None, stderr: str, stdout: str = "") -> str:
        text = f"{stderr}\n{stdout}".lower()
        if exit_code == -1073741515 or any(token in text for token in ("missing dll", "dll was not found", "cannot find dll")):
            return "runtime_dll_missing"
        if exit_code == -1073741701 or any(token in text for token in ("0xc000007b", "bad image", "invalid win32", "wrong architecture")):
            return "runtime_incompatible"
        if exit_code == -1073741801 or any(token in text for token in ("out of memory", "not enough memory", "failed to allocate", "cannot allocate memory")):
            return "insufficient_memory"
        if any(token in text for token in ("address already in use", "failed to bind", "bind failed", "port is already")):
            return "port_unavailable"
        if any(token in text for token in ("unknown argument", "unknown option", "unrecognized option", "invalid argument: --")):
            return "runtime_flag_unsupported"
        if exit_code not in {None, 0}:
            return "runtime_process_exit_nonzero"
        return "runtime_process_exited"

    def _is_fatal_runtime_exit(self, exit_code: int | None) -> bool:
        return exit_code in {-1073741515, -1073741701, -1073741801}

    def _is_ignored_runtime_path(self, path: Path) -> bool:
        ignored_prefixes = ("_extracting", "_installing", "_backup")
        for part in path.parts:
            lowered = part.lower()
            if lowered.endswith(".part") or lowered.startswith(ignored_prefixes) or ".backup" in lowered:
                return True
        return False

    def _is_legacy_runtime_path(self, path: Path) -> bool:
        return os.path.normcase(str(path.resolve(strict=False))) == os.path.normcase(str(self.legacy_runtime_path().resolve(strict=False)))

    def _quarantine_legacy_runtime(self, path: Path, reason: str) -> None:
        quarantine_dir = self.managed_runtime_dir() / "incomplete"
        quarantine_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        destination = quarantine_dir / f"{path.name}.{timestamp}.{uuid.uuid4().hex[:8]}.incomplete"
        try:
            path.replace(destination)
            self.record_event("migration", f"legacy_runtime_quarantined source={path} destination={destination} reason={reason}")
            if self._settings is not None:
                configured = self._settings.ai_runtime_path()
                if configured and os.path.normcase(str(Path(configured).resolve(strict=False))) == os.path.normcase(str(path.resolve(strict=False))):
                    self._settings.set_ai_runtime_path("")
        except OSError as exc:
            self.record_event(
                "migration",
                f"legacy_runtime_quarantine_failed path={path} reason={reason} exception={type(exc).__name__}: {exc}",
            )

    def _remove_invalid_legacy_after_install(self) -> None:
        legacy = self.legacy_runtime_path()
        if not legacy.exists():
            return
        validation = self.validate_runtime_installation(legacy, use_cache=False)
        if not validation.valid:
            self._quarantine_legacy_runtime(legacy, validation.error or "runtime_incomplete")

    def _store_validation_cache(self, path: Path, validation: RuntimeValidationResult) -> None:
        try:
            resolved = Path(path).resolve(strict=False)
            stat_result = resolved.stat()
        except OSError:
            return
        cached = RuntimeValidationResult(
            validation.valid,
            resolved,
            error=validation.error,
            probe_argument=validation.probe_argument,
            command=[str(resolved), validation.probe_argument] if validation.probe_argument else [],
            working_directory=resolved.parent,
            stdout=validation.stdout,
            stderr=validation.stderr,
            exit_code=validation.exit_code,
            native_exit_code=validation.native_exit_code,
            exception_type=validation.exception_type,
            exception_message=validation.exception_message,
            errno=validation.errno,
            winerror=validation.winerror,
        )
        key = (os.path.normcase(str(resolved)), stat_result.st_size, stat_result.st_mtime_ns)
        self._validation_cache[key] = cached

    def _cpu_supports_avx2(self) -> bool:
        if not sys.platform.startswith("win"):
            return False
        try:
            return bool(ctypes.windll.kernel32.IsProcessorFeaturePresent(40))
        except (AttributeError, OSError, ValueError):
            return False

    def _available_ram_gb(self) -> float:
        if not sys.platform.startswith("win"):
            return 0.0
        try:
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = MEMORYSTATUSEX()
            status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return status.ullAvailPhys / (1024**3)
        except (AttributeError, OSError, ValueError):
            pass
        return 0.0

    def _probe_runtime_devices(self, executable: Path) -> tuple[str, ...]:
        command = [str(executable), "--list-devices"]
        try:
            creationflags = subprocess.CREATE_NO_WINDOW if sys.platform.startswith("win") else 0
            completed = subprocess.run(
                command,
                cwd=str(executable.parent),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.RUNTIME_VALIDATION_TIMEOUT_SECONDS,
                shell=False,
                creationflags=creationflags,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return ()
        devices: list[str] = []
        for line in f"{completed.stdout}\n{completed.stderr}".splitlines():
            cleaned = line.strip()
            if not cleaned:
                continue
            # llama.cpp prints identifiers such as "Vulkan0: ...". Only the
            # identifier is safe to feed back to --device.
            match = re.match(r"^([A-Za-z][A-Za-z0-9_.-]*\d+)\s*:", cleaned)
            if match:
                devices.append(match.group(1))
        return tuple(dict.fromkeys(devices[:32]))

    def _safe_directory_component(self, value: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip()).strip("._")
        if not cleaned or cleaned.startswith("_"):
            raise ValueError("runtime_directory_component_invalid")
        return cleaned

    def _startup_duration(self) -> float:
        if self._process_started_monotonic is None:
            return 0.0
        return max(0.0, time.monotonic() - self._process_started_monotonic)

    def _tail_text(self, lines: deque[str], limit: int = 100) -> str:
        return "\n".join(list(lines)[-limit:])


def _normalize_windows_exit_code(exit_code: int | None) -> int | None:
    if exit_code is None:
        return None
    if exit_code > 0x7FFFFFFF:
        return exit_code - 0x100000000
    return exit_code


def _coerce_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def parse_runtime_loading_progress(line: str) -> int | None:
    if not line:
        return None
    match = re.search(r"\bloaded\s+(\d+)\s*/\s*(\d+)\b", line, re.IGNORECASE)
    if not match:
        return None
    loaded = int(match.group(1))
    total = int(match.group(2))
    if total <= 0:
        return None
    return max(0, min(100, round((loaded / total) * 100)))
