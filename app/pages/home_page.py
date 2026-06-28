from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.ai.ai_client import AIClient
from app.i18n import I18n
from app.services.publication_repository import PublicationRepository
from app.ui.components import metric_card


class HomePage(QWidget):
    action_requested = Signal(str)

    CARD_KEYS = (
        ("home.card.import.title", "home.card.import.description"),
        ("home.card.search.title", "home.card.search.description"),
        ("home.card.study.title", "home.card.study.description"),
    )
    QUICK_ACTIONS = (
        ("publications", "home.quick_actions.import"),
        ("publications", "home.quick_actions.index"),
        ("study", "home.quick_actions.chat"),
        ("settings", "home.quick_actions.configure_ai"),
    )
    METRICS = (
        "home.status.publications",
        "home.status.indexed",
        "home.status.chunks",
        "home.status.ai",
    )

    def __init__(
        self,
        translations: I18n,
        publication_repository: PublicationRepository | None = None,
        ai_client: AIClient | None = None,
    ) -> None:
        super().__init__()
        self._translations = translations
        self._publication_repository = publication_repository
        self._ai_client = ai_client
        self._cards: list[tuple[QLabel, QLabel, str, str]] = []
        self._quick_buttons: list[tuple[QPushButton, str, str]] = []
        self._metric_labels: list[tuple[QLabel, QLabel, str]] = []

        self.setObjectName("Page")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 30, 32, 32)
        layout.setSpacing(20)

        hero = QFrame()
        hero.setObjectName("HeroCard")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(26, 24, 26, 24)
        hero_layout.setSpacing(14)
        self._hero_title = QLabel()
        self._hero_title.setObjectName("HeroTitle")
        self._hero_title.setWordWrap(True)
        self._hero_subtitle = QLabel()
        self._hero_subtitle.setObjectName("HeroSubtitle")
        self._hero_subtitle.setWordWrap(True)
        hero_layout.addWidget(self._hero_title)
        hero_layout.addWidget(self._hero_subtitle)

        quick_layout = QHBoxLayout()
        quick_layout.setSpacing(10)
        self._quick_title = QLabel()
        self._quick_title.setObjectName("FieldLabel")
        quick_layout.addWidget(self._quick_title)
        for page_id, key in self.QUICK_ACTIONS:
            button = QPushButton()
            button.setObjectName("SecondaryButton")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda checked=False, target=page_id: self.action_requested.emit(target))
            self._quick_buttons.append((button, page_id, key))
            quick_layout.addWidget(button)
        quick_layout.addStretch(1)
        hero_layout.addLayout(quick_layout)
        layout.addWidget(hero)

        metrics_layout = QGridLayout()
        metrics_layout.setSpacing(14)
        for index, key in enumerate(self.METRICS):
            card, _card_layout, value, label = metric_card()
            self._metric_labels.append((value, label, key))
            metrics_layout.addWidget(card, 0, index)
        layout.addLayout(metrics_layout)

        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(16)
        for title_key, description_key in self.CARD_KEYS:
            card, title_label, description_label = self._create_card()
            self._cards.append((title_label, description_label, title_key, description_key))
            cards_layout.addWidget(card)
        layout.addLayout(cards_layout)

        guide = QFrame()
        guide.setObjectName("SectionCard")
        guide_layout = QVBoxLayout(guide)
        guide_layout.setContentsMargins(22, 20, 22, 20)
        guide_layout.setSpacing(10)
        self._guide_title = QLabel()
        self._guide_title.setObjectName("SectionTitle")
        self._guide_body = QLabel()
        self._guide_body.setObjectName("SectionDescription")
        self._guide_body.setWordWrap(True)
        guide_layout.addWidget(self._guide_title)
        guide_layout.addWidget(self._guide_body)
        layout.addWidget(guide)
        layout.addStretch(1)

        self.update_texts()

    def refresh_dashboard(self) -> None:
        self._update_metrics()

    def update_texts(self) -> None:
        self._hero_title.setText(self._translations.t("home.hero.title"))
        self._hero_subtitle.setText(self._translations.t("home.hero.subtitle"))
        self._quick_title.setText(self._translations.t("home.quick_actions.title"))
        for button, _page_id, key in self._quick_buttons:
            button.setText(self._translations.t(key))
        for title_label, description_label, title_key, description_key in self._cards:
            title_label.setText(self._translations.t(title_key))
            description_label.setText(self._translations.t(description_key))
        self._guide_title.setText(self._translations.t("home.guide.title"))
        self._guide_body.setText(
            "\n".join(
                self._translations.t(key)
                for key in (
                    "home.guide.import",
                    "home.guide.index",
                    "home.guide.configure",
                    "home.guide.ask",
                )
            )
        )
        self._update_metrics()

    def _update_metrics(self) -> None:
        publications = self._publication_repository.list_publications() if self._publication_repository else []
        indexed = [publication for publication in publications if publication.status == "indexed"]
        chunks = sum(publication.chunk_count for publication in publications)
        values = (
            str(len(publications)),
            str(len(indexed)),
            str(chunks),
            self._translations.t(f"settings.ai_status_values.{self._ai_client.status()}") if self._ai_client else self._translations.t("common.unavailable"),
        )
        for (value_label, label, key), value in zip(self._metric_labels, values):
            value_label.setText(value)
            label.setText(self._translations.t(key))

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
