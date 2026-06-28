from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from app.i18n import I18n


class PublicationsPage(QWidget):
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

        self._placeholder = QLabel()
        self._placeholder.setObjectName("PlaceholderText")
        self._placeholder.setWordWrap(True)
        layout.addWidget(self._placeholder)
        layout.addStretch(1)

        self.update_texts()

    def update_texts(self) -> None:
        self._title.setText(self._translations.t("publications.title"))
        self._placeholder.setText(self._translations.t("publications.placeholder"))
