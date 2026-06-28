from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout, QWidget

from app.i18n import I18n


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

    def __init__(self, translations: I18n, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._translations = translations
        self._buttons: dict[str, QPushButton] = {}
        self._active_page = "home"

        self.setObjectName("Sidebar")
        self.setFixedWidth(238)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 22, 18, 18)
        layout.setSpacing(8)

        self._title_label = QLabel()
        self._title_label.setObjectName("SidebarTitle")
        layout.addWidget(self._title_label)

        for item in self.ITEMS:
            button = QPushButton()
            button.setObjectName("NavButton")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda checked=False, page_id=item.page_id: self.select_page(page_id))
            self._buttons[item.page_id] = button
            layout.addWidget(button)

        layout.addStretch(1)
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
        for item in self.ITEMS:
            self._buttons[item.page_id].setText(self._translations.t(item.label_key))

    def _refresh_active_state(self) -> None:
        for page_id, button in self._buttons.items():
            button.setProperty("active", page_id == self._active_page)
            button.style().unpolish(button)
            button.style().polish(button)
