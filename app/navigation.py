from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout, QWidget

from app.i18n import I18n
from app.version import APP_VERSION


@dataclass(frozen=True)
class NavigationItem:
    page_id: str
    label_key: str


class SidebarNavigation(QFrame):
    page_selected = Signal(str)

    ITEMS = (
        NavigationItem("home", "nav.home"),
        NavigationItem("publications", "nav.publications"),
        NavigationItem("study", "nav.study"),
        NavigationItem("settings", "nav.settings"),
    )

    def __init__(
        self,
        translations: I18n,
        ai_status_provider: Callable[[], str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._translations = translations
        self._ai_status_provider = ai_status_provider
        self._buttons: dict[str, QPushButton] = {}
        self._active_page = "home"

        self.setObjectName("Sidebar")
        self.setFixedWidth(256)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 24, 20, 20)
        layout.setSpacing(9)

        self._title_label = QLabel()
        self._title_label.setObjectName("SidebarTitle")
        layout.addWidget(self._title_label)

        self._subtitle_label = QLabel()
        self._subtitle_label.setObjectName("SidebarSubtitle")
        layout.addWidget(self._subtitle_label)
        layout.addSpacing(18)

        for item in self.ITEMS:
            button = QPushButton()
            button.setObjectName("NavButton")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda checked=False, page_id=item.page_id: self.select_page(page_id))
            self._buttons[item.page_id] = button
            layout.addWidget(button)

        layout.addStretch(1)

        self._ai_text = QLabel()
        self._ai_text.setObjectName("SidebarAIText")
        self._ai_text.setWordWrap(True)
        self._ai_status = QLabel()
        self._ai_status.setObjectName("SidebarAIStatus")
        self._ai_status.setWordWrap(True)
        layout.addWidget(self._ai_text)
        layout.addWidget(self._ai_status)

        self.update_texts()
        self._refresh_active_state()

    def select_page(self, page_id: str) -> None:
        if page_id not in self._buttons:
            return
        self._active_page = page_id
        self._refresh_active_state()
        self.page_selected.emit(page_id)

    def update_texts(self) -> None:
        self._title_label.setText(self._translations.t("app.title"))
        self._subtitle_label.setText(self._translations.t("nav.version").format(version=APP_VERSION))
        self._ai_text.setText(self._translations.t("nav.ai_status_label"))
        for item in self.ITEMS:
            self._buttons[item.page_id].setText(self._translations.t(item.label_key))
        self.update_ai_status()

    def update_ai_status(self) -> None:
        status = self._ai_status_provider() if self._ai_status_provider is not None else "not_configured"
        self._ai_status.setText(self._translations.t(f"settings.ai_status_values.{status}"))
        self._ai_status.setProperty("status", status)
        self._ai_status.style().unpolish(self._ai_status)
        self._ai_status.style().polish(self._ai_status)

    def _refresh_active_state(self) -> None:
        for page_id, button in self._buttons.items():
            button.setProperty("active", page_id == self._active_page)
            button.style().unpolish(button)
            button.style().polish(button)
