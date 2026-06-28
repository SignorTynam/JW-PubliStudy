from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QLabel, QVBoxLayout, QWidget

from app.i18n import I18n


class SettingsPage(QWidget):
    language_changed = Signal(str)

    LANGUAGE_OPTIONS = (
        ("it", "settings.language_option.it"),
        ("al", "settings.language_option.al"),
        ("en", "settings.language_option.en"),
    )

    def __init__(self, translations: I18n) -> None:
        super().__init__()
        self._translations = translations

        self.setObjectName("Page")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(34, 34, 34, 34)
        layout.setSpacing(18)

        self._title = QLabel()
        self._title.setObjectName("PageTitle")
        layout.addWidget(self._title)

        self._description = QLabel()
        self._description.setObjectName("SettingsDescription")
        self._description.setWordWrap(True)
        layout.addWidget(self._description)

        self._language_label = QLabel()
        self._language_label.setObjectName("FieldLabel")
        layout.addWidget(self._language_label)

        self._language_combo = QComboBox()
        self._language_combo.currentIndexChanged.connect(self._on_language_changed)
        layout.addWidget(self._language_combo)
        layout.addStretch(1)

        self.update_texts()

    def update_texts(self) -> None:
        current_language = self._translations.language
        self._title.setText(self._translations.t("settings.title"))
        self._description.setText(self._translations.t("settings.language_description"))
        self._language_label.setText(self._translations.t("settings.language"))

        self._language_combo.blockSignals(True)
        self._language_combo.clear()
        for language_code, label_key in self.LANGUAGE_OPTIONS:
            self._language_combo.addItem(self._translations.t(label_key), language_code)
        self._language_combo.setCurrentIndex(self._index_for_language(current_language))
        self._language_combo.blockSignals(False)

    def _on_language_changed(self, index: int) -> None:
        language = self._language_combo.itemData(index)
        if isinstance(language, str) and language != self._translations.language:
            self.language_changed.emit(language)

    def _index_for_language(self, language: str) -> int:
        for index, (language_code, _) in enumerate(self.LANGUAGE_OPTIONS):
            if language_code == language:
                return index
        return 0
