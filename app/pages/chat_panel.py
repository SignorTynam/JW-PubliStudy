from __future__ import annotations

import html

from PySide6.QtCore import QThread, QTimer, Qt, Signal
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
from app.ai.chat_generation_worker import AIConnectionTestWorker, ChatGenerationWorker
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
        self._busy_cancellable = False
        self._pending_answer_text = ""
        self._generation_thread: QThread | None = None
        self._generation_worker: ChatGenerationWorker | None = None
        self._connection_thread: QThread | None = None
        self._connection_worker: AIConnectionTestWorker | None = None
        self._close_retry_scheduled = False
        self._stream_render_timer = QTimer(self)
        self._stream_render_timer.setInterval(50)
        self._stream_render_timer.setSingleShot(True)
        self._stream_render_timer.timeout.connect(self._render_history)

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
        show_manual_source_limit = self._settings.ai_mode() == "manual"
        self._sources_count_label.setVisible(show_manual_source_limit)
        self._sources_count_combo.setVisible(show_manual_source_limit)
        if self._is_busy and self._busy_cancellable:
            self._send_button.setText(self._translations.t("chat.cancel_generation"))
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
        if self._is_busy:
            if self._busy_cancellable:
                self._cancel_generation()
            return
        question = self._input.toPlainText().strip()
        if not question:
            self._append_system_status("rag.empty_question")
            return
        if self._settings.ai_mode() != "manual" and not self._llm_client.is_ready():
            self._append_system_status(f"chat.ai_status_help.{self._llm_client.status()}")
            return

        self._set_busy(True, cancellable=True)
        user_message = ChatMessage.create("user", question)
        self._messages.append(user_message)
        self._chat_history_repository.save_messages(self._messages)
        self._input.clear()
        self._render_history()
        self._pending_answer_text = ""
        self._generation_thread = QThread(self)
        self._generation_worker = ChatGenerationWorker(
            self._rag_service,
            question,
            language=str(self._language_filter.currentData() or "all"),
            publication_id=str(self._publication_filter.currentData() or "all"),
            retrieval_limit=self._settings.retrieval_limit() if self._settings.ai_mode() == "manual" else None,
        )
        worker = self._generation_worker
        thread = self._generation_thread
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.phase_changed.connect(self._on_generation_phase)
        worker.progress_changed.connect(self._on_generation_progress)
        worker.retrying.connect(self._on_generation_retry)
        worker.token_received.connect(self._on_generation_token)
        worker.completed.connect(self._on_generation_completed)
        worker.failed.connect(self._on_generation_failed)
        worker.cancelled.connect(self._on_generation_cancelled)
        for signal in (worker.completed, worker.failed, worker.cancelled):
            signal.connect(thread.quit, Qt.ConnectionType.DirectConnection)
            signal.connect(worker.deleteLater)
        thread.finished.connect(self._on_generation_thread_finished)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _on_generation_phase(self, phase: str) -> None:
        self._append_system_status(f"chat.request_phase.{phase}")

    def _on_generation_progress(self, _progress: int) -> None:
        return

    def _on_generation_retry(self, _attempt: int, _reason: str) -> None:
        self._stream_render_timer.stop()
        self._pending_answer_text = ""
        self._render_history()
        self._append_system_status("chat.request_phase.retrying")

    def _on_generation_token(self, token: str) -> None:
        self._pending_answer_text += token
        if not self._stream_render_timer.isActive():
            self._stream_render_timer.start()

    def _on_generation_completed(self, result: RagAnswer) -> None:
        self._stream_render_timer.stop()
        assistant_message = ChatMessage.create(
            "assistant",
            result.answer,
            [source.to_dict() for source in result.sources],
        )
        self._messages.append(assistant_message)
        self._chat_history_repository.save_messages(self._messages)
        self._pending_answer_text = ""
        self._render_history()
        self._append_system_status("chat.request_phase.completed")

    def _on_generation_failed(self, result: RagAnswer) -> None:
        self._stream_render_timer.stop()
        self._pending_answer_text = ""
        self._messages.append(ChatMessage.create("system", self._answer_text(result)))
        self._chat_history_repository.save_messages(self._messages)
        self._render_history()

    def _on_generation_cancelled(self, _result: RagAnswer) -> None:
        self._stream_render_timer.stop()
        self._pending_answer_text = ""
        self._messages.append(ChatMessage.create("system", self._translations.t("chat.request_errors.cancelled")))
        self._chat_history_repository.save_messages(self._messages)
        self._render_history()
        self._append_system_status("chat.request_phase.cancelled")

    def _on_generation_thread_finished(self) -> None:
        self._generation_worker = None
        self._generation_thread = None
        self._set_busy(False)

    def _cancel_generation(self) -> None:
        if self._generation_worker is None:
            return
        self._append_system_status("chat.cancelling_generation")
        self._send_button.setEnabled(False)
        self._generation_worker.request_cancel()

    def _answer_text(self, result: RagAnswer) -> str:
        if result.error_message == "insufficient_sources":
            return f"{self._translations.t('rag.insufficient_sources')}\n\n{self._translations.t('chat.insufficient_sources_suggestion')}"
        if result.error_message == "empty_question":
            return self._translations.t("rag.empty_question")
        if result.error_message == "no_indexed_publications":
            return self._translations.t("rag.no_indexed_publications")
        if result.error_message == "llm_error":
            return self._translations.t("chat.local_model_error")
        if result.error is not None:
            key = f"chat.request_errors.{result.error.code.value}"
            translated = self._translations.t(key)
            return translated if translated != key else self._translations.t("chat.request_errors.unknown_error")
        if result.error_message:
            key = f"chat.request_errors.{result.error_message}"
            translated = self._translations.t(key)
            return translated if translated != key else self._translations.t("chat.request_errors.unknown_error")
        return result.answer

    def _render_history(self) -> None:
        if not self._messages:
            self._history.setHtml(f"<p class='empty'>{html.escape(self._translations.t('chat.initial_hint'))}</p>")
            return

        blocks: list[str] = []
        for message in self._messages:
            if message.role == "user":
                label_key = "chat.user_label"
                class_name = "user-message"
            elif message.role == "system":
                label_key = "chat.system_label"
                class_name = "system-message"
            else:
                label_key = "chat.assistant_label"
                class_name = "assistant-message"
            blocks.append(
                f"<div class='{class_name}'><b>{html.escape(self._translations.t(label_key))}</b>"
                f"<p>{html.escape(message.content).replace(chr(10), '<br>')}</p></div>"
            )
            if message.role == "assistant":
                sources = [ChatSource.from_dict(source) for source in message.sources if isinstance(source, dict)]
                blocks.append(self._render_sources(sources))
        if self._pending_answer_text:
            blocks.append(
                f"<div class='assistant-message pending'><b>{html.escape(self._translations.t('chat.assistant_label'))}</b>"
                f"<p>{html.escape(self._pending_answer_text).replace(chr(10), '<br>')}</p></div>"
            )
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
        .user-message, .assistant-message, .system-message, .sources {
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
        .system-message {
            background: #fff7ed;
            border-color: #fed7aa;
            color: #9a3412;
        }
        .pending { border-style: dashed; }
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
        if self._is_busy:
            return
        self._set_busy(True, cancellable=False)
        self._append_system_status("chat.model.testing_connection")
        self._connection_thread = QThread(self)
        self._connection_worker = AIConnectionTestWorker(self._llm_client)
        worker = self._connection_worker
        thread = self._connection_thread
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.completed.connect(self._on_connection_test_completed)
        worker.completed.connect(thread.quit, Qt.ConnectionType.DirectConnection)
        worker.completed.connect(worker.deleteLater)
        thread.finished.connect(self._on_connection_thread_finished)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _on_connection_test_completed(self, ok: bool, _message: str) -> None:
        self._append_system_status("chat.model.connection_success" if ok else "chat.model.connection_failed")

    def _on_connection_thread_finished(self) -> None:
        self._connection_worker = None
        self._connection_thread = None
        self._set_busy(False)

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

    def _set_busy(self, is_busy: bool, *, cancellable: bool = False) -> None:
        self._is_busy = is_busy
        self._busy_cancellable = is_busy and cancellable
        self._send_button.setEnabled(not is_busy or cancellable)
        self._send_button.setText(
            self._translations.t("chat.cancel_generation") if is_busy and cancellable else self._translations.t("chat.send")
        )
        self._clear_button.setEnabled(not is_busy)
        self._copy_last_button.setEnabled(not is_busy)
        self._copy_last_with_sources_button.setEnabled(not is_busy)
        self._test_connection_button.setEnabled(not is_busy)
        self._configure_ai_button.setEnabled(not is_busy)
        self._input.setEnabled(not is_busy)
        if is_busy:
            self._append_system_status("chat.busy")

    def cancel_pending_request(self, wait_ms: int = 0) -> bool:
        if self._generation_worker is not None:
            self._generation_worker.request_cancel()
        if self._connection_thread is not None and self._connection_thread.isRunning():
            self._llm_client.cancel_active_request()
        generation_stopped = True
        connection_stopped = True
        if self._generation_thread is not None and wait_ms > 0:
            generation_stopped = self._generation_thread.wait(wait_ms)
        elif self._generation_thread is not None:
            generation_stopped = not self._generation_thread.isRunning()
        if self._connection_thread is not None and wait_ms > 0:
            connection_stopped = self._connection_thread.wait(wait_ms)
        elif self._connection_thread is not None:
            connection_stopped = not self._connection_thread.isRunning()
        return generation_stopped and connection_stopped

    def closeEvent(self, event) -> None:
        if not self.cancel_pending_request():
            event.ignore()
            if not self._close_retry_scheduled:
                self._close_retry_scheduled = True
                QTimer.singleShot(100, self._retry_close)
            return
        super().closeEvent(event)

    def _retry_close(self) -> None:
        self._close_retry_scheduled = False
        self.close()
