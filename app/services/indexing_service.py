from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.services.index_repository import IndexRepository, IndexRepositoryError
from app.services.publication_repository import PublicationError, PublicationRepository
from app.services.text_chunker import TextChunker
from app.services.text_extractor import (
    EmptyExtractedTextError,
    TextExtractionError,
    TextExtractor,
    UnsupportedExtractionTypeError,
)


@dataclass(frozen=True)
class IndexingResult:
    publication_id: str
    success: bool
    chunk_count: int
    error_message: str


class IndexingService:
    def __init__(
        self,
        publication_repository: PublicationRepository,
        index_repository: IndexRepository | None = None,
        text_extractor: TextExtractor | None = None,
        text_chunker: TextChunker | None = None,
    ) -> None:
        self._publication_repository = publication_repository
        self._index_repository = index_repository or IndexRepository(publication_repository.paths)
        self._text_extractor = text_extractor or TextExtractor()
        self._text_chunker = text_chunker or TextChunker()

    def index_publication(self, publication_id: str) -> IndexingResult:
        publication = self._publication_repository.get_publication(publication_id)
        if publication is None:
            return IndexingResult(publication_id, False, 0, "publication_missing")

        try:
            self._publication_repository.update_indexing_status(publication_id, "pending_indexing")
            source_path = self._publication_repository.get_stored_file_path(publication_id)
            if source_path is None or not source_path.is_file():
                raise TextExtractionError("missing_file")

            document = self._text_extractor.extract(source_path, publication.file_type)
            chunks = self._text_chunker.create_chunks(publication, document)
            if not chunks:
                raise EmptyExtractedTextError("no_extractable_text")

            self._index_repository.save_chunks(publication_id, chunks)
            indexed_at = datetime.now().astimezone().isoformat(timespec="seconds")
            self._publication_repository.update_indexing_status(
                publication_id,
                "indexed",
                chunk_count=len(chunks),
                indexed_at=indexed_at,
                error_message="",
            )
            updated_publication = self._publication_repository.get_publication(publication_id)
            if updated_publication is not None:
                self._index_repository.update_manifest(updated_publication, len(chunks))
            return IndexingResult(publication_id, True, len(chunks), "")
        except UnsupportedExtractionTypeError:
            return self._fail(publication_id, "unsupported_type")
        except EmptyExtractedTextError as exc:
            return self._fail(publication_id, str(exc) or "no_extractable_text")
        except TextExtractionError as exc:
            return self._fail(publication_id, str(exc) or "extraction_failed")
        except (IndexRepositoryError, PublicationError):
            return self._fail(publication_id, "index_failed")
        except Exception:
            return self._fail(publication_id, "index_failed")

    def delete_publication_index(self, publication_id: str) -> bool:
        return self._index_repository.delete_chunks(publication_id)

    def _fail(self, publication_id: str, error_message: str) -> IndexingResult:
        try:
            self._index_repository.delete_chunks(publication_id)
        except IndexRepositoryError:
            pass
        try:
            self._publication_repository.update_indexing_status(
                publication_id,
                "error",
                chunk_count=0,
                indexed_at="",
                error_message=error_message,
            )
        except PublicationError:
            pass
        return IndexingResult(publication_id, False, 0, error_message)
