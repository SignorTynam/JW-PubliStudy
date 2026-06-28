from __future__ import annotations

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.i18n import I18n


class HomePage(QWidget):
    CARD_KEYS = (
        ("home.card.import.title", "home.card.import.description"),
        ("home.card.search.title", "home.card.search.description"),
        ("home.card.study.title", "home.card.study.description"),
    )

    def __init__(self, translations: I18n) -> None:
        super().__init__()
        self._translations = translations
        self._cards: list[tuple[QLabel, QLabel, str, str]] = []

        self.setObjectName("Page")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(34, 34, 34, 34)
        layout.setSpacing(22)

        self._title = QLabel()
        self._title.setObjectName("PageTitle")
        layout.addWidget(self._title)

        self._subtitle = QLabel()
        self._subtitle.setObjectName("PageSubtitle")
        self._subtitle.setWordWrap(True)
        layout.addWidget(self._subtitle)

        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(18)
        for title_key, description_key in self.CARD_KEYS:
            card, title_label, description_label = self._create_card()
            self._cards.append((title_label, description_label, title_key, description_key))
            cards_layout.addWidget(card)
        layout.addLayout(cards_layout)
        layout.addStretch(1)

        self.update_texts()

    def update_texts(self) -> None:
        self._title.setText(self._translations.t("home.title"))
        self._subtitle.setText(self._translations.t("home.subtitle"))
        for title_label, description_label, title_key, description_key in self._cards:
            title_label.setText(self._translations.t(title_key))
            description_label.setText(self._translations.t(description_key))

    def _create_card(self) -> tuple[QFrame, QLabel, QLabel]:
        card = QFrame()
        card.setObjectName("Card")
        card.setMinimumHeight(150)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        title = QLabel()
        title.setObjectName("CardTitle")
        title.setWordWrap(True)

        description = QLabel()
        description.setObjectName("CardDescription")
        description.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(description)
        layout.addStretch(1)
        return card, title, description
