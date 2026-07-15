from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from app.ai.hardware_profile import HardwareProfile, get_hardware_profile, profile_to_dict
from app.ai.runtime_catalog import LLAMA_CPP_RELEASE_API, RuntimeResolution, resolve_runtime_assets


@dataclass(frozen=True)
class AutomaticConfigurationResult:
    profile: HardwareProfile
    resolutions: tuple[RuntimeResolution, ...]
    rejected: tuple[RuntimeResolution, ...]


def order_runtime_resolutions(resolutions: list[RuntimeResolution]) -> list[RuntimeResolution]:
    """Prefer verified release assets, native architecture, and catalog priority."""
    return sorted(
        resolutions,
        key=lambda item: (
            not item.available,
            item.requires_emulation,
            item.variant.experimental,
            -item.variant.priority,
            item.variant.id,
        ),
    )


def save_hardware_profile(profile: HardwareProfile) -> Path:
    target = profile.data_dir / "ai_hardware_profile.json"
    _write_json_atomic(target, profile_to_dict(profile))
    return target


def save_backend_selection(data_dir: Path, payload: dict[str, object]) -> Path:
    target = Path(data_dir) / "ai_backend_selection.json"
    _write_json_atomic(target, payload)
    return target


def _write_json_atomic(target: Path, payload: dict[str, object]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(target)


class AutomaticConfigurationWorker(QObject):
    status_changed = Signal(str)
    completed = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, data_dir: Path, *, experimental_enabled: bool = False) -> None:
        super().__init__()
        self._data_dir = Path(data_dir)
        self._experimental_enabled = experimental_enabled
        self._cancellation_event = threading.Event()

    @Slot()
    def run(self) -> None:
        try:
            self.status_changed.emit("detecting_hardware")
            profile = get_hardware_profile(self._data_dir, detect_devices=True)
            if self._cancelled():
                return
            save_hardware_profile(profile)

            self.status_changed.emit("evaluating_backends")
            release = self._load_release_json()
            if self._cancelled():
                return
            resolutions = order_runtime_resolutions(
                resolve_runtime_assets(
                    release,
                    profile,
                    experimental_enabled=self._experimental_enabled,
                )
            )
            available = tuple(item for item in resolutions if item.available)
            rejected = tuple(item for item in resolutions if not item.available)
            if not available:
                self.failed.emit("runtime_asset_not_found")
                return
            self.status_changed.emit("selecting_model")
            self.completed.emit(AutomaticConfigurationResult(profile, available, rejected))
        except (OSError, urllib.error.URLError, json.JSONDecodeError):
            if not self._cancelled():
                self.failed.emit("runtime_download_failed")

    def request_cancel(self) -> None:
        self._cancellation_event.set()

    def _cancelled(self) -> bool:
        if not self._cancellation_event.is_set():
            return False
        self.cancelled.emit()
        return True

    def _load_release_json(self) -> dict:
        request = urllib.request.Request(LLAMA_CPP_RELEASE_API, headers={"User-Agent": "JW-PubliStudy"})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
