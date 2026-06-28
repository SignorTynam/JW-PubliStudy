from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from app.models.publication import Publication, VALID_FILE_TYPES, VALID_LANGUAGES
from app.paths import AppPaths


class PublicationError(Exception):
    """Base exception for publication repository errors."""


class UnsupportedFileTypeError(PublicationError):
    """Raised when an imported file type is not supported."""


class DuplicatePublicationError(PublicationError):
    """Raised when a file with the same sha256 already exists."""


class PublicationRepository:
    def __init__(self, paths: AppPaths | None = None) -> None:
        self._paths = paths or AppPaths()
        self._publications: list[Publication] = self._load_publications()

    @property
    def paths(self) -> AppPaths:
        return self._paths

    def list_publications(self) -> list[Publication]:
        return list(self._publications)

    def get_publication(self, publication_id: str) -> Publication | None:
        return next((publication for publication in self._publications if publication.id == publication_id), None)

    def get_stored_file_path(self, publication_id: str) -> Path | None:
        publication = self.get_publication(publication_id)
        if publication is None or not publication.stored_filename:
            return None
        return self._paths.publications_dir / publication.stored_filename

    def add_publication(self, source_path: Path, language: str, title: str | None = None) -> Publication:
        source = Path(source_path)
        if not source.is_file():
            raise PublicationError("source_file_missing")

        file_type = source.suffix.lower().lstrip(".")
        if file_type not in VALID_FILE_TYPES:
            raise UnsupportedFileTypeError(file_type)

        normalized_language = language if language in VALID_LANGUAGES else "unknown"
        try:
            file_hash = self._sha256(source)
        except OSError as exc:
            raise PublicationError("hash_failed") from exc
        if any(publication.sha256 == file_hash for publication in self._publications):
            raise DuplicatePublicationError(file_hash)

        publication_id = str(uuid4())
        stored_filename = f"{publication_id}.{file_type}"
        destination = self._paths.publications_dir / stored_filename

        try:
            shutil.copy2(source, destination)
        except OSError as exc:
            raise PublicationError("copy_failed") from exc

        publication = Publication(
            id=publication_id,
            title=(title.strip() if title and title.strip() else source.stem),
            language=normalized_language,
            original_filename=source.name,
            stored_filename=stored_filename,
            file_type=file_type,
            file_size=destination.stat().st_size,
            imported_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            status="imported",
            sha256=file_hash,
        )

        self._publications.append(publication)
        try:
            self._save_publications()
        except PublicationError:
            self._publications.remove(publication)
            destination.unlink(missing_ok=True)
            raise

        return publication

    def delete_publication(self, publication_id: str) -> bool:
        publication = self.get_publication(publication_id)
        if publication is None:
            return False

        previous_publications = list(self._publications)
        self._publications = [item for item in self._publications if item.id != publication_id]
        stored_path = self._paths.publications_dir / publication.stored_filename
        try:
            stored_path.unlink(missing_ok=True)
            self._save_publications()
        except OSError as exc:
            self._publications = previous_publications
            raise PublicationError("delete_failed") from exc
        except PublicationError:
            self._publications = previous_publications
            raise
        return True

    def update_title(self, publication_id: str, new_title: str) -> bool:
        publication = self.get_publication(publication_id)
        cleaned_title = new_title.strip()
        if publication is None or not cleaned_title:
            return False

        previous_title = publication.title
        publication.title = cleaned_title
        try:
            self._save_publications()
        except PublicationError:
            publication.title = previous_title
            raise
        return True

    def update_indexing_status(
        self,
        publication_id: str,
        status: str,
        chunk_count: int = 0,
        indexed_at: str = "",
        error_message: str = "",
    ) -> bool:
        publication = self.get_publication(publication_id)
        if publication is None or status not in {"imported", "pending_indexing", "indexed", "error"}:
            return False

        previous_values = (
            publication.status,
            publication.chunk_count,
            publication.indexed_at,
            publication.error_message,
        )
        publication.status = status
        publication.chunk_count = chunk_count
        publication.indexed_at = indexed_at
        publication.error_message = error_message
        try:
            self.save()
        except PublicationError:
            (
                publication.status,
                publication.chunk_count,
                publication.indexed_at,
                publication.error_message,
            ) = previous_values
            raise
        return True

    def save(self) -> None:
        self._save_publications()

    def _load_publications(self) -> list[Publication]:
        metadata_file = self._paths.metadata_file
        if not metadata_file.exists():
            return []

        try:
            with metadata_file.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except (OSError, json.JSONDecodeError):
            return []

        if not isinstance(data, list):
            return []

        publications: list[Publication] = []
        for item in data:
            if isinstance(item, dict):
                publications.append(Publication.from_dict(item))
        return publications

    def _save_publications(self) -> None:
        metadata_file = self._paths.metadata_file
        metadata_file.parent.mkdir(parents=True, exist_ok=True)
        temp_file = metadata_file.with_suffix(".json.tmp")
        data = [publication.to_dict() for publication in self._publications]

        try:
            with temp_file.open("w", encoding="utf-8") as file:
                json.dump(data, file, ensure_ascii=False, indent=2)
            temp_file.replace(metadata_file)
        except OSError as exc:
            temp_file.unlink(missing_ok=True)
            raise PublicationError("metadata_write_failed") from exc

    def _sha256(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for block in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
