from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Callable
from uuid import uuid4

from app.ai.adaptive_request_planner import (
    AdaptiveRequestPlan,
    AdaptiveRequestPlanner,
    PerformanceProfileStore,
    RequestEnvironment,
)
from app.models.chat_source import ChatSource
from app.services.local_llm_client import (
    LLMChatResult,
    LLMClientError,
    LLMConfig,
    LLMErrorCode,
    LLMErrorDetails,
    LLMHealthResult,
)
from app.services.search_service import SearchService


class RagRequestState(str, Enum):
    IDLE = "idle"
    PREPARING_SOURCES = "preparing_sources"
    BUILDING_PROMPT = "building_prompt"
    SENDING_REQUEST = "sending_request"
    WAITING_FIRST_TOKEN = "waiting_first_token"
    GENERATING = "generating"
    RETRYING = "retrying"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(frozen=True)
class RagAnswer:
    answer: str
    sources: list[ChatSource]
    used_context: bool
    error_message: str
    error: LLMErrorDetails | None = None
    request_id: str = ""
    plan: AdaptiveRequestPlan | None = None


class RagService:
    SYSTEM_PROMPT = (
        "Sei l'assistente di studio locale di JW PubliStudy.\n"
        "Devi rispondere usando esclusivamente le fonti fornite nel contesto.\n"
        "Non usare conoscenze esterne.\n"
        "Non aggiungere informazioni non presenti nelle fonti.\n"
        "Se le fonti non bastano, dillo chiaramente.\n"
        "Ogni affermazione importante deve avere una citazione nel formato [S1], [S2], ecc.\n"
        "Rispondi nella stessa lingua della domanda, se possibile.\n"
        "Mantieni un tono rispettoso, chiaro e utile.\n"
        "Non presentarti come autorita religiosa.\n"
        "Non sostituire lo studio personale dell'utente."
    )
    CANDIDATE_LIMIT = 12
    MAX_ATTEMPTS = 2

    def __init__(
        self,
        search_service: SearchService,
        llm_client,
        planner: AdaptiveRequestPlanner | None = None,
        performance_store: PerformanceProfileStore | None = None,
        profile_path: Path | None = None,
    ) -> None:
        self._search_service = search_service
        self._llm_client = llm_client
        self._planner = planner or AdaptiveRequestPlanner()
        self._performance_store = performance_store or PerformanceProfileStore(profile_path)

    def answer_question(
        self,
        question: str,
        config: LLMConfig | None = None,
        language: str = "all",
        publication_id: str = "all",
        retrieval_limit: int | None = None,
        *,
        cancellation_event: threading.Event | None = None,
        phase_callback: Callable[[str], None] | None = None,
        progress_callback: Callable[[int], None] | None = None,
        retry_callback: Callable[[int, str], None] | None = None,
        token_callback: Callable[[str], None] | None = None,
        request_id: str | None = None,
    ) -> RagAnswer:
        candidate_limit = self.CANDIDATE_LIMIT if retrieval_limit is None else max(1, min(self.CANDIDATE_LIMIT, int(retrieval_limit)))
        request_id = request_id or uuid4().hex
        started = time.monotonic()
        cleaned_question = question.strip()
        question_hash = hashlib.sha256(cleaned_question.encode("utf-8")).hexdigest()[:12] if cleaned_question else "empty"
        self._record(
            f"request_id={request_id} event=start question_length={len(cleaned_question)} question_hash={question_hash} "
            f"runtime_state={self._runtime_state_label()}"
        )
        if not cleaned_question:
            return RagAnswer("", [], False, "empty_question", request_id=request_id)
        if self._cancelled(cancellation_event):
            return self._cancelled_answer(request_id, started)

        self._phase(RagRequestState.PREPARING_SOURCES, phase_callback, progress_callback, 10)
        search_started = time.monotonic()
        if not self._search_service.has_indexed_content():
            self._record(f"request_id={request_id} event=no_indexed_publications")
            return RagAnswer("", [], False, "no_indexed_publications", request_id=request_id)
        results = self._search_service.search(
            query=cleaned_question,
            language=language,
            publication_id=publication_id,
            limit=candidate_limit,
        )
        search_duration = time.monotonic() - search_started
        candidates = [ChatSource.from_search_result(result, index) for index, result in enumerate(results, start=1)]
        self._record(
            f"request_id={request_id} event=sources_retrieved candidates={len(candidates)} "
            f"search_duration_seconds={search_duration:.3f}"
        )
        if not candidates:
            return RagAnswer("", [], False, "insufficient_sources", request_id=request_id)
        if self._cancelled(cancellation_event):
            return self._cancelled_answer(request_id, started)

        environment = self._request_environment(config)
        profile = self._performance_store.get(environment.model_id)
        environment = replace(environment, first_request=profile.successful_requests == 0)
        previous_error: LLMErrorCode | None = None
        restarted_runtime = False
        last_plan: AdaptiveRequestPlan | None = None
        last_sources: list[ChatSource] = []
        last_error: LLMErrorDetails | None = None

        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            if self._cancelled(cancellation_event):
                return self._cancelled_answer(request_id, started, last_plan, last_sources)
            if attempt > 1:
                self._phase(RagRequestState.RETRYING, phase_callback, progress_callback, 45)
            plan = self._planner.plan(
                question=cleaned_question,
                system_prompt=self.SYSTEM_PROMPT,
                candidates=candidates,
                environment=environment,
                profile=profile,
                attempt_number=attempt,
                previous_error=previous_error,
            )
            last_plan = plan
            last_sources = plan.selected_sources
            self._record_plan(request_id, plan, previous_error)
            if not plan.valid:
                last_error = LLMErrorDetails(
                    plan.error_code or LLMErrorCode.CONTEXT_OVERFLOW,
                    "adaptive_planner_no_safe_prompt",
                    retryable=attempt < self.MAX_ATTEMPTS,
                    attempt_number=attempt,
                    elapsed_seconds=time.monotonic() - started,
                )
                if attempt < self.MAX_ATTEMPTS:
                    previous_error = last_error.code
                    if retry_callback is not None:
                        retry_callback(attempt + 1, last_error.code.value)
                    continue
                break

            self._phase(RagRequestState.BUILDING_PROMPT, phase_callback, progress_callback, 30)
            prompt_started = time.monotonic()
            user_prompt = self._build_user_prompt(cleaned_question, plan.selected_sources)
            prompt_duration = time.monotonic() - prompt_started
            self._record(
                f"request_id={request_id} event=prompt_built attempt={attempt} "
                f"prompt_build_duration_seconds={prompt_duration:.3f}"
            )
            http_started = time.monotonic()
            saw_first_token = False

            def forward_token(token: str) -> None:
                nonlocal saw_first_token
                if not saw_first_token:
                    saw_first_token = True
                    self._phase(RagRequestState.GENERATING, phase_callback, progress_callback, 75)
                if token_callback is not None:
                    token_callback(token)

            try:
                request_config = self._request_config(config, plan)
                self._phase(RagRequestState.SENDING_REQUEST, phase_callback, progress_callback, 55)
                self._phase(RagRequestState.WAITING_FIRST_TOKEN, phase_callback, progress_callback, 60)
                result = self._chat(
                    [
                        {"role": "system", "content": self.SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    request_config,
                    cancellation_event,
                    forward_token,
                    attempt,
                )
            except LLMClientError as exc:
                http_duration = time.monotonic() - http_started
                details = replace(
                    exc.details,
                    attempt_number=attempt,
                    elapsed_seconds=max(exc.details.elapsed_seconds, http_duration),
                )
                if details.code == LLMErrorCode.CANCELLED or self._cancelled(cancellation_event):
                    return self._cancelled_answer(request_id, started, plan, plan.selected_sources)
                health = self._health_check()
                details = details.with_runtime_alive(health.runtime_alive)
                last_error = details
                previous_error = details.code
                if details.code in {LLMErrorCode.CONNECTION_TIMEOUT, LLMErrorCode.READ_TIMEOUT}:
                    self._performance_store.record_timeout(environment.model_id)
                self._record_error(request_id, details, health, http_duration)

                should_restart = (
                    details.code in {LLMErrorCode.CONNECTION_FAILED, LLMErrorCode.CONNECTION_RESET, LLMErrorCode.RUNTIME_STOPPED}
                    and not health.models_available
                    and not restarted_runtime
                    and hasattr(self._llm_client, "restart_runtime")
                )
                if attempt < self.MAX_ATTEMPTS and should_restart:
                    if cancellation_event is not None:
                        restarted_runtime = bool(self._llm_client.restart_runtime(cancellation_event=cancellation_event))
                    else:
                        restarted_runtime = bool(self._llm_client.restart_runtime())
                    self._record(f"request_id={request_id} event=runtime_restart success={restarted_runtime}")
                    if self._cancelled(cancellation_event):
                        return self._cancelled_answer(request_id, started, plan, plan.selected_sources)
                    if not restarted_runtime and not health.runtime_alive:
                        break

                if attempt >= self.MAX_ATTEMPTS or not details.retryable:
                    break
                if retry_callback is not None:
                    retry_callback(attempt + 1, details.code.value)
                if cancellation_event is not None:
                    if cancellation_event.wait(0.5):
                        return self._cancelled_answer(request_id, started, plan, plan.selected_sources)
                else:
                    time.sleep(0.5)
                continue
            except Exception as exc:  # Defensive boundary: no worker exception may escape into Qt.
                last_error = LLMErrorDetails(
                    LLMErrorCode.UNKNOWN_ERROR,
                    f"{type(exc).__name__}: {exc}",
                    retryable=False,
                    attempt_number=attempt,
                    elapsed_seconds=time.monotonic() - started,
                )
                self._record(f"request_id={request_id} event=unexpected_error type={type(exc).__name__}")
                break

            http_duration = time.monotonic() - http_started
            self._performance_store.record_success(
                environment.model_id,
                first_token_seconds=result.first_token_seconds,
                output_tokens=result.output_tokens_estimated,
                duration_seconds=result.elapsed_seconds,
                prompt_tokens=plan.estimated_prompt_tokens,
            )
            total_duration = time.monotonic() - started
            self._record(
                f"request_id={request_id} event=completed attempt={attempt} sources={len(plan.selected_sources)} "
                f"http_duration_seconds={http_duration:.3f} first_token_seconds={result.first_token_seconds} "
                f"total_duration_seconds={total_duration:.3f} status_http={result.status_http}"
            )
            self._phase(RagRequestState.COMPLETED, phase_callback, progress_callback, 100)
            return RagAnswer(
                answer=result.content,
                sources=plan.selected_sources,
                used_context=True,
                error_message="",
                request_id=request_id,
                plan=plan,
            )

        error = last_error or LLMErrorDetails(
            LLMErrorCode.UNKNOWN_ERROR,
            "request_failed_without_details",
            attempt_number=self.MAX_ATTEMPTS,
            elapsed_seconds=time.monotonic() - started,
        )
        self._phase(RagRequestState.FAILED, phase_callback, progress_callback, 100)
        self._record(
            f"request_id={request_id} event=failed code={error.code.value} attempt={error.attempt_number} "
            f"runtime_alive={error.runtime_alive} total_duration_seconds={time.monotonic() - started:.3f}"
        )
        return RagAnswer(
            "",
            last_sources,
            bool(last_sources),
            error.code.value,
            error=error,
            request_id=request_id,
            plan=last_plan,
        )

    def cancel_active_request(self) -> None:
        if hasattr(self._llm_client, "cancel_active_request"):
            self._llm_client.cancel_active_request()

    def _chat(
        self,
        messages: list[dict[str, str]],
        config: LLMConfig,
        cancellation_event: threading.Event | None,
        token_callback: Callable[[str], None] | None,
        attempt_number: int,
    ) -> LLMChatResult:
        if hasattr(self._llm_client, "chat_detailed"):
            return self._llm_client.chat_detailed(
                messages,
                config,
                cancellation_event=cancellation_event,
                on_token=token_callback,
                attempt_number=attempt_number,
            )
        started = time.monotonic()
        content = self._llm_client.chat(messages, config)
        if token_callback is not None:
            token_callback(content)
        elapsed = time.monotonic() - started
        return LLMChatResult(content, elapsed, elapsed, max(1, len(content) // 4), 200)

    def _request_environment(self, config: LLMConfig | None) -> RequestEnvironment:
        if hasattr(self._llm_client, "request_environment"):
            return self._llm_client.request_environment()
        model_name = config.model if config is not None else "local-model"
        return RequestEnvironment("local", model_name, 4096, 600, 16.0, 8.0)

    def _request_config(self, fallback: LLMConfig | None, plan: AdaptiveRequestPlan) -> LLMConfig:
        if hasattr(self._llm_client, "build_request_config"):
            return self._llm_client.build_request_config(plan)
        if fallback is None:
            raise LLMClientError(LLMErrorDetails(LLMErrorCode.CONNECTION_FAILED, "missing_llm_config"))
        return replace(
            fallback,
            max_tokens=plan.max_tokens,
            timeout_seconds=int(plan.read_timeout_seconds),
            connect_timeout_seconds=plan.connect_timeout_seconds,
            read_timeout_seconds=plan.read_timeout_seconds,
        )

    def _health_check(self) -> LLMHealthResult:
        if hasattr(self._llm_client, "check_health"):
            return self._llm_client.check_health()
        return LLMHealthResult(True, True, False, models_status=200)

    def _runtime_state_label(self) -> str:
        if hasattr(self._llm_client, "status"):
            try:
                return str(self._llm_client.status())
            except Exception:
                return "unknown"
        return "unknown"

    def _record_plan(self, request_id: str, plan: AdaptiveRequestPlan, previous_error: LLMErrorCode | None) -> None:
        endpoint = "unavailable"
        if hasattr(self._llm_client, "get_active_endpoint"):
            try:
                endpoint = str(self._llm_client.get_active_endpoint() or "unavailable")
            except Exception:
                endpoint = "unavailable"
        self._record(
            f"request_id={request_id} event=plan attempt={plan.attempt_number} model={plan.model_name} endpoint={endpoint} "
            f"candidates={plan.candidate_count} sources_used={len(plan.selected_sources)} "
            f"prompt_tokens={plan.estimated_prompt_tokens} source_tokens={plan.source_tokens} "
            f"reserved_output_tokens={plan.max_tokens} max_tokens={plan.max_tokens} "
            f"context_window={plan.context_window} safety_margin={plan.safety_margin_tokens} "
            f"connect_timeout={plan.connect_timeout_seconds} read_timeout={plan.read_timeout_seconds} "
            f"retry_reason={previous_error.value if previous_error else 'none'}"
        )

    def _record_error(
        self,
        request_id: str,
        error: LLMErrorDetails,
        health: LLMHealthResult,
        http_duration: float,
    ) -> None:
        self._record(
            f"request_id={request_id} event=request_error attempt={error.attempt_number} code={error.code.value} "
            f"status_http={error.status_http} retryable={error.retryable} http_duration_seconds={http_duration:.3f} "
            f"runtime_alive={health.runtime_alive} models_available={health.models_available} "
            f"health_available={health.health_available} models_status={health.models_status} health_status={health.health_status}"
        )

    def _record(self, message: str) -> None:
        if hasattr(self._llm_client, "record_request_event"):
            self._llm_client.record_request_event(message)

    def _build_user_prompt(self, question: str, sources: list[ChatSource]) -> str:
        source_blocks = []
        for source in sources:
            source_blocks.append(
                "\n".join(
                    [
                        f"[{source.source_id}]",
                        f"Titolo: {source.publication_title}",
                        f"Lingua: {source.language}",
                        f"Pagina/blocco: {source.format_reference()}",
                        "Testo:",
                        source.text,
                    ]
                )
            )
        return "\n\n".join(
            [
                "DOMANDA:",
                question,
                "FONTI DISPONIBILI:",
                "\n\n".join(source_blocks),
                "ISTRUZIONI FINALI:",
                "- Rispondi solo con le fonti sopra.",
                "- Cita le fonti usando [S1], [S2].",
                "- Se le fonti non rispondono alla domanda, scrivi che non ci sono informazioni sufficienti nelle pubblicazioni indicizzate.",
            ]
        )

    def _phase(
        self,
        state: RagRequestState,
        phase_callback: Callable[[str], None] | None,
        progress_callback: Callable[[int], None] | None,
        progress: int,
    ) -> None:
        if phase_callback is not None:
            phase_callback(state.value)
        if progress_callback is not None:
            progress_callback(progress)

    def _cancelled(self, event: threading.Event | None) -> bool:
        return bool(event is not None and event.is_set())

    def _cancelled_answer(
        self,
        request_id: str,
        started: float,
        plan: AdaptiveRequestPlan | None = None,
        sources: list[ChatSource] | None = None,
    ) -> RagAnswer:
        error = LLMErrorDetails(
            LLMErrorCode.CANCELLED,
            "request_cancelled",
            retryable=False,
            elapsed_seconds=time.monotonic() - started,
        )
        self._record(f"request_id={request_id} event=cancelled total_duration_seconds={error.elapsed_seconds:.3f}")
        return RagAnswer("", sources or [], bool(sources), error.code.value, error=error, request_id=request_id, plan=plan)
