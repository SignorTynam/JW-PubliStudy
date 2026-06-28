from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.services.chat_history_repository import ChatHistoryRepository
from app.services.index_repository import IndexRepository
from app.services.indexing_service import IndexingService
from app.services.publication_repository import PublicationError, PublicationRepository


@dataclass(frozen=True)
class LibraryStats:
    total_publications: int
    imported_publications: int
    indexed_publications: int
    error_publications: int
    pending_publications: int
    total_chunks: int
    publications_size_bytes: int
    index_size_bytes: int
    chat_history_size_bytes: int


@dataclass(frozen=True)
class IntegrityIssue:
    code: str
    message: str
    publication_id: str | None = None
    publication_title: str = ""


@dataclass(frozen=True)
class IntegrityReport:
    ok: bool
    issues: list[IntegrityIssue]


@dataclass(frozen=True)
class MaintenanceResult:
    success: bool
    message: str
    processed_count: int = 0
    failed_count: int = 0


class MaintenanceService:
    def __init__(
        self,
        publication_repository: PublicationRepository,
        index_repository: IndexRepository,
        indexing_service: IndexingService,
        chat_history_repository: ChatHistoryRepository | None = None,
    ) -> None:
        self._publication_repository = publication_repository
        self._index_repository = index_repository
        self._indexing_service = indexing_service
        self._chat_history_repository = chat_history_repository
        self._paths = publication_repository.paths

    def get_library_stats(self) -> LibraryStats:
        publications = self._publication_repository.list_publications()
        return LibraryStats(
            total_publications=len(publications),
            imported_publications=sum(1 for item in publications if item.status == "imported"),
            indexed_publications=sum(1 for item in publications if item.status == "indexed"),
            error_publications=sum(1 for item in publications if item.status == "error"),
            pending_publications=sum(1 for item in publications if item.status == "pending_indexing"),
            total_chunks=sum(self._index_repository.chunk_count(item.id) for item in publications),
            publications_size_bytes=self._directory_size(self._paths.publications_dir),
            index_size_bytes=self._directory_size(self._paths.index_dir),
            chat_history_size_bytes=self._file_size(self._paths.chat_history_file),
        )

    def check_integrity(self) -> IntegrityReport:
        issues: list[IntegrityIssue] = []
        publications = self._publication_repository.list_publications()
        publication_ids = {item.id for item in publications}

        if self._paths.metadata_file.exists() and not self._is_valid_json(self._paths.metadata_file):
            issues.append(IntegrityIssue("metadata_corrupt", "metadata_corrupt"))

        if self._paths.index_manifest_file.exists() and not self._is_valid_json(self._paths.index_manifest_file):
            issues.append(IntegrityIssue("manifest_corrupt", "manifest_corrupt"))

        if self._paths.chat_history_file.exists() and not self._is_valid_json(self._paths.chat_history_file):
            issues.append(IntegrityIssue("chat_history_corrupt", "chat_history_corrupt"))

        for publication in publications:
            stored_path = self._publication_repository.get_stored_file_path(publication.id)
            if stored_path is None or not stored_path.exists():
                issues.append(IntegrityIssue("missing_file", "missing_file", publication.id, publication.title))
            if publication.status == "indexed":
                if not self._index_repository.has_chunks(publication.id):
                    issues.append(IntegrityIssue("missing_chunks", "missing_chunks", publication.id, publication.title))
                real_count = self._index_repository.chunk_count(publication.id)
                if real_count != publication.chunk_count:
                    issues.append(IntegrityIssue("chunk_count_mismatch", "chunk_count_mismatch", publication.id, publication.title))

        for indexed_id in self._index_repository.list_indexed_publication_ids():
            if indexed_id not in publication_ids:
                issues.append(IntegrityIssue("orphan_chunks", "orphan_chunks", indexed_id, ""))

        return IntegrityReport(ok=not issues, issues=issues)

    def rebuild_index(self) -> MaintenanceResult:
        processed = 0
        failed = 0
        for publication in self._publication_repository.list_publications():
            stored_path = self._publication_repository.get_stored_file_path(publication.id)
            if stored_path is None or not stored_path.exists():
                failed += 1
                continue
            result = self._indexing_service.index_publication(publication.id)
            if result.success:
                processed += 1
            else:
                failed += 1
        return MaintenanceResult(success=failed == 0, message="rebuild_done", processed_count=processed, failed_count=failed)

    def reset_index(self) -> MaintenanceResult:
        try:
            for path in self._paths.chunks_dir.glob("*.jsonl"):
                path.unlink(missing_ok=True)
            self._paths.index_manifest_file.unlink(missing_ok=True)
            for publication in self._publication_repository.list_publications():
                self._publication_repository.update_indexing_status(publication.id, "imported")
        except (OSError, PublicationError):
            return MaintenanceResult(False, "reset_failed")
        return MaintenanceResult(True, "reset_done")

    def clear_chat_history(self) -> MaintenanceResult:
        if self._chat_history_repository is None:
            return MaintenanceResult(False, "clear_chat_failed")
        try:
            self._chat_history_repository.clear_history()
        except OSError:
            return MaintenanceResult(False, "clear_chat_failed")
        return MaintenanceResult(True, "clear_chat_done")

    def _directory_size(self, path: Path) -> int:
        if not path.exists():
            return 0
        return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())

    def _file_size(self, path: Path) -> int:
        return path.stat().st_size if path.exists() else 0

    def _is_valid_json(self, path: Path) -> bool:
        try:
            with path.open("r", encoding="utf-8") as file:
                json.load(file)
        except (OSError, json.JSONDecodeError):
            return False
        return True
