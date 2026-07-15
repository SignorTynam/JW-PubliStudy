import os
import threading
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QThread, QTimer
from PySide6.QtWidgets import QApplication

from app.pages.chat_panel import ChatPanel
from app.services.local_llm_client import LLMErrorCode, LLMErrorDetails
from app.services.rag_service import RagAnswer


class FakeTranslations:
    def t(self, key: str) -> str:
        if key == "chat.request_errors.read_timeout":
            return "The local response timed out."
        return key


class FakeSettings:
    def __init__(self, mode: str = "auto") -> None:
        self.mode = mode

    def ai_mode(self):
        return self.mode

    def retrieval_limit(self):
        return 6

    def ai_manual_endpoint_url(self):
        return "http://127.0.0.1:1234/v1/chat/completions"

    def ai_manual_model_name(self):
        return "local-model"


class FakeHistoryRepository:
    def __init__(self) -> None:
        self.saved = []

    def list_messages(self):
        return []

    def save_messages(self, messages):
        self.saved.append(list(messages))

    def clear_history(self):
        pass


class FakeSearchService:
    def list_searchable_publications(self):
        return []


class FakeAIClient:
    def __init__(self) -> None:
        self.connection_thread = None
        self.cancel_calls = 0

    def is_ready(self):
        return True

    def status(self):
        return "ready"

    def test_connection(self):
        self.connection_thread = QThread.currentThread()
        return True, "ok"

    def cancel_active_request(self):
        self.cancel_calls += 1


class FakeRagService:
    def __init__(self, result: RagAnswer | None = None, *, wait_for_cancel: bool = False) -> None:
        self.result = result or RagAnswer("Answer [S1]", [], True, "")
        self.wait_for_cancel = wait_for_cancel
        self.thread = None
        self.started = threading.Event()
        self.calls = 0
        self.cancel_calls = 0

    def answer_question(self, **kwargs):
        self.calls += 1
        self.thread = QThread.currentThread()
        self.started.set()
        kwargs["phase_callback"]("preparing_sources")
        if self.wait_for_cancel:
            kwargs["cancellation_event"].wait(2.0)
            return RagAnswer(
                "",
                [],
                False,
                LLMErrorCode.CANCELLED.value,
                LLMErrorDetails(LLMErrorCode.CANCELLED, "cancelled", retryable=False),
            )
        kwargs["token_callback"]("Answer ")
        kwargs["token_callback"]("[S1]")
        return self.result

    def cancel_active_request(self):
        self.cancel_calls += 1


class ChatPanelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _panel(self, rag, *, mode="auto"):
        history = FakeHistoryRepository()
        ai_client = FakeAIClient()
        panel = ChatPanel(
            FakeTranslations(),
            FakeSettings(mode),
            rag,
            history,
            FakeSearchService(),
            ai_client,
        )
        return panel, history, ai_client

    def _wait_until(self, predicate, timeout=3.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.processEvents()
            if predicate():
                return True
            time.sleep(0.005)
        self.app.processEvents()
        return predicate()

    def _dispose(self, panel):
        panel.cancel_pending_request(3000)
        self._wait_until(lambda: panel._generation_thread is None and panel._connection_thread is None)
        panel.deleteLater()
        self.app.processEvents()

    def test_send_keeps_gui_responsive_and_persists_one_final_answer(self) -> None:
        release = threading.Event()

        class DelayedRag(FakeRagService):
            def answer_question(inner_self, **kwargs):
                inner_self.calls += 1
                inner_self.thread = QThread.currentThread()
                inner_self.started.set()
                release.wait(2.0)
                kwargs["token_callback"]("Answer [S1]")
                return inner_self.result

        rag = DelayedRag()
        panel, history, _client = self._panel(rag)
        panel._input.setPlainText("Question")
        panel._send_question()
        self.assertTrue(rag.started.wait(1.0))

        gui_callback = threading.Event()
        QTimer.singleShot(0, gui_callback.set)
        self.assertTrue(self._wait_until(gui_callback.is_set, 1.0))
        self.assertTrue(panel._is_busy)
        self.assertIsNot(rag.thread, self.app.thread())

        release.set()
        self.assertTrue(self._wait_until(lambda: panel._generation_thread is None))
        self.assertEqual([message.role for message in panel._messages], ["user", "assistant"])
        self.assertEqual(panel._messages[-1].content, "Answer [S1]")
        self.assertEqual(len(history.saved), 2)
        self.assertFalse(panel._is_busy)
        self._dispose(panel)

    def test_second_send_cancels_instead_of_starting_duplicate_request(self) -> None:
        rag = FakeRagService(wait_for_cancel=True)
        panel, _history, _client = self._panel(rag)
        panel._input.setPlainText("Question")
        panel._send_question()
        self.assertTrue(rag.started.wait(1.0))

        panel._send_question()
        self.assertTrue(self._wait_until(lambda: panel._generation_thread is None))

        self.assertEqual(rag.calls, 1)
        self.assertEqual(rag.cancel_calls, 1)
        self.assertEqual([message.role for message in panel._messages], ["user", "system"])
        self.assertEqual(panel._messages[-1].content, "chat.request_errors.cancelled")
        self.assertFalse(panel._is_busy)
        self._dispose(panel)

    def test_structured_timeout_is_not_reported_as_ai_not_ready(self) -> None:
        details = LLMErrorDetails(LLMErrorCode.READ_TIMEOUT, "read timeout", retryable=True)
        rag = FakeRagService(RagAnswer("", [], False, LLMErrorCode.READ_TIMEOUT.value, details))
        panel, _history, _client = self._panel(rag)
        panel._input.setPlainText("Question")
        panel._send_question()
        self.assertTrue(self._wait_until(lambda: panel._generation_thread is None))

        self.assertEqual([message.role for message in panel._messages], ["user", "system"])
        self.assertEqual(panel._messages[-1].content, "The local response timed out.")
        self.assertNotIn("chat.ai_status_help", panel._messages[-1].content)
        self._dispose(panel)

    def test_close_cancels_without_blocking_or_terminating_thread(self) -> None:
        rag = FakeRagService(wait_for_cancel=True)
        panel, _history, _client = self._panel(rag)
        panel.show()
        panel._input.setPlainText("Question")
        panel._send_question()
        self.assertTrue(rag.started.wait(1.0))

        started = time.monotonic()
        panel.close()
        self.assertLess(time.monotonic() - started, 0.25)
        self.assertEqual(rag.cancel_calls, 1)
        self.assertTrue(self._wait_until(lambda: panel._generation_thread is None))
        self.assertTrue(self._wait_until(lambda: not panel.isVisible()))
        self._dispose(panel)

    def test_connection_test_is_asynchronous(self) -> None:
        rag = FakeRagService()
        panel, _history, client = self._panel(rag)
        panel._test_connection()
        self.assertTrue(self._wait_until(lambda: panel._connection_thread is None))

        self.assertIsNot(client.connection_thread, self.app.thread())
        self.assertFalse(panel._is_busy)
        self.assertEqual(panel._sources_status.text(), "chat.model.connection_success")
        self._dispose(panel)

    def test_automatic_mode_hides_manual_source_count(self) -> None:
        auto_panel, _history, _client = self._panel(FakeRagService(), mode="auto")
        manual_panel, _history2, _client2 = self._panel(FakeRagService(), mode="manual")

        self.assertTrue(auto_panel._sources_count_combo.isHidden())
        self.assertFalse(manual_panel._sources_count_combo.isHidden())
        self._dispose(auto_panel)
        self._dispose(manual_panel)


if __name__ == "__main__":
    unittest.main()
