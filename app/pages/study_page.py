from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from app.ai.ai_client import AIClient
from app.i18n import I18n
from app.pages.chat_panel import ChatPanel
from app.pages.search_panel import SearchPanel
from app.services.chat_history_repository import ChatHistoryRepository
from app.services.publication_repository import PublicationRepository
from app.services.rag_service import RagService
from app.services.search_service import SearchService
from app.settings import AppSettings


class StudyPage(QWidget):
    configure_ai_requested = Signal()

    def __init__(
        self,
        translations: I18n,
        publication_repository: PublicationRepository,
        search_service: SearchService,
        rag_service: RagService,
        chat_history_repository: ChatHistoryRepository,
        settings: AppSettings,
        llm_client: AIClient,
    ) -> None:
        super().__init__()
        self._translations = translations
        self._publication_repository = publication_repository

        self.setObjectName("Page")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(34, 34, 34, 34)
        layout.setSpacing(16)

        self._tabs = QTabWidget()
        self._tabs.setObjectName("StudyTabs")
        self._search_panel = SearchPanel(translations, search_service)
        self._chat_panel = ChatPanel(
            translations=translations,
            settings=settings,
            rag_service=rag_service,
            chat_history_repository=chat_history_repository,
            search_service=search_service,
            llm_client=llm_client,
        )
        self._tabs.addTab(self._search_panel, "")
        self._tabs.addTab(self._chat_panel, "")
        self._chat_panel.configure_ai_requested.connect(self.configure_ai_requested.emit)
        layout.addWidget(self._tabs)

        self.update_texts()

    def refresh_sources(self) -> None:
        self._search_panel.refresh_sources()
        self._chat_panel.refresh_sources()

    def update_texts(self) -> None:
        self._tabs.setTabText(0, self._translations.t("study.tabs.search"))
        self._tabs.setTabText(1, self._translations.t("study.tabs.chat"))
        self._search_panel.update_texts()
        self._chat_panel.update_texts()

    def cancel_pending_request(self, wait_ms: int = 0) -> bool:
        return self._chat_panel.cancel_pending_request(wait_ms)
