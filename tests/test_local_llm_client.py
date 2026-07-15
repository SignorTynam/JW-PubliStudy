import json
import threading
import unittest
from unittest.mock import patch

import requests

from app.services.local_llm_client import (
    LLMClientError,
    LLMConfig,
    LLMErrorCode,
    LocalLLMClient,
    parse_sse_data_line,
)


class FakeResponse:
    def __init__(self, status_code=200, data=None, text="", lines=None, json_error=None):
        self.status_code = status_code
        self._data = data
        self.text = text
        self._lines = lines or []
        self._json_error = json_error
        self.closed = False

    def json(self):
        if self._json_error is not None:
            raise self._json_error
        return self._data

    def iter_lines(self, decode_unicode=True):
        del decode_unicode
        return iter(self._lines)

    def close(self):
        self.closed = True


def config(*, stream=False) -> LLMConfig:
    return LLMConfig(
        "http://127.0.0.1:1234/v1/chat/completions",
        "model",
        0.2,
        300,
        120,
        connect_timeout_seconds=3,
        read_timeout_seconds=75,
        stream=stream,
    )


class LocalLLMClientTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = LocalLLMClient()
        self.messages = [{"role": "user", "content": "test"}]

    def test_uses_separate_connect_and_read_timeouts(self) -> None:
        response = FakeResponse(data={"choices": [{"message": {"content": "ok"}}]})
        with patch("requests.post", return_value=response) as post:
            self.client.chat(self.messages, config())
        self.assertEqual(post.call_args.kwargs["timeout"], (3.0, 75.0))

    def test_connection_timeout_is_structured(self) -> None:
        with patch("requests.post", side_effect=requests.ConnectTimeout("connect")):
            with self.assertRaises(LLMClientError) as captured:
                self.client.chat(self.messages, config())
        self.assertEqual(captured.exception.details.code, LLMErrorCode.CONNECTION_TIMEOUT)
        self.assertTrue(captured.exception.details.retryable)

    def test_read_timeout_is_structured(self) -> None:
        with patch("requests.post", side_effect=requests.ReadTimeout("read")):
            with self.assertRaises(LLMClientError) as captured:
                self.client.chat(self.messages, config())
        self.assertEqual(captured.exception.details.code, LLMErrorCode.READ_TIMEOUT)

    def test_connection_reset_is_structured(self) -> None:
        with patch("requests.post", side_effect=requests.ConnectionError("connection reset by peer")):
            with self.assertRaises(LLMClientError) as captured:
                self.client.chat(self.messages, config())
        self.assertEqual(captured.exception.details.code, LLMErrorCode.CONNECTION_RESET)

    def test_context_overflow_http_400(self) -> None:
        response = FakeResponse(400, text="prompt exceeds context window n_ctx")
        with patch("requests.post", return_value=response):
            with self.assertRaises(LLMClientError) as captured:
                self.client.chat(self.messages, config())
        self.assertEqual(captured.exception.details.code, LLMErrorCode.CONTEXT_OVERFLOW)
        self.assertEqual(captured.exception.details.status_http, 400)
        self.assertTrue(captured.exception.details.retryable)

    def test_http_500_and_503_are_retryable(self) -> None:
        for status, expected in ((500, LLMErrorCode.SERVER_ERROR), (503, LLMErrorCode.SERVER_BUSY)):
            with self.subTest(status=status), patch("requests.post", return_value=FakeResponse(status, text="busy")):
                with self.assertRaises(LLMClientError) as captured:
                    self.client.chat(self.messages, config())
                self.assertEqual(captured.exception.details.code, expected)
                self.assertTrue(captured.exception.details.retryable)

    def test_out_of_memory_body_is_classified(self) -> None:
        with patch("requests.post", return_value=FakeResponse(500, text="failed to allocate memory")):
            with self.assertRaises(LLMClientError) as captured:
                self.client.chat(self.messages, config())
        self.assertEqual(captured.exception.details.code, LLMErrorCode.OUT_OF_MEMORY)

    def test_invalid_json_missing_and_empty_content(self) -> None:
        cases = [
            (FakeResponse(data=None, json_error=ValueError("invalid")), LLMErrorCode.INVALID_JSON),
            (FakeResponse(data={"choices": []}), LLMErrorCode.MISSING_CONTENT),
            (FakeResponse(data={"choices": [{"message": {"content": "  "}}]}), LLMErrorCode.EMPTY_CONTENT),
        ]
        for response, expected in cases:
            with self.subTest(expected=expected), patch("requests.post", return_value=response):
                with self.assertRaises(LLMClientError) as captured:
                    self.client.chat(self.messages, config())
                self.assertEqual(captured.exception.details.code, expected)

    def test_streaming_sse_emits_progressive_tokens_and_done(self) -> None:
        lines = [
            'data: {"choices":[{"delta":{"content":"Hel"}}]}',
            'data: {"choices":[{"delta":{"content":"lo"}}]}',
            "data: [DONE]",
        ]
        response = FakeResponse(lines=lines)
        tokens = []
        with patch("requests.post", return_value=response):
            result = self.client.chat_detailed(self.messages, config(stream=True), on_token=tokens.append)
        self.assertEqual(result.content, "Hello")
        self.assertEqual(tokens, ["Hel", "lo"])
        self.assertIsNotNone(result.first_token_seconds)
        self.assertTrue(response.closed)

    def test_stream_connection_interruption_is_structured(self) -> None:
        response = FakeResponse()

        def broken_stream(decode_unicode=True):
            del decode_unicode
            yield 'data: {"choices":[{"delta":{"content":"partial"}}]}'
            raise requests.ConnectionError("reset")

        response.iter_lines = broken_stream
        with patch("requests.post", return_value=response):
            with self.assertRaises(LLMClientError) as captured:
                self.client.chat_detailed(self.messages, config(stream=True))
        self.assertEqual(captured.exception.details.code, LLMErrorCode.CONNECTION_RESET)

    def test_cancellation_before_request_prevents_network_call(self) -> None:
        event = threading.Event()
        event.set()
        with patch("requests.post") as post:
            with self.assertRaises(LLMClientError) as captured:
                self.client.chat_detailed(self.messages, config(stream=True), cancellation_event=event)
        self.assertEqual(captured.exception.details.code, LLMErrorCode.CANCELLED)
        post.assert_not_called()

    def test_cancellation_during_stream_stops_before_done(self) -> None:
        event = threading.Event()
        response = FakeResponse(
            lines=[
                'data: {"choices":[{"delta":{"content":"partial"}}]}',
                'data: {"choices":[{"delta":{"content":" ignored"}}]}',
                "data: [DONE]",
            ]
        )
        tokens = []

        def cancel_after_first_token(token):
            tokens.append(token)
            event.set()

        with patch("requests.post", return_value=response):
            with self.assertRaises(LLMClientError) as captured:
                self.client.chat_detailed(
                    self.messages,
                    config(stream=True),
                    cancellation_event=event,
                    on_token=cancel_after_first_token,
                )

        self.assertEqual(captured.exception.details.code, LLMErrorCode.CANCELLED)
        self.assertEqual(tokens, ["partial"])
        self.assertTrue(response.closed)

    def test_health_check_prefers_models_and_accepts_temporary_health_failure(self) -> None:
        responses = [FakeResponse(200), FakeResponse(503)]
        with patch("requests.get", side_effect=responses) as get:
            result = self.client.health_check(config().endpoint_url)
        self.assertTrue(result.runtime_alive)
        self.assertTrue(result.models_available)
        self.assertFalse(result.health_available)
        self.assertTrue(get.call_args_list[0].args[0].endswith("/v1/models"))

    def test_sse_parser_ignores_comments_and_parses_data(self) -> None:
        self.assertIsNone(parse_sse_data_line(": keep-alive"))
        self.assertIsNone(parse_sse_data_line(""))
        self.assertEqual(parse_sse_data_line("data: [DONE]"), "[DONE]")
        payload = json.dumps({"choices": []})
        self.assertEqual(parse_sse_data_line(payload), payload)


if __name__ == "__main__":
    unittest.main()
