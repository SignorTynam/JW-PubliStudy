from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.i18n import I18n
from app.models.publication import Publication
from app.services.publication_repository import (
    DuplicatePublicationError,
    PublicationError,
    PublicationRepository,
    UnsupportedFileTypeError,
)


class ImportPublicationDialog(QDialog):
    LANGUAGE_OPTIONS = (
        ("it", "publications.language.it"),
        ("al", "publications.language.al"),
        ("en", "publications.language.en"),
        ("unknown", "publications.language.unknown"),
    )

    def __init__(self, translations: I18n, source_path: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._translations = translations
        self.setModal(True)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(16)

        form_layout = QFormLayout()
        form_layout.setSpacing(12)

        self._title_input = QLineEdit(source_path.stem)
        self._title_input.selectAll()

        self._language_combo = QComboBox()
        self._language_combo.setObjectName("FilterCombo")
        for language_code, label_key in self.LANGUAGE_OPTIONS:
            self._language_combo.addItem(self._translations.t(label_key), language_code)

        self._title_label = QLabel()
        self._language_label = QLabel()
        form_layout.addRow(self._title_label, self._title_input)
        form_layout.addRow(self._language_label, self._language_combo)
        layout.addLayout(form_layout)

        actions_layout = QHBoxLayout()
        actions_layout.addStretch(1)
        self._cancel_button = QPushButton()
        self._cancel_button.setObjectName("SecondaryButton")
        self._cancel_button.clicked.connect(self.reject)
        self._confirm_button = QPushButton()
        self._confirm_button.setObjectName("PrimaryButton")
        self._confirm_button.clicked.connect(self.accept)
        actions_layout.addWidget(self._cancel_button)
        actions_layout.addWidget(self._confirm_button)
        layout.addLayout(actions_layout)

        self._update_texts()

    @property
    def publication_title(self) -> str:
        return self._title_input.text().strip()

    @property
    def language(self) -> str:
        language = self._language_combo.currentData()
        return language if isinstance(language, str) else "unknown"

    def _update_texts(self) -> None:
        self.setWindowTitle(self._translations.t("publications.import_dialog.title"))
        self._title_label.setText(self._translations.t("publications.import_dialog.publication_title"))
        self._language_label.setText(self._translations.t("publications.import_dialog.language"))
        self._confirm_button.setText(self._translations.t("publications.import_dialog.confirm"))
        self._cancel_button.setText(self._translations.t("publications.import_dialog.cancel"))


class RenamePublicationDialog(QDialog):
    def __init__(self, translations: I18n, current_title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._translations = translations
        self.setModal(True)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(16)

        form_layout = QFormLayout()
        form_layout.setSpacing(12)
        self._title_label = QLabel()
        self._title_input = QLineEdit(current_title)
        self._title_input.selectAll()
        form_layout.addRow(self._title_label, self._title_input)
        layout.addLayout(form_layout)

        actions_layout = QHBoxLayout()
        actions_layout.addStretch(1)
        self._cancel_button = QPushButton()
        self._cancel_button.setObjectName("SecondaryButton")
        self._cancel_button.clicked.connect(self.reject)
        self._confirm_button = QPushButton()
        self._confirm_button.setObjectName("PrimaryButton")
        self._confirm_button.clicked.connect(self.accept)
        actions_layout.addWidget(self._cancel_button)
        actions_layout.addWidget(self._confirm_button)
        layout.addLayout(actions_layout)

        self._update_texts()

    @property
    def publication_title(self) -> str:
        return self._title_input.text().strip()

    def _update_texts(self) -> None:
        self.setWindowTitle(self._translations.t("publications.rename_dialog.title"))
        self._title_label.setText(self._translations.t("publications.rename_dialog.label"))
        self._confirm_button.setText(self._translations.t("publications.rename_dialog.confirm"))
        self._cancel_button.setText(self._translations.t("publications.rename_dialog.cancel"))


class PublicationsPage(QWidget):
    LANGUAGE_FILTERS = (
        ("all", "publications.filter.all"),
        ("it", "publications.language.it"),
        ("al", "publications.language.al"),
        ("en", "publications.language.en"),
        ("unknown", "publications.language.unknown"),
    )
    TYPE_FILTERS = (
        ("all", "publications.type.all"),
        ("pdf", "publications.type.pdf"),
        ("txt", "publications.type.txt"),
    )
    STATUS_FILTERS = (
        ("all", "publications.status.all"),
        ("imported", "publications.status.imported"),
    )
    TABLE_HEADERS = (
        "publications.table.title",
        "publications.table.language",
        "publications.table.type",
        "publications.table.size",
        "publications.table.status",
        "publications.table.imported_at",
    )

    def __init__(self, translations: I18n, repository: PublicationRepository) -> None:
        super().__init__()
        self._translations = translations
        self._repository = repository
        self._selected_publication_id: str | None = None

        self.setObjectName("Page")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(34, 34, 34, 34)
        layout.setSpacing(18)

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

        self._import_button = QPushButton()
        self._import_button.setObjectName("PrimaryButton")
        self._import_button.clicked.connect(self._import_publication)
        header_layout.addWidget(self._import_button, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header_layout)

        filters_frame = QFrame()
        filters_frame.setObjectName("ToolbarFrame")
        filters_layout = QHBoxLayout(filters_frame)
        filters_layout.setContentsMargins(14, 12, 14, 12)
        filters_layout.setSpacing(12)

        self._language_filter_label = QLabel()
        self._type_filter_label = QLabel()
        self._status_filter_label = QLabel()
        self._language_filter = self._create_filter_combo()
        self._type_filter = self._create_filter_combo()
        self._status_filter = self._create_filter_combo()

        filters_layout.addWidget(self._language_filter_label)
        filters_layout.addWidget(self._language_filter)
        filters_layout.addWidget(self._type_filter_label)
        filters_layout.addWidget(self._type_filter)
        filters_layout.addWidget(self._status_filter_label)
        filters_layout.addWidget(self._status_filter)
        filters_layout.addStretch(1)
        layout.addWidget(filters_frame)

        self._table = QTableWidget(0, len(self.TABLE_HEADERS))
        self._table.setObjectName("PublicationsTable")
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self._table, 1)

        self._empty_state = QLabel()
        self._empty_state.setObjectName("EmptyState")
        self._empty_state.setWordWrap(True)
        self._empty_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._empty_state)

        actions_layout = QHBoxLayout()
        actions_layout.addStretch(1)
        self._rename_button = QPushButton()
        self._rename_button.setObjectName("SecondaryButton")
        self._rename_button.clicked.connect(self._rename_selected_publication)
        self._delete_button = QPushButton()
        self._delete_button.setObjectName("DangerButton")
        self._delete_button.clicked.connect(self._delete_selected_publication)
        actions_layout.addWidget(self._rename_button)
        actions_layout.addWidget(self._delete_button)
        layout.addLayout(actions_layout)

        self.update_texts()
        self._refresh_table()

    def update_texts(self) -> None:
        selected_language = self._language_filter.currentData()
        selected_type = self._type_filter.currentData()
        selected_status = self._status_filter.currentData()

        self._title.setText(self._translations.t("publications.title"))
        self._description.setText(self._translations.t("publications.description"))
        self._import_button.setText(self._translations.t("publications.import_button"))
        self._rename_button.setText(self._translations.t("publications.rename_button"))
        self._delete_button.setText(self._translations.t("publications.delete_button"))
        self._empty_state.setText(self._translations.t("publications.empty"))
        self._language_filter_label.setText(self._translations.t("publications.filter.language"))
        self._type_filter_label.setText(self._translations.t("publications.filter.type"))
        self._status_filter_label.setText(self._translations.t("publications.filter.status"))

        self._populate_combo(self._language_filter, self.LANGUAGE_FILTERS, selected_language)
        self._populate_combo(self._type_filter, self.TYPE_FILTERS, selected_type)
        self._populate_combo(self._status_filter, self.STATUS_FILTERS, selected_status)
        self._table.setHorizontalHeaderLabels([self._translations.t(key) for key in self.TABLE_HEADERS])
        self._refresh_table()

    def _create_filter_combo(self) -> QComboBox:
        combo = QComboBox()
        combo.setObjectName("FilterCombo")
        combo.currentIndexChanged.connect(lambda _index: self._refresh_table())
        return combo

    def _populate_combo(
        self,
        combo: QComboBox,
        options: tuple[tuple[str, str], ...],
        selected_value: object,
    ) -> None:
        combo.blockSignals(True)
        combo.clear()
        for value, label_key in options:
            combo.addItem(self._translations.t(label_key), value)
        index = combo.findData(selected_value if selected_value else "all")
        combo.setCurrentIndex(index if index >= 0 else 0)
        combo.blockSignals(False)

    def _import_publication(self) -> None:
        file_filter = self._translations.t("publications.file_dialog.filter")
        source_file, _ = QFileDialog.getOpenFileName(
            self,
            self._translations.t("publications.file_dialog.title"),
            "",
            file_filter,
        )
        if not source_file:
            return

        source_path = Path(source_file)
        dialog = ImportPublicationDialog(self._translations, source_path, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            self._repository.add_publication(
                source_path=source_path,
                language=dialog.language,
                title=dialog.publication_title,
            )
        except UnsupportedFileTypeError:
            self._show_error("publications.error.unsupported_file")
            return
        except DuplicatePublicationError:
            self._show_error("publications.error.duplicate")
            return
        except PublicationError:
            self._show_error("publications.error.import_failed")
            return

        self._refresh_table()
        self._show_info("publications.success.imported")

    def _rename_selected_publication(self) -> None:
        publication = self._selected_publication()
        if publication is None:
            return

        dialog = RenamePublicationDialog(self._translations, publication.title, self)
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.publication_title:
            return

        try:
            updated = self._repository.update_title(publication.id, dialog.publication_title)
        except PublicationError:
            self._show_error("publications.error.rename_failed")
            return

        if updated:
            self._refresh_table(publication.id)
            self._show_info("publications.success.renamed")

    def _delete_selected_publication(self) -> None:
        publication = self._selected_publication()
        if publication is None:
            return

        message = self._translations.t("publications.delete_confirm.message").format(title=publication.title)
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle(self._translations.t("publications.delete_confirm.title"))
        dialog.setText(message)
        cancel_button = dialog.addButton(
            self._translations.t("publications.delete_confirm.cancel"),
            QMessageBox.ButtonRole.RejectRole,
        )
        delete_button = dialog.addButton(
            self._translations.t("publications.delete_confirm.delete"),
            QMessageBox.ButtonRole.DestructiveRole,
        )
        dialog.setDefaultButton(cancel_button)
        dialog.exec()
        if dialog.clickedButton() != delete_button:
            return

        try:
            deleted = self._repository.delete_publication(publication.id)
        except PublicationError:
            self._show_error("publications.error.delete_failed")
            return

        if deleted:
            self._selected_publication_id = None
            self._refresh_table()
            self._show_info("publications.success.deleted")

    def _refresh_table(self, publication_id_to_select: str | None = None) -> None:
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)

        publications = self._filtered_publications()
        for row, publication in enumerate(publications):
            self._table.insertRow(row)
            self._set_row(row, publication)

        self._table.setSortingEnabled(True)

        if publication_id_to_select:
            self._select_publication(publication_id_to_select)
        self._update_empty_state()
        self._on_selection_changed()

    def _set_row(self, row: int, publication: Publication) -> None:
        values = (
            publication.title,
            self._translations.t(f"publications.language.{publication.language}"),
            self._translations.t(f"publications.type.{publication.file_type}"),
            self._format_size(publication.file_size),
            self._translations.t(f"publications.status.{publication.status}"),
            publication.imported_at,
        )
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            item.setData(Qt.ItemDataRole.UserRole, publication.id)
            self._table.setItem(row, column, item)

    def _filtered_publications(self) -> list[Publication]:
        language_filter = self._language_filter.currentData() or "all"
        type_filter = self._type_filter.currentData() or "all"
        status_filter = self._status_filter.currentData() or "all"

        publications = self._repository.list_publications()
        if language_filter != "all":
            publications = [item for item in publications if item.language == language_filter]
        if type_filter != "all":
            publications = [item for item in publications if item.file_type == type_filter]
        if status_filter != "all":
            publications = [item for item in publications if item.status == status_filter]
        return publications

    def _selected_publication(self) -> Publication | None:
        if self._selected_publication_id is None:
            return None
        return self._repository.get_publication(self._selected_publication_id)

    def _on_selection_changed(self) -> None:
        selected_items = self._table.selectedItems()
        self._selected_publication_id = None
        if selected_items:
            publication_id = selected_items[0].data(Qt.ItemDataRole.UserRole)
            if isinstance(publication_id, str):
                self._selected_publication_id = publication_id

        has_selection = self._selected_publication_id is not None
        self._rename_button.setEnabled(has_selection)
        self._delete_button.setEnabled(has_selection)

    def _select_publication(self, publication_id: str) -> None:
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == publication_id:
                self._table.selectRow(row)
                return

    def _update_empty_state(self) -> None:
        has_publications = bool(self._repository.list_publications())
        self._empty_state.setVisible(not has_publications)
        self._table.setVisible(has_publications)

    def _format_size(self, size: int) -> str:
        if size < 1024:
            return self._translations.t("publications.size.bytes").format(size=size)
        if size < 1024 * 1024:
            return self._translations.t("publications.size.kb").format(size=size / 1024)
        return self._translations.t("publications.size.mb").format(size=size / (1024 * 1024))

    def _show_error(self, message_key: str) -> None:
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Critical)
        dialog.setWindowTitle(self._translations.t("publications.error.title"))
        dialog.setText(self._translations.t(message_key))
        dialog.addButton(
            self._translations.t("common.ok"),
            QMessageBox.ButtonRole.AcceptRole,
        )
        dialog.exec()

    def _show_info(self, message_key: str) -> None:
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Information)
        dialog.setWindowTitle(self._translations.t("publications.success.title"))
        dialog.setText(self._translations.t(message_key))
        dialog.addButton(
            self._translations.t("common.ok"),
            QMessageBox.ButtonRole.AcceptRole,
        )
        dialog.exec()
