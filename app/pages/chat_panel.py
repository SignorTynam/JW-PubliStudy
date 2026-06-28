from __future__ import annotations

import html

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.ai.ai_client import AIClient
from app.ai.ai_status import AIStatus
from app.i18n import I18n
from app.models.chat_message import ChatMessage
from app.models.chat_source import ChatSource
from app.models.publication import Publication
from app.services.chat_history_repository import ChatHistoryRepository
from app.services.local_llm_client import is_local_endpoint
from app.services.rag_service import RagAnswer, RagService
from app.services.search_service import SearchService
from app.settings import AppSettings


class ChatPanel(QWidget):
    configure_ai_requested = Signal()
    LANGUAGE_FILTERS = (
        ("all", "chat.filters.all_languages"),
        ("it", "publications.language.it"),
        ("al", "publications.language.al"),
        ("en", "publications.language.en"),
        ("unknown", "publications.language.unknown"),
    )
    SOURCE_LIMIT_OPTIONS = (3, 5, 6, 8, 10)

    def __init__(
        self,
        translations: I18n,
        settings: AppSettings,
        rag_service: RagService,
        chat_history_repository: ChatHistoryRepository,
        search_service: SearchService,
        llm_client: AIClient,
    ) -> None:
        super().__init__()
        self._translations = translations
        self._settings = settings
        self._rag_service = rag_service
        self._chat_history_repository = chat_history_repository
        self._search_service = search_service
        self._llm_client = llm_client
        self._searchable_publications: list[Publication] = []
        self._messages = self._chat_history_repository.list_messages()
        self._is_busy = False

        self.setObjectName("ChatPanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        header_layout = QVBoxLayout()
        header_layout.setSpacing(8)
        self._title = QLabel()
        self._title.setObjectName("PageTitle")
        self._description = QLabel()
        self._description.setObjectName("PageSubtitle")
        self._description.setWordWrap(True)
        self._privacy_warning = QLabel()
        self._privacy_warning.setObjectName("PrivacyWarning")
        self._privacy_warning.setWordWrap(True)
        self._sources_status = QLabel()
        self._sources_status.setObjectName("DetailMeta")
        header_layout.addWidget(self._title)
        header_layout.addWidget(self._description)
        header_layout.addWidget(self._privacy_warning)
        header_layout.addWidget(self._sources_status)
        layout.addLayout(header_layout)

        model_frame = QFrame()
        model_frame.setObjectName("ModelStatus")
        model_layout = QHBoxLayout(model_frame)
        model_layout.setContentsMargins(16, 14, 16, 14)
        model_layout.setSpacing(12)
        model_text_layout = QVBoxLayout()
        model_text_layout.setSpacing(6)
        self._model_status = QLabel()
        self._model_status.setObjectName("StatusBadge")
        self._model_status_detail = QLabel()
        self._model_status_detail.setObjectName("DetailMeta")
        self._model_status_detail.setWordWrap(True)
        model_text_layout.addWidget(self._model_status, 0, Qt.AlignmentFlag.AlignLeft)
        model_text_layout.addWidget(self._model_status_detail)
        self._test_connection_button = QPushButton()
        self._test_connection_button.setObjectName("SecondaryButton")
        self._test_connection_button.clicked.connect(self._test_connection)
        self._configure_ai_button = QPushButton()
        self._configure_ai_button.setObjectName("PrimaryButton")
        self._configure_ai_button.clicked.connect(self.configure_ai_requested.emit)
        model_layout.addLayout(model_text_layout, 1)
        model_layout.addWidget(self._configure_ai_button)
        model_layout.addWidget(self._test_connection_button)
        layout.addWidget(model_frame)

        filters_frame = QFrame()
        filters_frame.setObjectName("ToolbarFrame")
        filters_layout = QHBoxLayout(filters_frame)
        filters_layout.setContentsMargins(14, 12, 14, 12)
        filters_layout.setSpacing(12)
        self._language_filter_label = QLabel()
        self._publication_filter_label = QLabel()
        self._sources_count_label = QLabel()
        self._language_filter = self._create_combo()
        self._publication_filter = self._create_combo()
        self._sources_count_combo = self._create_combo()
        filters_layout.addWidget(self._language_filter_label)
        filters_layout.addWidget(self._language_filter)
        filters_layout.addWidget(self._publication_filter_label)
        filters_layout.addWidget(self._publication_filter, 1)
        filters_layout.addWidget(self._sources_count_label)
        filters_layout.addWidget(self._sources_count_combo)
        layout.addWidget(filters_frame)

        self._history = QTextBrowser()
        self._history.setObjectName("ChatHistory")
        self._history.setOpenExternalLinks(False)
        layout.addWidget(self._history, 1)

        self._input = QTextEdit()
        self._input.setObjectName("ChatInput")
        self._input.setMinimumHeight(90)
        self._input.setMaximumHeight(130)
        layout.addWidget(self._input)

        self._shortcut_hint = QLabel()
        self._shortcut_hint.setObjectName("DetailMeta")
        layout.addWidget(self._shortcut_hint)

        actions_layout = QHBoxLayout()
        actions_layout.addStretch(1)
        self._clear_button = QPushButton()
        self._clear_button.setObjectName("SecondaryButton")
        self._clear_button.clicked.connect(self._clear_history)
        self._copy_last_button = QPushButton()
        self._copy_last_button.setObjectName("SecondaryButton")
        self._copy_last_button.clicked.connect(self._copy_last_answer)
        self._copy_last_with_sources_button = QPushButton()
        self._copy_last_with_sources_button.setObjectName("SecondaryButton")
        self._copy_last_with_sources_button.clicked.connect(self._copy_last_answer_with_sources)
        self._send_button = QPushButton()
        self._send_button.setObjectName("PrimaryButton")
        self._send_button.clicked.connect(self._send_question)
        actions_layout.addWidget(self._clear_button)
        actions_layout.addWidget(self._copy_last_button)
        actions_layout.addWidget(self._copy_last_with_sources_button)
        actions_layout.addWidget(self._send_button)
        layout.addLayout(actions_layout)

        self._send_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self._input)
        self._send_shortcut.activated.connect(self._send_question)

        self.update_texts()
        self.refresh_sources()
        self._render_history()

    def refresh_sources(self) -> None:
        selected_publication = self._publication_filter.currentData()
        self._searchable_publications = self._search_service.list_searchable_publications()
        self._populate_publication_filter(selected_publication or "all")
        count = len(self._searchable_publications)
        if count:
            self._sources_status.setText(self._translations.t("chat.sources_status.available").format(count=count))
        else:
            self._sources_status.setText(self._translations.t("chat.sources_status.none"))
        self._update_model_status()

    def update_texts(self) -> None:
        selected_language = self._language_filter.currentData() or "all"
        selected_publication = self._publication_filter.currentData() or "all"
        selected_sources = self._sources_count_combo.currentData() or self._settings.retrieval_limit()

        self._title.setText(self._translations.t("chat.title"))
        self._description.setText(self._translations.t("chat.description"))
        self._test_connection_button.setText(self._translations.t("chat.model.test_connection"))
        self._configure_ai_button.setText(self._translations.t("chat.configure_ai"))
        self._language_filter_label.setText(self._translations.t("chat.filters.language"))
        self._publication_filter_label.setText(self._translations.t("chat.filters.publication"))
        self._sources_count_label.setText(self._translations.t("chat.filters.sources_count"))
        self._input.setPlaceholderText(self._translations.t("chat.input.placeholder"))
        self._send_button.setText(self._translations.t("chat.send"))
        self._clear_button.setText(self._translations.t("chat.clear"))
        self._copy_last_button.setText(self._translations.t("chat.copy_last_answer"))
        self._copy_last_with_sources_button.setText(self._translations.t("chat.copy_last_answer_with_sources"))
        self._shortcut_hint.setText(self._translations.t("chat.shortcut_hint"))

        self._populate_language_filter(selected_language)
        self._populate_publication_filter(selected_publication)
        self._populate_sources_count(selected_sources)
        self._update_model_status()
        self.refresh_sources()
        self._render_history()

    def _create_combo(self) -> QComboBox:
        combo = QComboBox()
        combo.setObjectName("FilterCombo")
        return combo

    def _populate_language_filter(self, selected_value: object) -> None:
        self._language_filter.blockSignals(True)
        self._language_filter.clear()
        for value, label_key in self.LANGUAGE_FILTERS:
            self._language_filter.addItem(self._translations.t(label_key), value)
        index = self._language_filter.findData(selected_value)
        self._language_filter.setCurrentIndex(index if index >= 0 else 0)
        self._language_filter.blockSignals(False)

    def _populate_publication_filter(self, selected_value: object = "all") -> None:
        self._publication_filter.blockSignals(True)
        self._publication_filter.clear()
        self._publication_filter.addItem(self._translations.t("chat.filters.all_publications"), "all")
        for publication in self._searchable_publications:
            self._publication_filter.addItem(publication.title, publication.id)
        index = self._publication_filter.findData(selected_value)
        self._publication_filter.setCurrentIndex(index if index >= 0 else 0)
        self._publication_filter.blockSignals(False)

    def _populate_sources_count(self, selected_value: object) -> None:
        self._sources_count_combo.blockSignals(True)
        self._sources_count_combo.clear()
        for value in self.SOURCE_LIMIT_OPTIONS:
            self._sources_count_combo.addItem(str(value), value)
        index = self._sources_count_combo.findData(selected_value)
        self._sources_count_combo.setCurrentIndex(index if index >= 0 else 2)
        self._sources_count_combo.blockSignals(False)

    def _send_question(self) -> None:
        question = self._input.toPlainText().strip()
        if not question:
            self._append_system_status("rag.empty_question")
            return
        if not self._search_service.has_indexed_content():
            self._append_system_status("rag.no_indexed_publications")
            return
        if self._settings.ai_mode() != "manual" and not self._llm_client.is_ready():
            self._append_system_status(f"chat.ai_status_help.{self._llm_client.status()}")
            return

        self._set_busy(True)
        user_message = ChatMessage.create("user", question)
        self._messages.append(user_message)
        self._chat_history_repository.save_messages(self._messages)
        self._input.clear()
        self._render_history()
        QApplication.processEvents()

        result = self._rag_service.answer_question(
            question=question,
            config=self._settings.llm_config(),
            language=str(self._language_filter.currentData() or "all"),
            publication_id=str(self._publication_filter.currentData() or "all"),
            retrieval_limit=int(self._sources_count_combo.currentData() or self._settings.retrieval_limit()),
        )
        answer_text = self._answer_text(result)
        assistant_message = ChatMessage.create(
            "assistant",
            answer_text,
            [source.to_dict() for source in result.sources],
        )
        self._messages.append(assistant_message)
        self._chat_history_repository.save_messages(self._messages)
        self._set_busy(False)
        self._render_history()

    def _answer_text(self, result: RagAnswer) -> str:
        if result.error_message == "insufficient_sources":
            return f"{self._translations.t('rag.insufficient_sources')}\n\n{self._translations.t('chat.insufficient_sources_suggestion')}"
        if result.error_message == "empty_question":
            return self._translations.t("rag.empty_question")
        if result.error_message == "no_indexed_publications":
            return self._translations.t("rag.no_indexed_publications")
        if result.error_message == "llm_error":
            return self._translations.t("chat.local_model_error")
        return result.answer

    def _render_history(self) -> None:
        if not self._messages:
            self._history.setHtml(f"<p class='empty'>{html.escape(self._translations.t('chat.initial_hint'))}</p>")
            return

        blocks: list[str] = []
        for message in self._messages:
            label_key = "chat.user_label" if message.role == "user" else "chat.assistant_label"
            class_name = "user-message" if message.role == "user" else "assistant-message"
            blocks.append(
                f"<div class='{class_name}'><b>{html.escape(self._translations.t(label_key))}</b>"
                f"<p>{html.escape(message.content).replace(chr(10), '<br>')}</p></div>"
            )
            if message.role == "assistant":
                sources = [ChatSource.from_dict(source) for source in message.sources if isinstance(source, dict)]
                blocks.append(self._render_sources(sources))
        self._history.setHtml(self._history_css() + "".join(blocks))
        self._history.moveCursor(QTextCursor.MoveOperation.End)

    def _render_sources(self, sources: list[ChatSource]) -> str:
        if not sources:
            return f"<div class='sources'><b>{html.escape(self._translations.t('chat.sources_title'))}</b><p>{html.escape(self._translations.t('chat.no_sources'))}</p></div>"
        items = []
        for source in sources:
            reference = html.escape(self._format_source_reference(source))
            snippet = html.escape(source.snippet)
            score_label = html.escape(self._translations.t("study.detail.score"))
            items.append(f"<li><b>[{html.escape(source.source_id)}]</b> {reference}<br><span>{snippet}</span><br><span>{score_label}: {source.score:.2f}</span></li>")
        return f"<div class='sources'><b>{html.escape(self._translations.t('chat.sources_title'))}</b><ul>{''.join(items)}</ul></div>"

    def _format_source_reference(self, source: ChatSource) -> str:
        if source.page_start is None:
            return self._translations.t("study.reference.chunk").format(
                title=source.publication_title,
                chunk=source.chunk_index + 1,
            )
        if source.page_end is not None and source.page_end != source.page_start:
            return self._translations.t("study.reference.pages").format(
                title=source.publication_title,
                page_start=source.page_start,
                page_end=source.page_end,
            )
        return self._translations.t("study.reference.page").format(
            title=source.publication_title,
            page=source.page_start,
        )

    def _history_css(self) -> str:
        return """
        <style>
        body {
            font-family: Segoe UI, Arial, sans-serif;
            color: #0f172a;
            background: #f8fafc;
            line-height: 1.45;
        }
        .user-message, .assistant-message, .sources {
            border: 1px solid #e2e8f0;
            border-radius: 14px;
            padding: 13px 15px;
            margin: 10px 0;
        }
        .user-message {
            background: #dbeafe;
            border-color: #bfdbfe;
            margin-left: 44px;
        }
        .assistant-message {
            background: #ffffff;
            margin-right: 28px;
        }
        .user-message b, .assistant-message b {
            color: #334155;
            font-size: 12px;
        }
        .user-message p, .assistant-message p {
            margin: 8px 0 0 0;
            font-size: 14px;
        }
        .sources {
            background: #f8fafc;
            color: #475569;
            margin-right: 28px;
        }
        .sources ul {
            margin: 8px 0 0 0;
            padding-left: 0;
            list-style: none;
        }
        .sources li {
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            padding: 10px;
            margin: 8px 0;
        }
        .sources span { color: #64748b; }
        .empty { color: #64748b; padding: 18px; }
        </style>
        """

    def _copy_last_answer(self) -> None:
        for message in reversed(self._messages):
            if message.role == "assistant":
                QApplication.clipboard().setText(message.content)
                self._append_system_status("chat.answer_copied")
                return

    def _copy_last_answer_with_sources(self) -> None:
        for message in reversed(self._messages):
            if message.role != "assistant":
                continue
            parts = [message.content]
            sources = [ChatSource.from_dict(source) for source in message.sources if isinstance(source, dict)]
            if sources:
                parts.append("")
                parts.append(self._translations.t("chat.sources_title"))
                for source in sources:
                    parts.append(f"[{source.source_id}] {self._format_source_reference(source)}")
            QApplication.clipboard().setText("\n".join(parts))
            self._append_system_status("chat.answer_copied_with_sources")
            return

    def _clear_history(self) -> None:
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setWindowTitle(self._translations.t("chat.confirm_clear_title"))
        dialog.setText(self._translations.t("chat.confirm_clear_message"))
        no_button = dialog.addButton(self._translations.t("common.no"), QMessageBox.ButtonRole.RejectRole)
        yes_button = dialog.addButton(self._translations.t("common.yes"), QMessageBox.ButtonRole.AcceptRole)
        dialog.setDefaultButton(no_button)
        dialog.exec()
        if dialog.clickedButton() != yes_button:
            return
        self._messages = []
        self._chat_history_repository.clear_history()
        self._render_history()
        self._append_system_status("chat.history_cleared")

    def _test_connection(self) -> None:
        self._set_busy(True)
        QApplication.processEvents()
        ok, _message = self._llm_client.test_connection(self._settings.llm_config())
        self._set_busy(False)
        self._append_system_status("chat.model.connection_success" if ok else "chat.model.connection_failed")

    def _append_system_status(self, key: str) -> None:
        self._sources_status.setText(self._translations.t(key))

    def _update_model_status(self) -> None:
        status = self._llm_client.status()
        if self._settings.ai_mode() == "manual":
            endpoint = self._settings.ai_manual_endpoint_url()
            model = self._settings.ai_manual_model_name()
            self._model_status.setText(self._translations.t("settings.ai_status_values.manual_mode"))
            self._model_status.setProperty("status", "manual_mode")
            self._model_status_detail.setText(
                f"{self._translations.t('chat.manual_mode_active')} | {self._translations.t('chat.model.endpoint')}: {endpoint} | {self._translations.t('chat.model.model')}: {model}"
            )
            self._configure_ai_button.setVisible(True)
            self._privacy_warning.setVisible(bool(endpoint and not is_local_endpoint(endpoint)))
        else:
            self._model_status.setText(self._translations.t(f"settings.ai_status_values.{status}"))
            self._model_status.setProperty("status", status)
            self._model_status_detail.setText(self._translations.t(f"chat.ai_status.{status}"))
            self._configure_ai_button.setVisible(status != AIStatus.READY)
            self._privacy_warning.setVisible(False)
        self._privacy_warning.setText(self._translations.t("chat.remote_endpoint_warning"))
        self._model_status.style().unpolish(self._model_status)
        self._model_status.style().polish(self._model_status)

    def _set_busy(self, is_busy: bool) -> None:
        self._is_busy = is_busy
        self._send_button.setEnabled(not is_busy)
        self._clear_button.setEnabled(not is_busy)
        self._copy_last_button.setEnabled(not is_busy)
        self._copy_last_with_sources_button.setEnabled(not is_busy)
        self._test_connection_button.setEnabled(not is_busy)
        self._configure_ai_button.setEnabled(not is_busy)
        self._input.setEnabled(not is_busy)
        if is_busy:
            self._append_system_status("chat.busy")
