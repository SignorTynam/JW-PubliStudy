import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.ai.adaptive_request_planner import PerformanceProfileStore, RequestEnvironment
from app.services.local_llm_client import (
    LLMChatResult,
    LLMClientError,
    LLMConfig,
    LLMErrorCode,
    LLMErrorDetails,
    LLMHealthResult,
)
from app.services.rag_service import RagRequestState, RagService


def search_result(index: int, *, text: str | None = None, score: float | None = None):
    value = text or (f"relevant unique{index} evidence about hope and faith " * 50)
    return SimpleNamespace(
        chunk_id=f"publication:{index}",
        publication_id="publication",
        publication_title="Publication",
        source_filename="publication.pdf",
        language="it",
        page_start=index,
        page_end=index,
        chunk_index=index,
        text=value,
        snippet=value[:200],
        score=score if score is not None else float(20 - index),
    )


class FakeSearchService:
    def __init__(self, results=None, has_content=True):
        self.results = results if results is not None else [search_result(index) for index in range(1, 9)]
        self.has_content = has_content
        self.search_calls = []

    def has_indexed_content(self):
        return self.has_content

    def search(self, **kwargs):
        self.search_calls.append(kwargs)
        return self.results[: kwargs["limit"]]


class FakeAIClient:
    def __init__(self, outcomes=None, health=None):
        self.outcomes = list(outcomes or [LLMChatResult("Answer [S1]", 2.0, 0.5, 20, 200)])
        self.health = health or LLMHealthResult(True, True, True, 200, 200)
        self.plans = []
        self.configs = []
        self.messages = []
        self.events = []
        self.chat_calls = 0
        self.restart_calls = 0
        self.restart_result = True
        self.global_status = "ready"
        self.cancel_calls = 0

    def request_environment(self):
        return RequestEnvironment("medium", "Medium", 4096, 900, 16.0, 8.0)

    def build_request_config(self, plan):
        self.plans.append(plan)
        result = LLMConfig("http://127.0.0.1:1234/v1/chat/completions", "Medium", 0.2, plan.max_tokens, int(plan.read_timeout_seconds), 3, plan.read_timeout_seconds, True)
        self.configs.append(result)
        return result

    def chat_detailed(self, messages, config, **kwargs):
        self.chat_calls += 1
        self.messages.append(messages)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        callback = kwargs.get("on_token")
        if callback:
            callback(outcome.content)
        return outcome

    def check_health(self):
        return self.health

    def restart_runtime(self):
        self.restart_calls += 1
        return self.restart_result

    def cancel_active_request(self):
        self.cancel_calls += 1

    def record_request_event(self, message):
        self.events.append(message)

    def status(self):
        return self.global_status

    def get_active_endpoint(self):
        return "http://127.0.0.1:1234/v1/chat/completions"


def error(code: LLMErrorCode, *, retryable=True, attempt=1):
    return LLMClientError(LLMErrorDetails(code, code.value, retryable=retryable, attempt_number=attempt))


