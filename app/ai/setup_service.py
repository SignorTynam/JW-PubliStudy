from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import QObject, QThread, Signal, Slot

from app.ai.download_worker import DownloadWorker
from app.ai.hardware_check import get_hardware_info
from app.ai.model_catalog import LocalModelSpec, recommend_model
from app.ai.model_manager import ModelManager
from app.ai.runtime_manager import RuntimeManager
from app.settings import AppSettings


class LocalAISetupService(QObject):
    status_changed = Signal(str)
    step_changed = Signal(str)
    progress_changed = Signal(int)
    error_occurred = Signal(str)
    finished = Signal()

    def __init__(self, settings: AppSettings, model_manager: ModelManager, runtime_manager: RuntimeManager) -> None:
        super().__init__()
        self._settings = settings
        self._model_manager = model_manager
        self._runtime_manager = runtime_manager
        self._download_thread: QThread | None = None
        self._download_worker: DownloadWorker | None = None
        self._runtime_thread: QThread | None = None
        self._runtime_worker: RuntimeStartWorker | None = None

    def recommended_model(self) -> LocalModelSpec:
        info = get_hardware_info(self._model_manager.models_dir().parent)
        return recommend_model(info.total_ram_gb)

    @Slot()
    def configure_automatically(self) -> None:
        self.status_changed.emit("checking_hardware")
        info = get_hardware_info(self._model_manager.models_dir().parent)
        spec = recommend_model(info.total_ram_gb)
        self._settings.set_ai_mode("auto")
        self._settings.set_ai_selected_model_id(spec.id)
        self.status_changed.emit("model_recommended")
        if info.free_disk_gb < spec.size_gb + 1:
            self.error_occurred.emit("disk_space_insufficient")
            return
        if not self._model_manager.is_model_ready(spec):
            self.download_model(spec, start_after_download=True)
            return
        self.start_runtime(spec)

    def download_model(self, spec: LocalModelSpec, start_after_download: bool = False) -> None:
        if self._is_placeholder_url(spec.download_url):
            self._settings.set_ai_last_status("failed")
            self.error_occurred.emit("download_url_placeholder")
            return
        target = self._model_manager.get_model_path(spec)
        self.status_changed.emit("download_model")
        self._download_thread = QThread()
        self._download_worker = DownloadWorker(spec.download_url, target, spec.sha256)
        self._download_worker.moveToThread(self._download_thread)
        self._download_thread.started.connect(self._download_worker.run)
        self._download_worker.progress_changed.connect(lambda percent, _done, _total: self.progress_changed.emit(percent))
        self._download_worker.status_changed.connect(self.status_changed.emit)
        self._download_worker.failed.connect(self._on_download_failed)
        if start_after_download:
            self._download_worker.finished.connect(lambda _path: self.start_runtime(spec))
        else:
            self._download_worker.finished.connect(lambda _path: self.finished.emit())
        self._download_worker.finished.connect(self._download_thread.quit)
        self._download_worker.failed.connect(self._download_thread.quit)
        self._download_thread.finished.connect(self._download_thread.deleteLater)
        self._download_thread.start()

    def start_runtime(self, spec: LocalModelSpec) -> None:
        self.status_changed.emit("starting_runtime")
        if not self._model_manager.is_model_ready(spec):
            self.error_occurred.emit("model_missing")
            return
        self._runtime_thread = QThread()
        self._runtime_worker = RuntimeStartWorker(
            self._runtime_manager,
            self._model_manager.get_model_path(spec),
            spec.context_tokens,
        )
        self._runtime_worker.moveToThread(self._runtime_thread)
        self._runtime_thread.started.connect(self._runtime_worker.run)
        self._runtime_worker.finished.connect(self._on_runtime_started)
        self._runtime_worker.failed.connect(self._on_runtime_failed)
        self._runtime_worker.finished.connect(self._runtime_thread.quit)
        self._runtime_worker.failed.connect(self._runtime_thread.quit)
        self._runtime_thread.finished.connect(self._runtime_thread.deleteLater)
        self._runtime_thread.start()

    def _on_download_failed(self, error: str) -> None:
        self._settings.set_ai_last_status("failed")
        self.error_occurred.emit(error)

    def _on_runtime_started(self, endpoint: str) -> None:
        self._settings.set_ai_runtime_endpoint(endpoint)
        self._settings.set_ai_last_status("ready")
        self.status_changed.emit("ready")
        self.finished.emit()

    def _on_runtime_failed(self, error: str) -> None:
        self._settings.set_ai_last_status("failed")
        self.error_occurred.emit(error)

    def _is_placeholder_url(self, url: str) -> bool:
        try:
            host = urlparse(url).hostname or ""
        except ValueError:
            return True
        return host.lower() in {"example.com", "www.example.com"}


class RuntimeStartWorker(QObject):
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, runtime_manager: RuntimeManager, model_path: Path, context_tokens: int) -> None:
        super().__init__()
        self._runtime_manager = runtime_manager
        self._model_path = model_path
        self._context_tokens = context_tokens

    @Slot()
    def run(self) -> None:
        state = self._runtime_manager.start(self._model_path, self._context_tokens)
        if state.status == "ready" and state.endpoint_url:
            self.finished.emit(state.endpoint_url)
            return
        self.failed.emit(state.error or "runtime_start_failed")
