from __future__ import annotations

import hashlib
import shutil
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

    def custom_models_dir(self) -> Path:
        path = self.models_dir() / "custom"
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

    def is_custom_model_ready(self, path: str) -> bool:
        return self.get_custom_model_state(path).verified

    def get_custom_model_state(self, path: str) -> ModelLocalState:
        model_path = Path(path) if path else Path()
        exists = bool(path) and model_path.is_file()
        size = 0
        verified = False
        error = None
        if exists:
            try:
                size = model_path.stat().st_size
                verified = model_path.suffix.lower() == ".gguf" and size >= self.MIN_PLAUSIBLE_MODEL_BYTES
            except OSError:
                verified = False
        if path and not exists:
            error = "model_missing"
        elif exists and not verified:
            error = "invalid_model"
        return ModelLocalState("custom", exists, model_path, size, verified, error)

    def import_custom_model(self, source_path: Path, display_name: str | None = None) -> Path:
        source = Path(source_path)
        if source.suffix.lower() != ".gguf":
            raise ValueError("invalid_model_file")
        if not source.is_file():
            raise FileNotFoundError("model_file_missing")
        if source.stat().st_size < self.MIN_PLAUSIBLE_MODEL_BYTES:
            raise ValueError("invalid_model_file")

        target = self._available_custom_path(source.name, source.stat().st_size)
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

    def _available_custom_path(self, filename: str, source_size: int) -> Path:
        target = self.custom_models_dir() / Path(filename).name
        if not target.exists() or target.stat().st_size == source_size:
            return target
        stem = target.stem
        suffix = target.suffix
        for index in range(1, 1000):
            candidate = target.with_name(f"{stem}-{index}{suffix}")
            if not candidate.exists() or candidate.stat().st_size == source_size:
                return candidate
        raise OSError("custom_model_name_exhausted")

    def _sha256(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for block in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
