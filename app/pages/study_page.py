from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.i18n import I18n
from app.models.publication import Publication
from app.models.search_result import SearchResult
from app.services.publication_repository import PublicationRepository
from app.services.search_service import SearchService


class StudyPage(QWidget):
    LANGUAGE_FILTERS = (
        ("all", "study.filters.all_languages"),
        ("it", "publications.language.it"),
        ("al", "publications.language.al"),
        ("en", "publications.language.en"),
        ("unknown", "publications.language.unknown"),
    )
    LIMIT_OPTIONS = (
        (10, "study.filters.limit_10"),
        (20, "study.filters.limit_20"),
        (30, "study.filters.limit_30"),
        (50, "study.filters.limit_50"),
    )
    TABLE_HEADERS = (
        "study.results.table.source",
        "study.results.table.language",
        "study.results.table.page",
        "study.results.table.snippet",
        "study.results.table.score",
    )

    def __init__(
        self,
        translations: I18n,
        publication_repository: PublicationRepository,
        search_service: SearchService,
    ) -> None:
        super().__init__()
        self._translations = translations
        self._publication_repository = publication_repository
        self._search_service = search_service
        self._searchable_publications: list[Publication] = []
        self._results: list[SearchResult] = []
        self._selected_result: SearchResult | None = None

        self.setObjectName("Page")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(34, 34, 34, 34)
        layout.setSpacing(16)

        header_layout = QHBoxLayout()
        title_area = QVBoxLayout()
        title_area.setSpacing(8)
        self._title = QLabel()
        self._title.setObjectName("PageTitle")
        self._description = QLabel()
        self._description.setObjectName("PageSubtitle")
        self._description.setWordWrap(True)
        title_area.addWidget(self._title)
        title_area.addWidget(self._description)
        header_layout.addLayout(title_area, 1)

        self._refresh_button = QPushButton()
        self._refresh_button.setObjectName("SecondaryButton")
        self._refresh_button.clicked.connect(self.refresh_sources)
        header_layout.addWidget(self._refresh_button, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header_layout)

        search_frame = QFrame()
        search_frame.setObjectName("ToolbarFrame")
        search_layout = QHBoxLayout(search_frame)
        search_layout.setContentsMargins(14, 12, 14, 12)
        search_layout.setSpacing(10)
        self._search_input = QLineEdit()
        self._search_input.setObjectName("SearchInput")
        self._search_input.returnPressed.connect(self._execute_search)
        self._search_button = QPushButton()
        self._search_button.setObjectName("SearchButton")
        self._search_button.clicked.connect(self._execute_search)
        search_layout.addWidget(self._search_input, 1)
        search_layout.addWidget(self._search_button)
        layout.addWidget(search_frame)

        filters_frame = QFrame()
        filters_frame.setObjectName("ToolbarFrame")
        filters_layout = QHBoxLayout(filters_frame)
        filters_layout.setContentsMargins(14, 12, 14, 12)
        filters_layout.setSpacing(12)
        self._language_filter_label = QLabel()
        self._publication_filter_label = QLabel()
        self._limit_filter_label = QLabel()
        self._language_filter = self._create_filter_combo()
        self._publication_filter = self._create_filter_combo()
        self._limit_filter = self._create_filter_combo()
        filters_layout.addWidget(self._language_filter_label)
        filters_layout.addWidget(self._language_filter)
        filters_layout.addWidget(self._publication_filter_label)
        filters_layout.addWidget(self._publication_filter, 1)
        filters_layout.addWidget(self._limit_filter_label)
        filters_layout.addWidget(self._limit_filter)
        layout.addWidget(filters_frame)

        self._status_label = QLabel()
        self._status_label.setObjectName("EmptyState")
        self._status_label.setWordWrap(True)
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._status_label)

        self._results_table = QTableWidget(0, len(self.TABLE_HEADERS))
        self._results_table.setObjectName("ResultsTable")
        self._results_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._results_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._results_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._results_table.verticalHeader().setVisible(False)
        self._results_table.horizontalHeader().setStretchLastSection(True)
        self._results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._results_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._results_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._results_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self._results_table.itemSelectionChanged.connect(self._on_result_selected)
        layout.addWidget(self._results_table, 1)

        detail_panel = QFrame()
        detail_panel.setObjectName("DetailPanel")
        detail_layout = QVBoxLayout(detail_panel)
        detail_layout.setContentsMargins(18, 18, 18, 18)
        detail_layout.setSpacing(10)
        self._detail_title = QLabel()
        self._detail_title.setObjectName("DetailTitle")
        self._detail_title.setWordWrap(True)
        self._detail_meta = QLabel()
        self._detail_meta.setObjectName("DetailMeta")
        self._detail_meta.setWordWrap(True)
        self._chunk_text = QTextEdit()
        self._chunk_text.setObjectName("ChunkText")
        self._chunk_text.setReadOnly(True)
        self._chunk_text.setMinimumHeight(150)

        detail_actions = QHBoxLayout()
        detail_actions.addStretch(1)
        self._copy_text_button = QPushButton()
        self._copy_text_button.setObjectName("SecondaryButton")
        self._copy_text_button.clicked.connect(self._copy_selected_text)
        self._copy_reference_button = QPushButton()
        self._copy_reference_button.setObjectName("SecondaryButton")
        self._copy_reference_button.clicked.connect(self._copy_selected_reference)
        detail_actions.addWidget(self._copy_text_button)
        detail_actions.addWidget(self._copy_reference_button)

        detail_layout.addWidget(self._detail_title)
        detail_layout.addWidget(self._detail_meta)
        detail_layout.addWidget(self._chunk_text)
        detail_layout.addLayout(detail_actions)
        layout.addWidget(detail_panel)

        self.update_texts()
        self.refresh_sources()

    def refresh_sources(self) -> None:
        selected_publication = self._publication_filter.currentData()
        self._searchable_publications = self._search_service.list_searchable_publications()
        self._populate_publication_filter(selected_publication)
        if not self._search_service.has_indexed_content():
            self._results = []
            self._refresh_results_table()
            self._set_status("study.results.empty_no_index")
        elif not self._search_input.text().strip():
            self._set_status("study.results.empty_query")

    def update_texts(self) -> None:
        selected_language = self._language_filter.currentData()
        selected_limit = self._limit_filter.currentData()
        selected_publication = self._publication_filter.currentData()

        self._title.setText(self._translations.t("study.title"))
        self._description.setText(self._translations.t("study.description"))
        self._refresh_button.setText(self._translations.t("study.refresh_sources"))
        self._search_input.setPlaceholderText(self._translations.t("study.search.placeholder"))
        self._search_button.setText(self._translations.t("study.search.button"))
        self._language_filter_label.setText(self._translations.t("study.filters.language"))
        self._publication_filter_label.setText(self._translations.t("study.filters.publication"))
        self._limit_filter_label.setText(self._translations.t("study.filters.limit"))
        self._copy_text_button.setText(self._translations.t("study.detail.copy_text"))
        self._copy_reference_button.setText(self._translations.t("study.detail.copy_reference"))
        self._results_table.setHorizontalHeaderLabels([self._translations.t(key) for key in self.TABLE_HEADERS])

        self._populate_combo(self._language_filter, self.LANGUAGE_FILTERS, selected_language or "all")
        self._populate_combo(self._limit_filter, self.LIMIT_OPTIONS, selected_limit or 30)
        self._populate_publication_filter(selected_publication or "all")
        self._refresh_results_table()
        self._update_detail()

    def _create_filter_combo(self) -> QComboBox:
        combo = QComboBox()
        combo.setObjectName("FilterCombo")
        combo.currentIndexChanged.connect(lambda _index: self._execute_search_if_query())
        return combo

    def _populate_combo(
        self,
        combo: QComboBox,
        options: tuple[tuple[object, str], ...],
        selected_value: object,
    ) -> None:
        combo.blockSignals(True)
        combo.clear()
        for value, label_key in options:
            combo.addItem(self._translations.t(label_key), value)
        index = combo.findData(selected_value)
        combo.setCurrentIndex(index if index >= 0 else 0)
        combo.blockSignals(False)

    def _populate_publication_filter(self, selected_value: object = "all") -> None:
        self._publication_filter.blockSignals(True)
        self._publication_filter.clear()
        self._publication_filter.addItem(self._translations.t("study.filters.all_publications"), "all")
        for publication in self._searchable_publications:
            self._publication_filter.addItem(publication.title, publication.id)
        index = self._publication_filter.findData(selected_value)
        self._publication_filter.setCurrentIndex(index if index >= 0 else 0)
        self._publication_filter.blockSignals(False)

    def _execute_search_if_query(self) -> None:
        if self._search_input.text().strip():
            self._execute_search()

    def _execute_search(self) -> None:
        self.refresh_sources()
        query = self._search_input.text().strip()
        if not self._search_service.has_indexed_content():
            self._results = []
            self._refresh_results_table()
            self._set_status("study.results.empty_no_index")
            return
        if not query:
            self._results = []
            self._refresh_results_table()
            self._set_status("study.results.empty_query")
            return

        limit = self._limit_filter.currentData()
        self._results = self._search_service.search(
            query=query,
            language=str(self._language_filter.currentData() or "all"),
            publication_id=str(self._publication_filter.currentData() or "all"),
            limit=int(limit) if isinstance(limit, int) else 30,
        )
        self._refresh_results_table()
        if self._results:
            self._set_status("study.results.count", count=len(self._results))
        else:
            self._set_status("study.results.empty_no_results")

    def _refresh_results_table(self) -> None:
        self._results_table.setRowCount(0)
        for row, result in enumerate(self._results):
            self._results_table.insertRow(row)
            values = (
                result.publication_title,
                self._translations.t(f"publications.language.{result.language}"),
                self._format_page(result),
                result.snippet,
                f"{result.score:.2f}",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, result.chunk_id)
                self._results_table.setItem(row, column, item)
        self._results_table.setVisible(bool(self._results))
        self._selected_result = None
        self._update_detail()

    def _on_result_selected(self) -> None:
        selected_items = self._results_table.selectedItems()
        self._selected_result = None
        if selected_items:
            chunk_id = selected_items[0].data(Qt.ItemDataRole.UserRole)
            self._selected_result = next(
                (result for result in self._results if result.chunk_id == chunk_id),
                None,
            )
        self._update_detail()

    def _update_detail(self) -> None:
        result = self._selected_result
        has_result = result is not None
        self._copy_text_button.setEnabled(has_result)
        self._copy_reference_button.setEnabled(has_result)
        if result is None:
            self._detail_title.setText(self._translations.t("study.detail.title"))
            self._detail_meta.setText(self._translations.t("study.detail.no_selection"))
            self._chunk_text.setPlainText("")
            return

        meta_parts = [
            f"{self._translations.t('study.detail.source')}: {result.publication_title}",
            f"{self._translations.t('study.detail.file')}: {result.source_filename}",
            f"{self._translations.t('study.detail.language')}: {self._translations.t(f'publications.language.{result.language}')}",
            f"{self._translations.t('study.detail.page')}: {self._format_page(result)}",
            f"{self._translations.t('study.detail.score')}: {result.score:.2f}",
        ]
        self._detail_title.setText(result.publication_title)
        self._detail_meta.setText("  |  ".join(meta_parts))
        self._chunk_text.setPlainText(result.text)

    def _set_status(self, key: str, **format_values: object) -> None:
        self._status_label.setText(self._translations.t(key).format(**format_values))
        self._status_label.setVisible(True)

    def _format_page(self, result: SearchResult) -> str:
        if result.page_start is None:
            return self._translations.t("study.page.none")
        if result.page_end is not None and result.page_end != result.page_start:
            return f"{result.page_start}-{result.page_end}"
        return str(result.page_start)

    def _format_reference(self, result: SearchResult) -> str:
        if result.page_start is None:
            return self._translations.t("study.reference.chunk").format(
                title=result.publication_title,
                chunk=result.chunk_index + 1,
            )
        if result.page_end is not None and result.page_end != result.page_start:
            return self._translations.t("study.reference.pages").format(
                title=result.publication_title,
                page_start=result.page_start,
                page_end=result.page_end,
            )
        return self._translations.t("study.reference.page").format(
            title=result.publication_title,
            page=result.page_start,
        )

    def _copy_selected_text(self) -> None:
        if self._selected_result is None:
            return
        QApplication.clipboard().setText(self._selected_result.text)
        self._set_status("study.detail.copied_text")

    def _copy_selected_reference(self) -> None:
        if self._selected_result is None:
            return
        QApplication.clipboard().setText(self._format_reference(self._selected_result))
        self._set_status("study.detail.copied_reference")
