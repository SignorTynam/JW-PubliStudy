import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.ai.adaptive_request_planner import (
    AdaptiveRequestPlanner,
    PerformanceProfile,
    PerformanceProfileStore,
    RequestEnvironment,
    TokenEstimator,
)
from app.models.chat_source import ChatSource
from app.services.local_llm_client import LLMErrorCode


def source(index: int, text: str, score: float = 10.0) -> ChatSource:
    return ChatSource(
        source_id=f"S{index}",
        chunk_id=f"publication:{index}",
        publication_id="publication",
        publication_title=f"Publication {index}",
        source_filename="publication.pdf",
        language="it",
        page_start=index,
        page_end=index,
        chunk_index=index,
        text=text,
        snippet=text[:120],
        score=score,
        original_text_length=len(text),
    )


class AdaptiveRequestPlannerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.planner = AdaptiveRequestPlanner()
        self.environment = RequestEnvironment("medium", "Medium", 4096, 900, 16.0, 8.0)
        self.system_prompt = "Use only the supplied sources and cite each claim."

    def test_token_estimator_is_conservative_and_centralized(self) -> None:
        estimator = TokenEstimator()
        self.assertGreaterEqual(estimator.estimate_text("word " * 100), 125)
        self.assertEqual(estimator.estimate_text(""), 0)

    def test_small_prompt_uses_two_or_three_sources(self) -> None:
        candidates = [source(index, f"faith hope source {index} " * 20, 10 - index) for index in range(1, 7)]
        plan = self.planner.plan(
            question="Che cos'e la speranza?",
            system_prompt=self.system_prompt,
            candidates=candidates,
            environment=self.environment,
        )
        self.assertTrue(plan.valid)
        self.assertGreaterEqual(len(plan.selected_sources), 2)
        self.assertLessEqual(len(plan.selected_sources), 3)

    def test_large_prompt_never_exceeds_context_budget(self) -> None:
        candidates = [source(index, f"term relevant paragraph {index} " * 180, 20 - index) for index in range(1, 10)]
        plan = self.planner.plan(
            question="Confronta in modo articolato i temi principali e spiega le relazioni tra tutti i passaggi citati.",
            system_prompt=self.system_prompt * 4,
            candidates=candidates,
            environment=self.environment,
        )
        self.assertTrue(plan.valid)
        self.assertLessEqual(plan.total_budgeted_tokens, plan.context_window)
        self.assertGreaterEqual(plan.safety_margin_tokens, int(plan.context_window * 0.14))

    def test_retry_uses_fewer_sources_and_lower_max_tokens(self) -> None:
        candidates = [source(index, f"topic details unique{index} " * 80, 20 - index) for index in range(1, 9)]
        first = self.planner.plan(
            question="Spiega ampiamente il tema, confronta i dettagli e riassumi tutte le implicazioni disponibili nelle fonti.",
            system_prompt=self.system_prompt,
            candidates=candidates,
            environment=self.environment,
        )
        retry = self.planner.plan(
            question="Spiega ampiamente il tema, confronta i dettagli e riassumi tutte le implicazioni disponibili nelle fonti.",
            system_prompt=self.system_prompt,
            candidates=candidates,
            environment=self.environment,
            attempt_number=2,
            previous_error=LLMErrorCode.READ_TIMEOUT,
        )
        self.assertLess(len(retry.selected_sources), len(first.selected_sources))
        self.assertLess(retry.max_tokens, first.max_tokens)
        self.assertLess(retry.source_tokens, first.source_tokens)
        self.assertGreater(retry.read_timeout_seconds, 45)

    def test_long_chunk_is_reduced_around_question_terms(self) -> None:
        text = ("unrelated " * 1500) + "importantkeyword target sentence " + ("tail " * 1500)
        plan = self.planner.plan(
            question="Cosa dice importantkeyword?",
            system_prompt=self.system_prompt,
            candidates=[source(1, text)],
            environment=RequestEnvironment("small", "Small", 2048, 600, 8.0, 3.0),
        )
        self.assertTrue(plan.valid)
        fitted = plan.selected_sources[0]
        self.assertTrue(fitted.reduced)
        self.assertIn("importantkeyword", fitted.text)
        self.assertLess(len(fitted.text), len(text))
        self.assertEqual(fitted.original_text_length, len(text))

    def test_near_duplicate_sources_are_removed(self) -> None:
        repeated = "same relevant words about a subject " * 30
        candidates = [source(1, repeated, 10), source(2, repeated + " extra", 9), source(3, "different relevant evidence " * 20, 8)]
        plan = self.planner.plan(
            question="Quali sono le prove rilevanti?",
            system_prompt=self.system_prompt,
            candidates=candidates,
            environment=self.environment,
        )
        self.assertLess(plan.deduplicated_count, len(candidates))
        chunk_ids = {item.chunk_id for item in plan.selected_sources}
        self.assertFalse({"publication:1", "publication:2"}.issubset(chunk_ids))

    def test_max_tokens_adapts_to_question_complexity(self) -> None:
        candidates = [source(1, "relevant evidence " * 60)]
        short = self.planner.plan(
            question="Perche?",
            system_prompt=self.system_prompt,
            candidates=candidates,
            environment=self.environment,
        )
        long = self.planner.plan(
            question="Analizza, confronta e sintetizza in modo approfondito tutti gli argomenti, le differenze e le conseguenze presenti nelle pubblicazioni indicate, includendo una spiegazione articolata.",
            system_prompt=self.system_prompt,
            candidates=candidates,
            environment=self.environment,
        )
        self.assertGreater(long.max_tokens, short.max_tokens)

    def test_low_available_ram_reduces_output_budget(self) -> None:
        candidates = [source(1, "relevant evidence " * 60)]
        normal = self.planner.plan(
            question="Spiega questo argomento in modo chiaro.",
            system_prompt=self.system_prompt,
            candidates=candidates,
            environment=self.environment,
        )
        low_memory = self.planner.plan(
            question="Spiega questo argomento in modo chiaro.",
            system_prompt=self.system_prompt,
            candidates=candidates,
            environment=RequestEnvironment("medium", "Medium", 4096, 900, 16.0, 2.0),
        )
        self.assertLess(low_memory.max_tokens, normal.max_tokens)

    def test_very_long_question_is_rejected_before_context_overflow(self) -> None:
        plan = self.planner.plan(
            question="domanda " * 10000,
            system_prompt=self.system_prompt,
            candidates=[source(1, "evidence")],
            environment=RequestEnvironment("small", "Small", 2048, 600, 8.0, 4.0),
        )
        self.assertFalse(plan.valid)
        self.assertEqual(plan.error_code, LLMErrorCode.CONTEXT_OVERFLOW)
        self.assertGreater(plan.total_budgeted_tokens, plan.context_window)

    def test_no_sources_is_not_a_valid_plan(self) -> None:
        plan = self.planner.plan(
            question="Question",
            system_prompt=self.system_prompt,
            candidates=[],
            environment=self.environment,
        )
        self.assertFalse(plan.valid)
        self.assertEqual(plan.selected_sources, [])

    def test_slow_profile_increases_timeout_and_reduces_output(self) -> None:
        candidates = [source(1, "evidence " * 100)]
        fast = self.planner.plan(
            question="Spiega il tema.",
            system_prompt=self.system_prompt,
            candidates=candidates,
            environment=self.environment,
            profile=PerformanceProfile(5, 0, 2.0, 20.0, 10.0, 500, 300),
        )
        slow = self.planner.plan(
            question="Spiega il tema.",
            system_prompt=self.system_prompt,
            candidates=candidates,
            environment=self.environment,
            profile=PerformanceProfile(5, 2, 20.0, 2.0, 100.0, 1000, 300),
        )
        self.assertGreater(slow.read_timeout_seconds, fast.read_timeout_seconds)
        self.assertLess(slow.max_tokens, fast.max_tokens)

    def test_performance_profile_persists_only_technical_metrics(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"
            store = PerformanceProfileStore(path)
            store.record_success("medium", first_token_seconds=2.0, output_tokens=100, duration_seconds=12.0, prompt_tokens=800)
            store.record_timeout("medium")
            loaded = PerformanceProfileStore(path).get("medium")
            self.assertEqual(loaded.successful_requests, 1)
            self.assertEqual(loaded.timeout_count, 1)
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("question", text.lower())
            self.assertNotIn("source", text.lower())


if __name__ == "__main__":
    unittest.main()
