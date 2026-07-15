from __future__ import annotations

import json
import math
import re
import threading
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from app.models.chat_source import ChatSource
from app.services.local_llm_client import LLMErrorCode


class TokenEstimator:
    """Conservative tokenizer-free estimate suitable for multilingual GGUF prompts."""

    def estimate_text(self, text: str) -> int:
        if not text:
            return 0
        normalized = re.sub(r"\s+", " ", text).strip()
        character_estimate = math.ceil(len(normalized) / 3.2)
        word_estimate = math.ceil(len(normalized.split()) * 1.35)
        return max(1, character_estimate, word_estimate)

    def estimate_source(self, source: ChatSource) -> int:
        metadata = f"[{source.source_id}] {source.publication_title} {source.language} {source.format_reference()} Testo:"
        return self.estimate_text(metadata) + self.estimate_text(source.text) + 12


@dataclass(frozen=True)
class RequestEnvironment:
    model_id: str
    model_name: str
    context_window: int
    default_output_tokens: int
    total_ram_gb: float
    available_ram_gb: float
    first_request: bool = False


@dataclass(frozen=True)
class PerformanceProfile:
    successful_requests: int = 0
    timeout_count: int = 0
    average_first_token_seconds: float = 0.0
    average_tokens_per_second: float = 0.0
    average_duration_seconds: float = 0.0
    average_prompt_tokens: float = 0.0
    average_output_tokens: float = 0.0


@dataclass(frozen=True)
class AdaptiveRequestPlan:
    model_id: str
    model_name: str
    context_window: int
    selected_sources: list[ChatSource]
    candidate_count: int
    deduplicated_count: int
    system_prompt_tokens: int
    question_tokens: int
    formatting_tokens: int
    source_tokens: int
    estimated_prompt_tokens: int
    max_tokens: int
    safety_margin_tokens: int
    available_source_tokens: int
    connect_timeout_seconds: float
    read_timeout_seconds: float
    attempt_number: int
    valid: bool = True
    error_code: LLMErrorCode | None = None

    @property
    def total_budgeted_tokens(self) -> int:
        return self.estimated_prompt_tokens + self.max_tokens + self.safety_margin_tokens


class PerformanceProfileStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = Path(path) if path is not None else None
        self._lock = threading.Lock()
        self._profiles: dict[str, PerformanceProfile] = {}
        self._load()

    def get(self, model_id: str) -> PerformanceProfile:
        with self._lock:
            return self._profiles.get(model_id, PerformanceProfile())

    def record_success(
        self,
        model_id: str,
        *,
        first_token_seconds: float | None,
        output_tokens: int,
        duration_seconds: float,
        prompt_tokens: int,
    ) -> None:
        with self._lock:
            current = self._profiles.get(model_id, PerformanceProfile())
            count = current.successful_requests + 1
            tokens_per_second = output_tokens / max(duration_seconds - (first_token_seconds or 0.0), 0.1)
            updated = PerformanceProfile(
                successful_requests=count,
                timeout_count=current.timeout_count,
                average_first_token_seconds=_running_average(current.average_first_token_seconds, first_token_seconds or 0.0, count),
                average_tokens_per_second=_running_average(current.average_tokens_per_second, tokens_per_second, count),
                average_duration_seconds=_running_average(current.average_duration_seconds, duration_seconds, count),
                average_prompt_tokens=_running_average(current.average_prompt_tokens, float(prompt_tokens), count),
                average_output_tokens=_running_average(current.average_output_tokens, float(output_tokens), count),
            )
            self._profiles[model_id] = updated
            self._save_locked()

    def record_timeout(self, model_id: str) -> None:
        with self._lock:
            current = self._profiles.get(model_id, PerformanceProfile())
            self._profiles[model_id] = replace(current, timeout_count=current.timeout_count + 1)
            self._save_locked()

    def _load(self) -> None:
        if self._path is None or not self._path.is_file():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(data, dict):
            return
        for model_id, value in data.items():
            if not isinstance(model_id, str) or not isinstance(value, dict):
                continue
            try:
                self._profiles[model_id] = PerformanceProfile(**value)
            except TypeError:
                continue

    def _save_locked(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_suffix(self._path.suffix + ".tmp")
        try:
            temporary.write_text(
                json.dumps({key: asdict(value) for key, value in self._profiles.items()}, indent=2),
                encoding="utf-8",
            )
            temporary.replace(self._path)
        except OSError:
            temporary.unlink(missing_ok=True)


class AdaptiveRequestPlanner:
    SAFETY_RATIO = 0.15
    FORMATTING_TOKENS = 192
    MIN_OUTPUT_TOKENS = 160
    MAX_OUTPUT_TOKENS = 900

    def __init__(self, estimator: TokenEstimator | None = None) -> None:
        self._estimator = estimator or TokenEstimator()

    @property
    def estimator(self) -> TokenEstimator:
        return self._estimator

    def plan(
        self,
        *,
        question: str,
        system_prompt: str,
        candidates: list[ChatSource],
        environment: RequestEnvironment,
        profile: PerformanceProfile | None = None,
        attempt_number: int = 1,
        previous_error: LLMErrorCode | None = None,
    ) -> AdaptiveRequestPlan:
        profile = profile or PerformanceProfile()
        context_window = max(1024, int(environment.context_window))
        safety_margin = max(128, math.ceil(context_window * self.SAFETY_RATIO))
        system_tokens = self._estimator.estimate_text(system_prompt)
        question_tokens = self._estimator.estimate_text(question)
        max_tokens = self._choose_output_tokens(question, environment, profile, attempt_number, previous_error)
        fixed_tokens = system_tokens + question_tokens + self.FORMATTING_TOKENS + safety_margin + max_tokens
        available_source_tokens = context_window - fixed_tokens
        if available_source_tokens < 96:
            return AdaptiveRequestPlan(
                model_id=environment.model_id,
                model_name=environment.model_name,
                context_window=context_window,
                selected_sources=[],
                candidate_count=len(candidates),
                deduplicated_count=0,
                system_prompt_tokens=system_tokens,
                question_tokens=question_tokens,
                formatting_tokens=self.FORMATTING_TOKENS,
                source_tokens=0,
                estimated_prompt_tokens=system_tokens + question_tokens + self.FORMATTING_TOKENS,
                max_tokens=max_tokens,
                safety_margin_tokens=safety_margin,
                available_source_tokens=max(0, available_source_tokens),
                connect_timeout_seconds=3.0,
                read_timeout_seconds=60.0,
                attempt_number=attempt_number,
                valid=False,
                error_code=LLMErrorCode.CONTEXT_OVERFLOW,
            )

        source_factor = 1.0
        if attempt_number > 1:
            source_factor *= 0.58
        if previous_error in {LLMErrorCode.CONTEXT_OVERFLOW, LLMErrorCode.OUT_OF_MEMORY}:
            source_factor *= 0.72
        source_budget = max(96, int(available_source_tokens * source_factor))
        deduplicated = self._deduplicate(candidates)
        relevant = self._relevant_sources(deduplicated)
        planning_sources = relevant
        if attempt_number > 1 and len(planning_sources) > 1:
            planning_sources = planning_sources[: max(1, min(2, len(planning_sources) // 2))]
        selected, source_tokens = self._select_sources(question, planning_sources, source_budget)
        estimated_prompt = system_tokens + question_tokens + self.FORMATTING_TOKENS + source_tokens
        read_timeout = self._choose_read_timeout(
            environment,
            profile,
            estimated_prompt,
            max_tokens,
            attempt_number,
            previous_error,
        )
        return AdaptiveRequestPlan(
            model_id=environment.model_id,
            model_name=environment.model_name,
            context_window=context_window,
            selected_sources=selected,
            candidate_count=len(candidates),
            deduplicated_count=len(relevant),
            system_prompt_tokens=system_tokens,
            question_tokens=question_tokens,
            formatting_tokens=self.FORMATTING_TOKENS,
            source_tokens=source_tokens,
            estimated_prompt_tokens=estimated_prompt,
            max_tokens=max_tokens,
            safety_margin_tokens=safety_margin,
            available_source_tokens=source_budget,
            connect_timeout_seconds=3.0,
            read_timeout_seconds=read_timeout,
            attempt_number=attempt_number,
            valid=bool(selected),
            error_code=None if selected else LLMErrorCode.CONTEXT_OVERFLOW,
        )

    def _choose_output_tokens(
        self,
        question: str,
        environment: RequestEnvironment,
        profile: PerformanceProfile,
        attempt_number: int,
        previous_error: LLMErrorCode | None,
    ) -> int:
        word_count = len(question.split())
        if word_count <= 18 and len(question) <= 140:
            desired = 300
        elif word_count <= 60 and len(question) <= 500:
            desired = 480
        else:
            desired = 650
        desired = min(desired, max(self.MIN_OUTPUT_TOKENS, environment.default_output_tokens), self.MAX_OUTPUT_TOKENS)
        if environment.available_ram_gb > 0 and environment.total_ram_gb > 0:
            available_ratio = environment.available_ram_gb / environment.total_ram_gb
            if available_ratio < 0.20:
                desired = int(desired * 0.70)
            elif available_ratio < 0.35:
                desired = int(desired * 0.85)
        if profile.average_tokens_per_second and profile.average_tokens_per_second < 4.0:
            desired = int(desired * 0.75)
        if attempt_number > 1:
            desired = int(desired * 0.65)
        if previous_error in {LLMErrorCode.CONTEXT_OVERFLOW, LLMErrorCode.OUT_OF_MEMORY}:
            desired = int(desired * 0.75)
        return max(self.MIN_OUTPUT_TOKENS, min(self.MAX_OUTPUT_TOKENS, desired))

    def _choose_read_timeout(
        self,
        environment: RequestEnvironment,
        profile: PerformanceProfile,
        prompt_tokens: int,
        max_tokens: int,
        attempt_number: int,
        previous_error: LLMErrorCode | None,
    ) -> float:
        if profile.average_tokens_per_second > 0:
            tokens_per_second = max(1.5, profile.average_tokens_per_second * 0.70)
            first_token = max(5.0, profile.average_first_token_seconds * 1.8)
        else:
            tokens_per_second = 5.0 if environment.total_ram_gb < 12 else 8.0 if environment.total_ram_gb < 24 else 12.0
            first_token = 30.0 if environment.first_request else 18.0
        predicted = first_token + (prompt_tokens / max(tokens_per_second * 4.0, 1.0)) + (max_tokens / tokens_per_second * 1.6)
        if environment.first_request:
            predicted *= 1.20
        if attempt_number > 1 and previous_error in {LLMErrorCode.READ_TIMEOUT, LLMErrorCode.CONNECTION_TIMEOUT}:
            predicted *= 1.25
        predicted += min(profile.timeout_count * 15.0, 45.0)
        return round(max(45.0, min(480.0, predicted)), 1)

    def _deduplicate(self, candidates: list[ChatSource]) -> list[ChatSource]:
        unique: list[ChatSource] = []
        signatures: list[set[str]] = []
        seen_chunk_ids: set[str] = set()
        for source in sorted(candidates, key=lambda item: item.score, reverse=True):
            if source.chunk_id in seen_chunk_ids:
                continue
            signature = set(re.findall(r"\w+", source.text.lower()))
            duplicate = False
            for existing in signatures:
                union = signature | existing
                if union and len(signature & existing) / len(union) >= 0.82:
                    duplicate = True
                    break
            if duplicate:
                continue
            seen_chunk_ids.add(source.chunk_id)
            signatures.append(signature)
            unique.append(source)
        return unique

    def _relevant_sources(self, candidates: list[ChatSource]) -> list[ChatSource]:
        if not candidates:
            return []
        threshold = max(0.05, candidates[0].score * 0.12)
        return [source for source in candidates if source.score >= threshold]

    def _select_sources(self, question: str, candidates: list[ChatSource], budget: int) -> tuple[list[ChatSource], int]:
        if not candidates:
            return [], 0
        word_count = len(question.split())
        max_sources = 3 if word_count <= 15 else 6 if word_count <= 50 else 8
        question_terms = [term for term in re.findall(r"\w+", question.lower()) if len(term) >= 3]
        selected: list[ChatSource] = []
        used_tokens = 0
        target_per_source = max(120, min(1000, budget // max(1, min(max_sources, len(candidates)))))
        for candidate in candidates[:max_sources]:
            remaining = budget - used_tokens
            if remaining < 80:
                break
            fitted = self._fit_source(candidate, question_terms, min(remaining, target_per_source))
            fitted = replace(fitted, source_id=f"S{len(selected) + 1}")
            tokens = self._estimator.estimate_source(fitted)
            if tokens > remaining:
                continue
            selected.append(fitted)
            used_tokens += tokens
        return selected, used_tokens

    def _fit_source(self, source: ChatSource, question_terms: list[str], token_budget: int) -> ChatSource:
        if self._estimator.estimate_source(source) <= token_budget:
            return source
        max_characters = max(320, int(token_budget * 2.7))
        flattened = re.sub(r"\s+", " ", source.text).strip()
        lowered = flattened.lower()
        match_index = -1
        for term in question_terms:
            match_index = lowered.find(term)
            if match_index >= 0:
                break
        if match_index < 0:
            match_index = 0
        start = max(0, match_index - max_characters // 3)
        end = min(len(flattened), start + max_characters)
        if end - start < max_characters:
            start = max(0, end - max_characters)
        window = flattened[start:end].strip()
        if start > 0:
            window = "..." + window
        if end < len(flattened):
            window += "..."
        return replace(
            source,
            text=window,
            snippet=window[:320],
            reduced=True,
            original_text_length=source.original_text_length or len(source.text),
        )


def _running_average(previous: float, value: float, count: int) -> float:
    if count <= 1:
        return round(value, 4)
    return round(previous + (value - previous) / count, 4)
