from __future__ import annotations

from PySide6.QtCore import QRect
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMainWindow, QStackedWidget, QVBoxLayout, QWidget

from app.i18n import I18n
from app.navigation import SidebarNavigation
from app.pages.home_page import HomePage
from app.pages.publications_page import PublicationsPage
from app.pages.settings_page import SettingsPage
from app.pages.study_page import StudyPage
from app.services.index_repository import IndexRepository
from app.services.indexing_service import IndexingService
from app.services.publication_repository import PublicationRepository
from app.services.search_service import SearchService
from app.settings import AppSettings


class MainWindow(QMainWindow):
    PAGE_INDEX = {
        "home": 0,
        "publications": 1,
        "study": 2,
        "settings": 3,
    }

    PAGE_TITLE_KEYS = {
        "home": "home.title",
        "publications": "publications.title",
        "study": "study.title",
        "settings": "settings.title",
    }

    def __init__(self, translations: I18n, settings: AppSettings) -> None:
        super().__init__()
        self._translations = translations
        self._settings = settings
        self._publication_repository = PublicationRepository()
        self._index_repository = IndexRepository(self._publication_repository.paths)
        self._indexing_service = IndexingService(self._publication_repository, self._index_repository)
        self._search_service = SearchService(self._publication_repository, self._index_repository)
        self._current_page = "home"

        self.resize(1100, 720)
        self.setMinimumSize(920, 620)

        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self._navigation = SidebarNavigation(translations)
        self._navigation.page_selected.connect(self._show_page)
        root_layout.addWidget(self._navigation)

        content_root = QWidget()
        content_root.setObjectName("ContentRoot")
        content_layout = QVBoxLayout(content_root)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        top_bar = QWidget()
        top_bar.setObjectName("TopBar")
        top_bar_layout = QHBoxLayout(top_bar)
        top_bar_layout.setContentsMargins(28, 16, 28, 16)
        self._top_bar_title = QLabel()
        self._top_bar_title.setObjectName("TopBarTitle")
        top_bar_layout.addWidget(self._top_bar_title)
        top_bar_layout.addStretch(1)
        content_layout.addWidget(top_bar)

        self._stack = QStackedWidget()
        self._home_page = HomePage(translations)
        self._publications_page = PublicationsPage(
            translations,
            self._publication_repository,
            self._indexing_service,
        )
        self._study_page = StudyPage(
            translations,
            self._publication_repository,
            self._search_service,
        )
        self._settings_page = SettingsPage(translations)
        self._settings_page.language_changed.connect(self._change_language)

        self._pages = (
            self._home_page,
            self._publications_page,
            self._study_page,
            self._settings_page,
        )

        for page in self._pages:
            self._stack.addWidget(page)

        content_layout.addWidget(self._stack, 1)
        root_layout.addWidget(content_root, 1)

        self.setCentralWidget(root)
        self._update_texts()
        self._center_on_screen()

    def _show_page(self, page_id: str) -> None:
        index = self.PAGE_INDEX.get(page_id)
        if index is None:
            return
        self._current_page = page_id
        self._stack.setCurrentIndex(index)
        if page_id == "study":
            self._study_page.refresh_sources()
        self._top_bar_title.setText(self._translations.t(self.PAGE_TITLE_KEYS[page_id]))

    def _change_language(self, language: str) -> None:
        self._settings.set_language(language)
        self._translations.set_language(language)
        self._update_texts()

    def _update_texts(self) -> None:
        self.setWindowTitle(self._translations.t("app.title"))
        self._navigation.update_texts()
        for page in self._pages:
            page.update_texts()
        self._top_bar_title.setText(self._translations.t(self.PAGE_TITLE_KEYS[self._current_page]))

    def _center_on_screen(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        available_geometry: QRect = screen.availableGeometry()
        frame_geometry = self.frameGeometry()
        frame_geometry.moveCenter(available_geometry.center())
        self.move(frame_geometry.topLeft())
