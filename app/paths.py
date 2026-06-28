from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QStandardPaths


class AppPaths:
    """Resolve and create local application data paths."""

    def __init__(self) -> None:
        base_path = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        if not base_path:
            base_path = str(Path.home() / "AppData" / "Local" / "JW PubliStudy")
        self._app_data_dir = Path(base_path)

    @property
    def app_data_dir(self) -> Path:
        self._app_data_dir.mkdir(parents=True, exist_ok=True)
        return self._app_data_dir

    @property
    def publications_dir(self) -> Path:
        path = self.app_data_dir / "publications"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def metadata_file(self) -> Path:
        return self.app_data_dir / "publications.json"

    @property
    def index_dir(self) -> Path:
        path = self.app_data_dir / "index"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def chunks_dir(self) -> Path:
        path = self.index_dir / "chunks"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def index_manifest_file(self) -> Path:
        return self.index_dir / "index_manifest.json"

    @property
    def chat_history_file(self) -> Path:
        return self.app_data_dir / "chat_history.json"

    @property
    def logs_dir(self) -> Path:
        path = self.app_data_dir / "logs"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def models_dir(self) -> Path:
        path = self.app_data_dir / "models"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def runtime_dir(self) -> Path:
        path = self.app_data_dir / "runtime"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def ensure_all_dirs(self) -> None:
        self.app_data_dir.mkdir(parents=True, exist_ok=True)
        self.publications_dir.mkdir(parents=True, exist_ok=True)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.chunks_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
