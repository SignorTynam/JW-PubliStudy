from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class I18n:
    """JSON-backed translation loader with Italian fallback."""

    FALLBACK_LANGUAGE = "it"
    SUPPORTED_LANGUAGES = ("it", "al", "en")

    def __init__(self, translations_dir: Path, language: str = FALLBACK_LANGUAGE) -> None:
        self._translations_dir = translations_dir
        self._fallback: dict[str, Any] = self._load_language(self.FALLBACK_LANGUAGE)
        self._language = self._normalize_language(language)
        self._current: dict[str, Any] = self._load_language(self._language)

    @property
    def language(self) -> str:
        return self._language

    def set_language(self, language: str) -> None:
        normalized = self._normalize_language(language)
        self._language = normalized
        self._current = self._load_language(normalized)

    def t(self, key: str) -> str:
        value = self._lookup(self._current, key)
        if value is None:
            value = self._lookup(self._fallback, key)
        return str(value) if value is not None else key

    def _normalize_language(self, language: str) -> str:
        return language if language in self.SUPPORTED_LANGUAGES else self.FALLBACK_LANGUAGE

    def _load_language(self, language: str) -> dict[str, Any]:
        path = self._translations_dir / f"{language}.json"
        try:
            with path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _lookup(self, data: dict[str, Any], key: str) -> Any | None:
        current: Any = data
        for part in key.split("."):
            if not isinstance(current, dict) or part not in current:
                return None
            current = current[part]
        return current
