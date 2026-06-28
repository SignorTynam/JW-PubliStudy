from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class SearchResult:
    chunk_id: str
    publication_id: str
    publication_title: str
    language: str
    source_filename: str
    chunk_index: int
    text: str
    snippet: str
    score: float
    page_start: int | None
    page_end: int | None
    matched_terms: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "publication_id": self.publication_id,
            "publication_title": self.publication_title,
            "language": self.language,
            "source_filename": self.source_filename,
            "chunk_index": self.chunk_index,
            "text": self.text,
            "snippet": self.snippet,
            "score": self.score,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "matched_terms": self.matched_terms,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SearchResult":
        matched_terms = data.get("matched_terms")
        return cls(
            chunk_id=_string_value(data.get("chunk_id"), ""),
            publication_id=_string_value(data.get("publication_id"), ""),
            publication_title=_string_value(data.get("publication_title"), ""),
            language=_string_value(data.get("language"), "unknown"),
            source_filename=_string_value(data.get("source_filename"), ""),
            chunk_index=_int_value(data.get("chunk_index"), 0),
            text=_string_value(data.get("text"), ""),
            snippet=_string_value(data.get("snippet"), ""),
            score=_float_value(data.get("score"), 0.0),
            page_start=_optional_int_value(data.get("page_start")),
            page_end=_optional_int_value(data.get("page_end")),
            matched_terms=[term for term in matched_terms if isinstance(term, str)] if isinstance(matched_terms, list) else [],
        )


def _string_value(value: Any, fallback: str) -> str:
    return value if isinstance(value, str) else fallback


def _int_value(value: Any, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed >= 0 else fallback


def _float_value(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _optional_int_value(value: Any) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None