class RagServiceTest(unittest.TestCase):
    def _service(self, client=None, search=None):
        return RagService(
            search or FakeSearchService(),
            client or FakeAIClient(),
            performance_store=PerformanceProfileStore(),
        )

    def test_success_runs_phases_and_returns_exact_sources_sent_to_model(self) -> None:
        client = FakeAIClient()
        phases = []
        tokens = []
        service = self._service(client)
        result = service.answer_question(
            "Spiega la speranza usando le fonti.",
            phase_callback=phases.append,
            token_callback=tokens.append,
        )
        self.assertFalse(result.error_message)
        self.assertEqual(tokens, ["Answer [S1]"])
        self.assertIn(RagRequestState.PREPARING_SOURCES.value, phases)
        self.assertIn(RagRequestState.GENERATING.value, phases)
        self.assertIn(RagRequestState.COMPLETED.value, phases)
        prompt = client.messages[0][1]["content"]
        for source in result.sources:
            self.assertIn(f"[{source.source_id}]", prompt)
            self.assertIn(source.text, prompt)
        self.assertEqual(len(result.sources), len(client.plans[0].selected_sources))

    def test_no_indexed_content_does_not_call_model(self) -> None:
        client = FakeAIClient()
        result = self._service(client, FakeSearchService(has_content=False)).answer_question("Question")
        self.assertEqual(result.error_message, "no_indexed_publications")
        self.assertEqual(client.chat_calls, 0)

    def test_automatic_mode_retrieves_broad_set_and_manual_limit_remains_supported(self) -> None:
        automatic_search = FakeSearchService()
        manual_search = FakeSearchService()

        self._service(search=automatic_search).answer_question("Question")
        self._service(search=manual_search).answer_question("Question", retrieval_limit=3)

        self.assertEqual(automatic_search.search_calls[0]["limit"], 12)
        self.assertEqual(manual_search.search_calls[0]["limit"], 3)

    def test_read_timeout_with_live_runtime_retries_with_lighter_plan(self) -> None:
        client = FakeAIClient([error(LLMErrorCode.READ_TIMEOUT), LLMChatResult("Retry success", 2, 0.4, 20, 200)])
        retries = []
        with patch("app.services.rag_service.time.sleep"):
            result = self._service(client).answer_question("Analizza ampiamente tutte le prove e confronta ogni dettaglio disponibile nelle pubblicazioni.", retry_callback=lambda attempt, reason: retries.append((attempt, reason)))
        self.assertEqual(result.answer, "Retry success")
        self.assertEqual(client.chat_calls, 2)
        self.assertLess(len(client.plans[1].selected_sources), len(client.plans[0].selected_sources))
        self.assertLess(client.plans[1].max_tokens, client.plans[0].max_tokens)
        self.assertEqual(retries, [(2, LLMErrorCode.READ_TIMEOUT.value)])
        self.assertEqual(client.global_status, "ready")

    def test_context_overflow_rebuilds_prompt_before_retry(self) -> None:
        client = FakeAIClient([error(LLMErrorCode.CONTEXT_OVERFLOW), LLMChatResult("ok", 1, 0.2, 10, 200)])
        with patch("app.services.rag_service.time.sleep"):
            result = self._service(client).answer_question("Spiega in dettaglio tutte le informazioni e confronta le fonti disponibili.")
        self.assertEqual(result.answer, "ok")
        self.assertLess(client.plans[1].source_tokens, client.plans[0].source_tokens)

    def test_server_500_and_503_retry_once_then_succeed(self) -> None:
        for code in (LLMErrorCode.SERVER_ERROR, LLMErrorCode.SERVER_BUSY):
            with self.subTest(code=code):
                client = FakeAIClient([error(code), LLMChatResult("ok", 1, 0.2, 10, 200)])
                with patch("app.services.rag_service.time.sleep"):
                    result = self._service(client).answer_question("Question about hope")
                self.assertEqual(result.answer, "ok")
                self.assertEqual(client.chat_calls, 2)

    def test_connection_reset_restarts_unresponsive_runtime_once(self) -> None:
        client = FakeAIClient(
            [error(LLMErrorCode.CONNECTION_RESET), LLMChatResult("after restart", 1, 0.2, 10, 200)],
            health=LLMHealthResult(False, False, False),
        )
        with patch("app.services.rag_service.time.sleep"):
            result = self._service(client).answer_question("Question")
        self.assertEqual(result.answer, "after restart")

    def test_cancellation_during_runtime_restart_stops_the_request(self) -> None:
        cancellation_event = threading.Event()

        class CancellingRestartClient(FakeAIClient):
            def restart_runtime(self, *, cancellation_event=None):
                self.restart_calls += 1
                cancellation_event.set()
                return False

        client = CancellingRestartClient(
            [error(LLMErrorCode.CONNECTION_RESET)],
            health=LLMHealthResult(False, False, False),
        )
        result = self._service(client).answer_question("Question", cancellation_event=cancellation_event)

        self.assertEqual(client.restart_calls, 1)
        self.assertEqual(result.error.code, LLMErrorCode.CANCELLED)
        self.assertEqual(client.chat_calls, 1)

    def test_failed_restart_stops_retry_when_runtime_is_dead(self) -> None:
        client = FakeAIClient([error(LLMErrorCode.CONNECTION_FAILED)], health=LLMHealthResult(False, False, False))
        client.restart_result = False
        result = self._service(client).answer_question("Question")
        self.assertEqual(result.error_message, LLMErrorCode.CONNECTION_FAILED.value)
        self.assertEqual(client.chat_calls, 1)
        self.assertEqual(client.restart_calls, 1)

    def test_final_retry_failure_is_structured_and_limited_to_two_attempts(self) -> None:
        client = FakeAIClient([error(LLMErrorCode.SERVER_ERROR, attempt=1), error(LLMErrorCode.SERVER_ERROR, attempt=2)])
        with patch("app.services.rag_service.time.sleep"):
            result = self._service(client).answer_question("Question")
        self.assertEqual(client.chat_calls, 2)
        self.assertEqual(result.error.code, LLMErrorCode.SERVER_ERROR)
        self.assertEqual(result.error.attempt_number, 2)

    def test_no_retry_after_cancellation(self) -> None:
        client = FakeAIClient([error(LLMErrorCode.SERVER_ERROR)])
        cancellation = threading.Event()

        def cancel_on_retry(attempt, reason):
            del attempt, reason
            cancellation.set()

        with patch("app.services.rag_service.time.sleep"):
            result = self._service(client).answer_question("Question", cancellation_event=cancellation, retry_callback=cancel_on_retry)
        self.assertEqual(result.error.code, LLMErrorCode.CANCELLED)
        self.assertEqual(client.chat_calls, 1)

    def test_request_failure_does_not_change_global_ready_state(self) -> None:
        client = FakeAIClient([error(LLMErrorCode.READ_TIMEOUT), error(LLMErrorCode.READ_TIMEOUT, attempt=2)])
        with patch("app.services.rag_service.time.sleep"):
            result = self._service(client).answer_question("Question")
        self.assertEqual(result.error.code, LLMErrorCode.READ_TIMEOUT)
        self.assertEqual(client.global_status, "ready")

    def test_logs_use_length_and_hash_not_question_text(self) -> None:
        client = FakeAIClient()
        question = "Sensitive full question text"
        self._service(client).answer_question(question)
        logs = "\n".join(client.events)
        self.assertIn("question_length=", logs)
        self.assertIn("question_hash=", logs)
        self.assertNotIn(question, logs)
        self.assertIn("prompt_tokens=", logs)
        self.assertIn("read_timeout=", logs)
        self.assertIn("endpoint=http://127.0.0.1:1234/v1/chat/completions", logs)

    def test_technical_logs_cover_plan_timing_http_and_health_fields(self) -> None:
        success_client = FakeAIClient()
        self._service(success_client).answer_question("Question")
        success_logs = "\n".join(success_client.events)
        for marker in (
            "request_id=",
            "runtime_state=",
            "model=",
            "endpoint=",
            "candidates=",
            "sources_used=",
            "prompt_tokens=",
            "source_tokens=",
            "reserved_output_tokens=",
            "max_tokens=",
            "context_window=",
            "safety_margin=",
            "connect_timeout=",
            "read_timeout=",
            "retry_reason=",
            "search_duration_seconds=",
            "prompt_build_duration_seconds=",
            "http_duration_seconds=",
            "first_token_seconds=",
            "total_duration_seconds=",
            "status_http=",
        ):
            self.assertIn(marker, success_logs)

        failure_client = FakeAIClient([error(LLMErrorCode.READ_TIMEOUT), error(LLMErrorCode.READ_TIMEOUT)])
        with patch("app.services.rag_service.time.sleep"):
            self._service(failure_client).answer_question("Question")
        failure_logs = "\n".join(failure_client.events)
        for marker in ("event=request_error", "code=read_timeout", "runtime_alive=", "models_available=", "health_available="):
            self.assertIn(marker, failure_logs)


if __name__ == "__main__":
    unittest.main()
