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
