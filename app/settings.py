from __future__ import annotations

from PySide6.QtCore import QSettings

from app.i18n import I18n


class AppSettings:
    """Small wrapper around QSettings for local application preferences."""

    LANGUAGE_KEY = "language"

    def __init__(self) -> None:
        self._settings = QSettings("JW PubliStudy", "JW PubliStudy")

    def language(self) -> str:
        language = self._settings.value(self.LANGUAGE_KEY, I18n.FALLBACK_LANGUAGE, str)
        return language if language in I18n.SUPPORTED_LANGUAGES else I18n.FALLBACK_LANGUAGE

    def set_language(self, language: str) -> None:
        if language in I18n.SUPPORTED_LANGUAGES:
            self._settings.setValue(self.LANGUAGE_KEY, language)
            self._settings.sync()
