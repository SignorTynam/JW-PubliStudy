from __future__ import annotations

import re

from app.models.document_chunk import DocumentChunk
from app.models.publication import Publication
from app.models.search_result import SearchResult
from app.services.index_repository import IndexRepository
from app.services.publication_repository import PublicationRepository


class SearchService:
    def __init__(
        self,
        publication_repository: PublicationRepository,
        index_repository: IndexRepository | None = None,
    ) -> None:
        self._publication_repository = publication_repository
        self._index_repository = index_repository or IndexRepository(publication_repository.paths)

    def search(
        self,
        query: str,
        language: str = "all",
        publication_id: str = "all",
        limit: int = 30,
    ) -> list[SearchResult]:
        phrase, terms = self._normalize_query(query)
        if not phrase and not terms:
            return []

        results: list[SearchResult] = []
        for publication in self._filtered_publications(language, publication_id):
            for chunk in self._index_repository.load_chunks(publication.id):
                result = self._score_chunk(chunk, publication, phrase, terms)
                if result is not None and result.score > 0:
                    results.append(result)

        results.sort(key=lambda result: result.score, reverse=True)
        return results[: max(limit, 0)]

    def list_searchable_publications(self) -> list[Publication]:
        return [
            publication
            for publication in self._publication_repository.list_publications()
            if publication.status == "indexed" and self._index_repository.has_chunks(publication.id)
        ]

    def has_indexed_content(self) -> bool:
        return bool(self.list_searchable_publications())

    def get_chunk(self, chunk_id: str) -> DocumentChunk | None:
        publication_id = chunk_id.split(":", 1)[0]
        if not publication_id:
            return None
        for chunk in self._index_repository.load_chunks(publication_id):
            if chunk.id == chunk_id:
                return chunk
        return None

    def _filtered_publications(self, language: str, publication_id: str) -> list[Publication]:
        publications = self.list_searchable_publications()
        if language != "all":
            publications = [publication for publication in publications if publication.language == language]
        if publication_id != "all":
            publications = [publication for publication in publications if publication.id == publication_id]
        return publications

    def _score_chunk(
        self,
        chunk: DocumentChunk,
        publication: Publication,
        phrase: str,
        terms: list[str],
    ) -> SearchResult | None:
        searchable_text = self._normalize_text(chunk.text)
        searchable_title = self._normalize_text(publication.title)
        score = 0.0
        phrase_count = searchable_text.count(phrase) if phrase else 0
        if phrase_count:
            score += phrase_count * 5

        matched_terms: list[str] = []
        for term in terms:
            term_count = self._count_term(searchable_text, term)
            if term_count:
                score += term_count * 2
                matched_terms.append(term)
                if self._count_term(searchable_title, term):
                    score += 1

        if len(set(matched_terms)) > 1:
            score += 1

        if score <= 0:
            return None

        length_penalty = max(len(searchable_text) / 1200, 1.0)
        normalized_score = score / length_penalty
        return SearchResult(
            chunk_id=chunk.id,
            publication_id=chunk.publication_id,
            publication_title=chunk.publication_title or publication.title,
            language=chunk.language or publication.language,
            source_filename=chunk.source_filename or publication.original_filename,
            chunk_index=chunk.chunk_index,
            text=chunk.text,
            snippet=self._build_snippet(chunk.text, phrase, matched_terms),
            score=round(normalized_score, 3),
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            matched_terms=matched_terms,
        )

    def _normalize_query(self, query: str) -> tuple[str, list[str]]:
        phrase = self._normalize_text(query)
        raw_terms = re.split(r"\W+", phrase, flags=re.UNICODE)
        terms: list[str] = []
        for term in raw_terms:
            if len(term) < 2 or term in terms:
                continue
            terms.append(term)
        if not terms:
            return "", []
        return phrase, terms

    def _normalize_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", text.lower()).strip()

    def _count_term(self, text: str, term: str) -> int:
        return len(re.findall(rf"(?<!\w){re.escape(term)}(?!\w)", text))

    def _build_snippet(self, text: str, phrase: str, matched_terms: list[str]) -> str:
        flattened = re.sub(r"\s+", " ", text).strip()
        searchable = flattened.lower()
        match_index = searchable.find(phrase) if phrase else -1
        if match_index < 0:
            for term in matched_terms:
                match_index = searchable.find(term)
                if match_index >= 0:
                    break
        if match_index < 0:
            match_index = 0

        target_length = 320
        start = max(match_index - 110, 0)
        end = min(start + target_length, len(flattened))
        if end - start < target_length:
            start = max(end - target_length, 0)
        snippet = flattened[start:end].strip()
        if start > 0:
            snippet = f"...{snippet}"
        if end < len(flattened):
            snippet = f"{snippet}..."
        return snippet
