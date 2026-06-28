from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4


VALID_LANGUAGES = {"it", "al", "en", "unknown"}
VALID_FILE_TYPES = {"pdf", "txt"}
VALID_STATUSES = {"imported", "pending_indexing", "indexed", "error"}


@dataclass
class Publication:
    id: str
    title: str
    language: str
    original_filename: str
    stored_filename: str
    file_type: str
    file_size: int
    imported_at: str
    status: str
    sha256: str
    indexed_at: str = ""
    chunk_count: int = 0
    error_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "language": self.language,
            "original_filename": self.original_filename,
            "stored_filename": self.stored_filename,
            "file_type": self.file_type,
            "file_size": self.file_size,
            "imported_at": self.imported_at,
            "status": self.status,
            "sha256": self.sha256,
            "indexed_at": self.indexed_at,
            "chunk_count": self.chunk_count,
            "error_message": self.error_message,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Publication":
        publication_id = _string_value(data.get("id"), str(uuid4()))
        title = _string_value(data.get("title"), _string_value(data.get("original_filename"), "Untitled"))
        language = _choice_value(data.get("language"), VALID_LANGUAGES, "unknown")
        original_filename = _string_value(data.get("original_filename"), title)
        stored_filename = _string_value(data.get("stored_filename"), "")
        file_type = _choice_value(data.get("file_type"), VALID_FILE_TYPES, "txt")
        file_size = _int_value(data.get("file_size"), 0)
        imported_at = _string_value(data.get("imported_at"), "")
        status = _choice_value(data.get("status"), VALID_STATUSES, "imported")
        sha256 = _string_value(data.get("sha256"), "")
        indexed_at = _string_value(data.get("indexed_at"), "")
        chunk_count = _int_value(data.get("chunk_count"), 0)
        error_message = _string_value(data.get("error_message"), "")

        return cls(
            id=publication_id,
            title=title,
            language=language,
            original_filename=original_filename,
            stored_filename=stored_filename,
            file_type=file_type,
            file_size=file_size,
            imported_at=imported_at,
            status=status,
            sha256=sha256,
            indexed_at=indexed_at,
            chunk_count=chunk_count,
            error_message=error_message,
        )


def _string_value(value: Any, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def _int_value(value: Any, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed >= 0 else fallback


def _choice_value(value: Any, valid_values: set[str], fallback: str) -> str:
    if isinstance(value, str) and value in valid_values:
        return value
    return fallback
