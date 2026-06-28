from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.models.document_chunk import DocumentChunk
from app.models.publication import Publication
from app.paths import AppPaths


class IndexRepositoryError(Exception):
    """Raised when local index persistence fails."""


class IndexRepository:
    MANIFEST_VERSION = 1

    def __init__(self, paths: AppPaths | None = None) -> None:
        self._paths = paths or AppPaths()

    def save_chunks(self, publication_id: str, chunks: list[DocumentChunk]) -> None:
        target = self._chunks_file(publication_id)
        temp_file = target.with_suffix(".jsonl.tmp")
        try:
            with temp_file.open("w", encoding="utf-8") as file:
                for chunk in chunks:
                    file.write(json.dumps(chunk.to_dict(), ensure_ascii=False))
                    file.write("\n")
            temp_file.replace(target)
        except OSError as exc:
            temp_file.unlink(missing_ok=True)
            raise IndexRepositoryError("chunks_write_failed") from exc

    def load_chunks(self, publication_id: str) -> list[DocumentChunk]:
        path = self._chunks_file(publication_id)
        if not path.exists():
            return []

        chunks: list[DocumentChunk] = []
        try:
            with path.open("r", encoding="utf-8") as file:
                for line in file:
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(data, dict):
                        chunks.append(DocumentChunk.from_dict(data))
        except OSError:
            return []
        return chunks

    def delete_chunks(self, publication_id: str) -> bool:
        try:
            self._chunks_file(publication_id).unlink(missing_ok=True)
            self.remove_from_manifest(publication_id)
        except OSError as exc:
            raise IndexRepositoryError("chunks_delete_failed") from exc
        return True

    def has_chunks(self, publication_id: str) -> bool:
        return self._chunks_file(publication_id).exists()

    def chunk_count(self, publication_id: str) -> int:
        return len(self.load_chunks(publication_id))

    def list_indexed_publication_ids(self) -> set[str]:
        return {path.stem for path in self._paths.chunks_dir.glob("*.jsonl")}

    def update_manifest(self, publication: Publication, chunk_count: int) -> None:
        manifest = self._load_manifest()
        publications = manifest.setdefault("publications", {})
        if not isinstance(publications, dict):
            publications = {}
            manifest["publications"] = publications
        publications[publication.id] = {
            "chunk_count": chunk_count,
            "indexed_at": publication.indexed_at or datetime.now().astimezone().isoformat(timespec="seconds"),
            "source_sha256": publication.sha256,
        }
        self._save_manifest(manifest)

    def remove_from_manifest(self, publication_id: str) -> None:
        manifest = self._load_manifest()
        publications = manifest.get("publications")
        if isinstance(publications, dict):
            publications.pop(publication_id, None)
        self._save_manifest(manifest)

    def _chunks_file(self, publication_id: str) -> Path:
        return self._paths.chunks_dir / f"{publication_id}.jsonl"

    def _load_manifest(self) -> dict[str, Any]:
        path = self._paths.index_manifest_file
        if not path.exists():
            return self._empty_manifest()
        try:
            with path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except (OSError, json.JSONDecodeError):
            return self._empty_manifest()
        if not isinstance(data, dict):
            return self._empty_manifest()
        data.setdefault("version", self.MANIFEST_VERSION)
        data.setdefault("publications", {})
        return data

    def _save_manifest(self, manifest: dict[str, Any]) -> None:
        path = self._paths.index_manifest_file
        temp_file = path.with_suffix(".json.tmp")
        try:
            with temp_file.open("w", encoding="utf-8") as file:
                json.dump(manifest, file, ensure_ascii=False, indent=2)
            temp_file.replace(path)
        except OSError as exc:
            temp_file.unlink(missing_ok=True)
            raise IndexRepositoryError("manifest_write_failed") from exc

    def _empty_manifest(self) -> dict[str, Any]:
        return {"version": self.MANIFEST_VERSION, "publications": {}}
