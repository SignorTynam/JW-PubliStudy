from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class DocumentChunk:
    id: str
    publication_id: str
    publication_title: str
    language: str
    source_filename: str
    chunk_index: int
    text: str
    page_start: int | None
    page_end: int | None
    char_start: int
    char_end: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "publication_id": self.publication_id,
            "publication_title": self.publication_title,
            "language": self.language,
            "source_filename": self.source_filename,
            "chunk_index": self.chunk_index,
            "text": self.text,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "char_start": self.char_start,
            "char_end": self.char_end,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DocumentChunk":
        publication_id = _string_value(data.get("publication_id"), "")
        chunk_index = _int_value(data.get("chunk_index"), 0)
        chunk_id = _string_value(data.get("id"), f"{publication_id}:{chunk_index}")
        return cls(
            id=chunk_id,
            publication_id=publication_id,
            publication_title=_string_value(data.get("publication_title"), ""),
            language=_string_value(data.get("language"), "unknown"),
            source_filename=_string_value(data.get("source_filename"), ""),
            chunk_index=chunk_index,
            text=_string_value(data.get("text"), ""),
            page_start=_optional_int_value(data.get("page_start")),
            page_end=_optional_int_value(data.get("page_end")),
            char_start=_int_value(data.get("char_start"), 0),
            char_end=_int_value(data.get("char_end"), 0),
        )


def _string_value(value: Any, fallback: str) -> str:
    if isinstance(value, str):
        return value
    return fallback


def _int_value(value: Any, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed >= 0 else fallback


def _optional_int_value(value: Any) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None
