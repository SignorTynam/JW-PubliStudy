from __future__ import annotations

import hashlib
import urllib.error
import urllib.request
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot


class DownloadWorker(QObject):
    progress_changed = Signal(int, int, int)
    status_changed = Signal(str)
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, url: str, target_path: Path, sha256: str | None = None) -> None:
        super().__init__()
        self._url = url
        self._target_path = Path(target_path)
        self._sha256 = sha256
        self._cancelled = False

    @Slot()
    def run(self) -> None:
        part_path = self._target_path.with_suffix(self._target_path.suffix + ".part")
        try:
            self._target_path.parent.mkdir(parents=True, exist_ok=True)
            part_path.unlink(missing_ok=True)
            self.status_changed.emit("download_started")
            request = urllib.request.Request(self._url, headers={"User-Agent": "JW-PubliStudy"})
            with urllib.request.urlopen(request, timeout=30) as response:
                total = int(response.headers.get("Content-Length") or 0)
                downloaded = 0
                with part_path.open("wb") as file:
                    while not self._cancelled:
                        block = response.read(1024 * 1024)
                        if not block:
                            break
                        file.write(block)
                        downloaded += len(block)
                        percent = int((downloaded / total) * 100) if total else 0
                        self.progress_changed.emit(percent, downloaded, total)
            if self._cancelled:
                part_path.unlink(missing_ok=True)
                self.failed.emit("download_cancelled")
                return
            if self._sha256 and self._sha256_of(part_path).lower() != self._sha256.lower():
                part_path.unlink(missing_ok=True)
                self.failed.emit("checksum_failed")
                return
            part_path.replace(self._target_path)
            self.progress_changed.emit(100, self._target_path.stat().st_size, self._target_path.stat().st_size)
            self.finished.emit(str(self._target_path))
        except urllib.error.HTTPError:
            part_path.unlink(missing_ok=True)
            self.failed.emit("http_error")
        except urllib.error.URLError:
            part_path.unlink(missing_ok=True)
            self.failed.emit("network_error")
        except OSError:
            part_path.unlink(missing_ok=True)
            self.failed.emit("file_error")

    def cancel(self) -> None:
        self._cancelled = True

    def _sha256_of(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for block in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
