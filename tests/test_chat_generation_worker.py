import os
import threading
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QThread, Qt
from PySide6.QtWidgets import QApplication

from app.ai.chat_generation_worker import AIConnectionTestWorker, ChatGenerationWorker
from app.services.local_llm_client import LLMErrorCode, LLMErrorDetails
from app.services.rag_service import RagAnswer


class FakeRagService:
    def __init__(self, result: RagAnswer | None = None, *, wait_for_cancel: bool = False) -> None:
        self.result = result or RagAnswer("Answer [S1]", [], True, "")
        self.wait_for_cancel = wait_for_cancel
        self.thread = None
        self.cancel_calls = 0
        self.started = threading.Event()

    def answer_question(self, **kwargs):
        self.thread = QThread.currentThread()
        self.started.set()
        kwargs["phase_callback"]("building_prompt")
        kwargs["progress_callback"](40)
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


class FakeAIClient:
    def __init__(self, result=(True, "ok")) -> None:
        self.result = result
        self.thread = None

    def test_connection(self):
        self.thread = QThread.currentThread()
        return self.result


class ChatGenerationWorkerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _start_worker(self, worker, terminal_signals):
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        for signal in terminal_signals:
            signal.connect(thread.quit, Qt.ConnectionType.DirectConnection)
        thread.start()
        return thread

    def test_generation_runs_outside_gui_thread_and_streams_signals(self) -> None:
        rag = FakeRagService()
        worker = ChatGenerationWorker(rag, "Question")
        phases = []
        progress = []
        tokens = []
        completed = []
        worker.phase_changed.connect(phases.append, Qt.ConnectionType.DirectConnection)
        worker.progress_changed.connect(progress.append, Qt.ConnectionType.DirectConnection)
        worker.token_received.connect(tokens.append, Qt.ConnectionType.DirectConnection)
        worker.completed.connect(completed.append, Qt.ConnectionType.DirectConnection)

        thread = self._start_worker(worker, (worker.completed, worker.failed, worker.cancelled))
        self.assertTrue(thread.wait(3000))

        self.assertIsNot(rag.thread, self.app.thread())
        self.assertEqual(phases, ["building_prompt"])
        self.assertEqual(progress, [40])
        self.assertEqual(tokens, ["Answer ", "[S1]"])
        self.assertEqual(completed[0].answer, "Answer [S1]")

    def test_structured_failure_uses_failed_signal(self) -> None:
        details = LLMErrorDetails(LLMErrorCode.READ_TIMEOUT, "read timeout", retryable=True)
        rag = FakeRagService(RagAnswer("", [], False, LLMErrorCode.READ_TIMEOUT.value, details))
        worker = ChatGenerationWorker(rag, "Question")
        failures = []
        worker.failed.connect(failures.append, Qt.ConnectionType.DirectConnection)

        thread = self._start_worker(worker, (worker.completed, worker.failed, worker.cancelled))
        self.assertTrue(thread.wait(3000))

        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0].error.code, LLMErrorCode.READ_TIMEOUT)

    def test_cancellation_interrupts_worker_without_completion(self) -> None:
        rag = FakeRagService(wait_for_cancel=True)
        worker = ChatGenerationWorker(rag, "Question")
        cancelled = []
        completed = []
        worker.cancelled.connect(cancelled.append, Qt.ConnectionType.DirectConnection)
        worker.completed.connect(completed.append, Qt.ConnectionType.DirectConnection)

        thread = self._start_worker(worker, (worker.completed, worker.failed, worker.cancelled))
        self.assertTrue(rag.started.wait(1.0))
        worker.request_cancel()
        self.assertTrue(thread.wait(3000))

        self.assertEqual(rag.cancel_calls, 1)
        self.assertEqual(len(cancelled), 1)
        self.assertEqual(completed, [])

    def test_connection_test_runs_outside_gui_thread(self) -> None:
        client = FakeAIClient()
        worker = AIConnectionTestWorker(client)
        results = []
        worker.completed.connect(lambda ok, message: results.append((ok, message)), Qt.ConnectionType.DirectConnection)

        thread = self._start_worker(worker, (worker.completed,))
        self.assertTrue(thread.wait(3000))

        self.assertIsNot(client.thread, self.app.thread())
        self.assertEqual(results, [(True, "ok")])


if __name__ == "__main__":
    unittest.main()
