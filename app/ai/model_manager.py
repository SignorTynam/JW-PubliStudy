from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from app.ai.model_catalog import LocalModelSpec


@dataclass
class ModelLocalState:
    model_id: str
    exists: bool
    path: Path
    size_bytes: int
    verified: bool
    error: str | None = None


class ModelManager:
    MIN_PLAUSIBLE_MODEL_BYTES = 1024 * 1024

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = Path(data_dir)

    def models_dir(self) -> Path:
        path = self._data_dir / "models"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_model_path(self, spec: LocalModelSpec) -> Path:
        return self.models_dir() / spec.filename

    def get_local_state(self, spec: LocalModelSpec) -> ModelLocalState:
        path = self.get_model_path(spec)
        exists = path.exists()
        size = path.stat().st_size if exists else 0
        verified = self.verify_model(spec) if exists else False
        error = None if verified or not exists else "invalid_model"
        return ModelLocalState(spec.id, exists, path, size, verified, error)

    def is_model_ready(self, spec: LocalModelSpec) -> bool:
        return self.get_local_state(spec).verified

    def verify_model(self, spec: LocalModelSpec) -> bool:
        path = self.get_model_path(spec)
        if not path.is_file():
            return False
        try:
            if path.stat().st_size < self.MIN_PLAUSIBLE_MODEL_BYTES:
                return False
        except OSError:
            return False
        if not spec.sha256:
            return True
        return self._sha256(path).lower() == spec.sha256.lower()

    def delete_model(self, spec: LocalModelSpec) -> None:
        self.get_model_path(spec).unlink(missing_ok=True)
        self.get_model_path(spec).with_suffix(self.get_model_path(spec).suffix + ".part").unlink(missing_ok=True)

    def _sha256(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for block in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

