from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from app.ai.runtime_manager import RuntimeManager
from app.ai.runtime_catalog import RuntimeResolution


class RuntimeDownloadWorker(QObject):
    progress_changed = Signal(int, int, int)
    status_changed = Signal(str)
    finished = Signal(str)
    failed = Signal(str)

    LATEST_RELEASE_URL = "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest"

    def __init__(self, runtime_manager: RuntimeManager, resolution: RuntimeResolution | None = None) -> None:
        super().__init__()
        self._runtime_manager = runtime_manager
        self._resolution = resolution
        self._cancellation_event = threading.Event()

    @Slot()
    def run(self) -> None:
        zip_path: Path | None = None
        try:
            self.status_changed.emit("resolving_runtime_release")
            release = self._load_release_json() if self._resolution is None else None
            asset_url = (
                self._runtime_manager.find_latest_windows_asset(release or {})
                if self._resolution is None
                else self._resolution.asset_url
            )
            if not asset_url:
                self._runtime_manager.record_event("download", "runtime_asset_not_found")
                self.failed.emit("runtime_asset_not_found")
                return
            self._runtime_manager.record_event(
                "download",
                f"release={self._release_tag(release)} asset={self._asset_name()}",
            )

            self.status_changed.emit("downloading_runtime")
            archive_name = self._resolution.variant.id if self._resolution else "llama-runtime"
            zip_path = self._runtime_manager.runtime_dir() / f"{archive_name}.zip.part"
            self._download(asset_url, zip_path)
            if self._cancellation_event.is_set():
                self.failed.emit("setup_cancelled")
                return
            self._runtime_manager.record_event("download", f"archive_path={zip_path} bytes={zip_path.stat().st_size}")

            self.status_changed.emit("extracting_runtime")
            if self._resolution is None:
                runtime_path = self._runtime_manager.install_runtime_from_zip(zip_path)
            else:
                runtime_path = self._runtime_manager.install_runtime_variant_from_zip(
                    zip_path,
                    self._resolution.variant.id,
                    self._resolution.release_tag or "unknown",
                )
            self.status_changed.emit("runtime_ready")
            self.finished.emit(str(runtime_path))
        except UnsupportedOSError:
            self._runtime_manager.record_event("download", "runtime_download_unsupported_os")
            self.failed.emit("runtime_download_unsupported_os")
        except zipfile.BadZipFile as exc:
            self._runtime_manager.record_event("download", f"runtime_zip_invalid exception={type(exc).__name__}: {exc}")
            self.failed.emit("runtime_zip_invalid")
        except RuntimeError as exc:
            self._runtime_manager.record_event("download", f"runtime_installation_failed error={exc}")
            self.failed.emit(str(exc))
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            self._runtime_manager.record_event(
                "download",
                f"runtime_download_failed exception_type={type(exc).__name__} message={exc} "
                f"errno={getattr(exc, 'errno', None)} winerror={getattr(exc, 'winerror', None)}",
            )
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
                    if self._cancellation_event.is_set():
                        return
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    file.write(block)
                    downloaded += len(block)
                    percent = int((downloaded / total) * 100) if total else 0
                    self.progress_changed.emit(percent, downloaded, total)

    def cancel(self) -> None:
        self._cancellation_event.set()

    def _release_tag(self, release: dict | None) -> str:
        if self._resolution is not None:
            return self._resolution.release_tag or "unknown"
        return str((release or {}).get("tag_name") or "unknown")

    def _asset_name(self) -> str:
        if self._resolution is not None:
            return self._resolution.asset_name or "unknown"
        return self._runtime_manager.last_selected_asset_name() or "unknown"


class UnsupportedOSError(Exception):
    pass
