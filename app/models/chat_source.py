from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models.search_result import SearchResult


@dataclass
class ChatSource:
    source_id: str
    chunk_id: str
    publication_id: str
    publication_title: str
    source_filename: str
    language: str
    page_start: int | None
    page_end: int | None
    chunk_index: int
    text: str
    snippet: str
    score: float
    reduced: bool = False
    original_text_length: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "chunk_id": self.chunk_id,
            "publication_id": self.publication_id,
            "publication_title": self.publication_title,
            "source_filename": self.source_filename,
            "language": self.language,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "chunk_index": self.chunk_index,
            "text": self.text,
            "snippet": self.snippet,
            "score": self.score,
            "reduced": self.reduced,
            "original_text_length": self.original_text_length,
        }

    @classmethod
    def from_search_result(cls, result: SearchResult, source_number: int) -> "ChatSource":
        return cls(
            source_id=f"S{source_number}",
            chunk_id=result.chunk_id,
            publication_id=result.publication_id,
            publication_title=result.publication_title,
            source_filename=result.source_filename,
            language=result.language,
            page_start=result.page_start,
            page_end=result.page_end,
            chunk_index=result.chunk_index,
            text=result.text,
            snippet=result.snippet,
            score=result.score,
            reduced=False,
            original_text_length=len(result.text),
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChatSource":
        return cls(
            source_id=_string_value(data.get("source_id"), ""),
            chunk_id=_string_value(data.get("chunk_id"), ""),
            publication_id=_string_value(data.get("publication_id"), ""),
            publication_title=_string_value(data.get("publication_title"), ""),
            source_filename=_string_value(data.get("source_filename"), ""),
            language=_string_value(data.get("language"), "unknown"),
            page_start=_optional_int(data.get("page_start")),
            page_end=_optional_int(data.get("page_end")),
            chunk_index=_int_value(data.get("chunk_index"), 0),
            text=_string_value(data.get("text"), ""),
            snippet=_string_value(data.get("snippet"), ""),
            score=_float_value(data.get("score"), 0.0),
            reduced=bool(data.get("reduced", False)),
            original_text_length=_optional_nonnegative_int(data.get("original_text_length")),
        )

    def format_reference(self) -> str:
        if self.page_start is None:
            return f"{self.publication_title} - chunk {self.chunk_index + 1}"
        if self.page_end is not None and self.page_end != self.page_start:
            return f"{self.publication_title} - pages {self.page_start}-{self.page_end}"
        return f"{self.publication_title} - page {self.page_start}"


def _string_value(value: Any, fallback: str) -> str:
    return value if isinstance(value, str) else fallback


def _int_value(value: Any, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed >= 0 else fallback


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _optional_nonnegative_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _float_value(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback
