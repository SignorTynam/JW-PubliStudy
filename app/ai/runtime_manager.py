from __future__ import annotations

import socket
import subprocess
import shutil
import sys
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
import re

from app.settings import AppSettings


@dataclass(frozen=True)
class RuntimeSpec:
    id: str
    display_name: str
    executable_name: str
    download_url: str | None
    sha256: str | None


@dataclass
class RuntimeState:
    status: str
    endpoint_url: str | None
    port: int | None
    process_running: bool
    error: str | None = None


DEFAULT_RUNTIME_SPEC = RuntimeSpec(
    id="llama_cpp_server",
    display_name="llama.cpp server",
    executable_name="llama-server.exe" if sys.platform.startswith("win") else "llama-server",
    download_url="https://api.github.com/repos/ggml-org/llama.cpp/releases/latest",
    sha256=None,
)


class RuntimeManager:
    def __init__(self, data_dir: Path, settings: AppSettings | None = None) -> None:
        self._data_dir = Path(data_dir)
        self._settings = settings
        self._process: subprocess.Popen[str] | None = None
        self._state = RuntimeState("not_installed", None, None, False)

    def find_runtime_executable(self) -> Path | None:
        if self._settings is not None and self._settings.ai_use_custom_runtime():
            custom_path = Path(self._settings.ai_custom_runtime_path())
            return custom_path if custom_path.is_file() else None
        candidates = [
            Path.cwd() / "runtime" / DEFAULT_RUNTIME_SPEC.executable_name,
            self._data_dir / "runtime" / DEFAULT_RUNTIME_SPEC.executable_name,
        ]
        configured = self._settings.ai_runtime_path() if self._settings is not None else ""
        if configured:
            candidates.insert(0, Path(configured))
        for path in candidates:
            if path.is_file():
                return path
        return None

    def is_runtime_available(self) -> bool:
        return self.find_runtime_executable() is not None

    def runtime_dir(self) -> Path:
        path = self._data_dir / "runtime"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_runtime_path(self) -> Path:
        return self.runtime_dir() / DEFAULT_RUNTIME_SPEC.executable_name

    def supports_runtime_download(self) -> bool:
        return sys.platform.startswith("win")

    def find_latest_windows_asset(self, release_json: dict) -> str | None:
        assets = release_json.get("assets")
        if not isinstance(assets, list):
            return None
        patterns = (
            re.compile(r".*bin-win-cpu-x64\.zip$", re.IGNORECASE),
            re.compile(r".*bin-win-avx2-x64\.zip$", re.IGNORECASE),
            re.compile(r".*win.*cpu.*x64.*\.zip$", re.IGNORECASE),
            re.compile(r".*win.*x64.*\.zip$", re.IGNORECASE),
        )
        for pattern in patterns:
            for asset in assets:
                if not isinstance(asset, dict):
                    continue
                name = str(asset.get("name") or "")
                url = str(asset.get("browser_download_url") or "")
                if url and pattern.match(name):
                    return url
        return None

    def install_runtime_from_zip(self, zip_path: Path) -> Path:
        target = self.get_runtime_path()
        extract_root = self.runtime_dir() / "_extracting"
        shutil.rmtree(extract_root, ignore_errors=True)
        extract_root.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(zip_path) as archive:
                archive.extractall(extract_root)
            executable = next(extract_root.rglob(DEFAULT_RUNTIME_SPEC.executable_name), None)
            if executable is None:
                raise RuntimeError("runtime_executable_missing")
            if not self.is_runtime_ready_file(executable):
                raise RuntimeError("runtime_executable_missing")
            temp_target = target.with_suffix(target.suffix + ".part")
            shutil.copy2(executable, temp_target)
            temp_target.replace(target)
        finally:
            shutil.rmtree(extract_root, ignore_errors=True)
        return target

    def is_runtime_ready_file(self, path: Path) -> bool:
        try:
            return path.is_file() and path.stat().st_size > 1024
        except OSError:
            return False

    def import_runtime_executable(self, source_path: Path) -> Path:
        source = Path(source_path)
        if sys.platform.startswith("win") and source.suffix.lower() != ".exe":
            raise ValueError("invalid_runtime_file")
        if not source.is_file():
            raise FileNotFoundError("runtime_file_missing")
        target = self.get_runtime_path()
        if target.exists() and target.stat().st_size == source.stat().st_size:
            return target
        temp_target = target.with_suffix(target.suffix + ".part")
        try:
            shutil.copy2(source, temp_target)
            temp_target.replace(target)
        except OSError:
            temp_target.unlink(missing_ok=True)
            raise
        return target

    def find_free_port(self) -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    def build_command(self, model_path: Path, port: int, context_tokens: int) -> list[str]:
        executable = self.find_runtime_executable()
        if executable is None:
            executable = self._data_dir / "runtime" / DEFAULT_RUNTIME_SPEC.executable_name
        return [
            str(executable),
            "--model",
            str(model_path),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--ctx-size",
            str(context_tokens),
        ]

    def start(self, model_path: Path, context_tokens: int) -> RuntimeState:
        executable = self.find_runtime_executable()
        if executable is None:
            self._state = RuntimeState("not_installed", None, None, False, "runtime_missing")
            return self._state
        if self._process is not None and self._process.poll() is None and self._state.endpoint_url:
            self._state.status = "ready"
            self._state.process_running = True
            return self._state
        port = self.find_free_port()
        endpoint_base = f"http://127.0.0.1:{port}"
        command = self.build_command(model_path, port, context_tokens)
        try:
            creationflags = subprocess.CREATE_NO_WINDOW if sys.platform.startswith("win") else 0
            self._process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
                creationflags=creationflags,
            )
        except OSError:
            self._state = RuntimeState("failed", None, None, False, "start_failed")
            return self._state
        self._state = RuntimeState("starting", endpoint_base + "/v1/chat/completions", port, True)
        if self.wait_until_ready(endpoint_base):
            self._state = RuntimeState("ready", endpoint_base + "/v1/chat/completions", port, True)
            return self._state
        self.stop()
        self._state = RuntimeState("failed", None, port, False, "readiness_timeout")
        return self._state

    def stop(self) -> None:
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self._process.kill()
        self._state = RuntimeState("stopped", None, None, False)

    def restart(self, model_path: Path, context_tokens: int) -> RuntimeState:
        self.stop()
        return self.start(model_path, context_tokens)

    def get_state(self) -> RuntimeState:
        if self._process is not None and self._process.poll() is not None and self._state.status in {"starting", "ready"}:
            self._state = RuntimeState("failed", self._state.endpoint_url, self._state.port, False, "process_exited")
        return self._state

    def wait_until_ready(self, endpoint_base_url: str, timeout_seconds: int = 120) -> bool:
        deadline = time.monotonic() + timeout_seconds
        url = endpoint_base_url.rstrip("/") + "/v1/models"
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=2) as response:
                    if 200 <= response.status < 300:
                        return True
            except (urllib.error.URLError, TimeoutError, OSError):
                time.sleep(1)
        return False
