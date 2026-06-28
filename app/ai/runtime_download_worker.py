from __future__ import annotations

import json
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from app.ai.runtime_manager import RuntimeManager


class RuntimeDownloadWorker(QObject):
    progress_changed = Signal(int, int, int)
    status_changed = Signal(str)
    finished = Signal(str)
    failed = Signal(str)

    LATEST_RELEASE_URL = "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest"

    def __init__(self, runtime_manager: RuntimeManager) -> None:
        super().__init__()
        self._runtime_manager = runtime_manager

    @Slot()
    def run(self) -> None:
        zip_path: Path | None = None
        try:
            self.status_changed.emit("resolving_runtime_release")
            release = self._load_release_json()
            asset_url = self._runtime_manager.find_latest_windows_asset(release)
            if not asset_url:
                self.failed.emit("runtime_asset_not_found")
                return

            self.status_changed.emit("downloading_runtime")
            zip_path = self._runtime_manager.runtime_dir() / "llama-runtime.zip.part"
            self._download(asset_url, zip_path)

            self.status_changed.emit("extracting_runtime")
            runtime_path = self._runtime_manager.install_runtime_from_zip(zip_path)
            self.status_changed.emit("runtime_ready")
            self.finished.emit(str(runtime_path))
        except UnsupportedOSError:
            self.failed.emit("runtime_download_unsupported_os")
        except zipfile.BadZipFile:
            self.failed.emit("runtime_zip_invalid")
        except RuntimeError as exc:
            self.failed.emit(str(exc))
        except (OSError, urllib.error.URLError, json.JSONDecodeError):
            self.failed.emit("runtime_download_failed")
        finally:
            if zip_path is not None:
                zip_path.unlink(missing_ok=True)

    def _load_release_json(self) -> dict:
        if not self._runtime_manager.supports_runtime_download():
            raise UnsupportedOSError
        request = urllib.request.Request(self.LATEST_RELEASE_URL, headers={"User-Agent": "JW-PubliStudy"})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def _download(self, url: str, target_path: Path) -> None:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(url, headers={"User-Agent": "JW-PubliStudy"})
        with urllib.request.urlopen(request, timeout=30) as response:
            total = int(response.headers.get("Content-Length") or 0)
            downloaded = 0
            with target_path.open("wb") as file:
                while True:
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    file.write(block)
                    downloaded += len(block)
                    percent = int((downloaded / total) * 100) if total else 0
                    self.progress_changed.emit(percent, downloaded, total)


class UnsupportedOSError(Exception):
    pass
