from __future__ import annotations

from dataclasses import dataclass

from app.models.chat_source import ChatSource
from app.services.local_llm_client import LLMClientError, LLMConfig, LocalLLMClient
from app.services.search_service import SearchService


@dataclass(frozen=True)
class RagAnswer:
    answer: str
    sources: list[ChatSource]
    used_context: bool
    error_message: str


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

    def __init__(self, search_service: SearchService, llm_client: LocalLLMClient) -> None:
        self._search_service = search_service
        self._llm_client = llm_client

    def answer_question(
        self,
        question: str,
        config: LLMConfig,
        language: str = "all",
        publication_id: str = "all",
        retrieval_limit: int = 6,
    ) -> RagAnswer:
        cleaned_question = question.strip()
        if not cleaned_question:
            return RagAnswer("", [], False, "empty_question")
        if not self._search_service.has_indexed_content():
            return RagAnswer("", [], False, "no_indexed_publications")

        results = self._search_service.search(
            query=cleaned_question,
            language=language,
            publication_id=publication_id,
            limit=retrieval_limit,
        )
        if not results:
            return RagAnswer("", [], False, "insufficient_sources")

        sources = [ChatSource.from_search_result(result, index) for index, result in enumerate(results, start=1)]
        try:
            answer = self._llm_client.chat(
                [
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": self._build_user_prompt(cleaned_question, sources)},
                ],
                config,
            )
        except LLMClientError:
            return RagAnswer("", sources, True, "llm_error")

        return RagAnswer(answer=answer, sources=sources, used_context=True, error_message="")

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
