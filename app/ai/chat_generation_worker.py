from __future__ import annotations

import threading
from uuid import uuid4

from PySide6.QtCore import QObject, Signal, Slot

from app.services.local_llm_client import LLMErrorCode
from app.services.rag_service import RagAnswer, RagService


class ChatGenerationWorker(QObject):
    started = Signal(str)
    phase_changed = Signal(str)
    progress_changed = Signal(int)
    retrying = Signal(int, str)
    token_received = Signal(str)
    completed = Signal(object)
    failed = Signal(object)
    cancelled = Signal(object)

    def __init__(
        self,
        rag_service: RagService,
        question: str,
        *,
        language: str = "all",
        publication_id: str = "all",
        retrieval_limit: int | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__()
        self._rag_service = rag_service
        self._question = question
        self._language = language
        self._publication_id = publication_id
        self._retrieval_limit = retrieval_limit
        self._request_id = request_id or uuid4().hex
        self._cancellation_event = threading.Event()

    @property
    def request_id(self) -> str:
        return self._request_id

    @Slot()
    def run(self) -> None:
        self.started.emit(self._request_id)
        try:
            result = self._rag_service.answer_question(
                question=self._question,
                language=self._language,
                publication_id=self._publication_id,
                retrieval_limit=self._retrieval_limit,
                cancellation_event=self._cancellation_event,
                phase_callback=self.phase_changed.emit,
                progress_callback=self.progress_changed.emit,
                retry_callback=self.retrying.emit,
                token_callback=self.token_received.emit,
                request_id=self._request_id,
            )
        except Exception:
            result = RagAnswer("", [], False, LLMErrorCode.UNKNOWN_ERROR.value, request_id=self._request_id)
        if self._cancellation_event.is_set() or (result.error and result.error.code == LLMErrorCode.CANCELLED):
            self.cancelled.emit(result)
        elif result.error_message:
            self.failed.emit(result)
        else:
            self.completed.emit(result)

    def request_cancel(self) -> None:
        self._cancellation_event.set()
        self._rag_service.cancel_active_request()


class AIConnectionTestWorker(QObject):
    completed = Signal(bool, str)

    def __init__(self, ai_client) -> None:
        super().__init__()
        self._ai_client = ai_client

    @Slot()
    def run(self) -> None:
        try:
            ok, message = self._ai_client.test_connection()
        except Exception as exc:
            self.completed.emit(False, type(exc).__name__)
            return
        self.completed.emit(bool(ok), str(message))
