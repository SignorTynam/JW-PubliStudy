from __future__ import annotations

import re
from dataclasses import dataclass

from app.models.document_chunk import DocumentChunk
from app.models.publication import Publication
from app.services.text_extractor import ExtractedDocument


@dataclass(frozen=True)
class PageSpan:
    page_number: int | None
    char_start: int
    char_end: int


class TextChunker:
    def __init__(
        self,
        target_chunk_size: int = 1200,
        overlap_size: int = 150,
        min_chunk_size: int = 200,
    ) -> None:
        self._target_chunk_size = target_chunk_size
        self._overlap_size = overlap_size
        self._min_chunk_size = min_chunk_size

    def clean_text(self, text: str) -> str:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        cleaned_lines: list[str] = []
        previous_blank = False

        for raw_line in normalized.split("\n"):
            line = re.sub(r"[ \t]+", " ", raw_line).strip()
            if not line:
                if not previous_blank and cleaned_lines:
                    cleaned_lines.append("")
                previous_blank = True
                continue
            cleaned_lines.append(line)
            previous_blank = False

        return "\n".join(cleaned_lines).strip()

    def create_chunks(self, publication: Publication, document: ExtractedDocument) -> list[DocumentChunk]:
        full_text, page_spans = self._clean_pages(document)
        if not full_text:
            return []

        chunks: list[DocumentChunk] = []
        start = 0
        text_length = len(full_text)

        while start < text_length:
            max_end = min(start + self._target_chunk_size, text_length)
            if text_length - max_end < self._min_chunk_size:
                end = text_length
            else:
                end = self._find_chunk_end(full_text, start, max_end)

            chunk_text = full_text[start:end].strip()
            if chunk_text:
                page_start, page_end = self._pages_for_span(page_spans, start, end)
                chunk_index = len(chunks)
                chunks.append(
                    DocumentChunk(
                        id=f"{publication.id}:{chunk_index}",
                        publication_id=publication.id,
                        publication_title=publication.title,
                        language=publication.language,
                        source_filename=publication.original_filename,
                        chunk_index=chunk_index,
                        text=chunk_text,
                        page_start=page_start,
                        page_end=page_end,
                        char_start=start,
                        char_end=end,
                    )
                )

            if end >= text_length:
                break
            next_start = max(end - self._overlap_size, start + 1)
            start = self._skip_leading_whitespace(full_text, next_start)

        return chunks

    def _clean_pages(self, document: ExtractedDocument) -> tuple[str, list[PageSpan]]:
        parts: list[str] = []
        page_spans: list[PageSpan] = []
        cursor = 0

        for page in document.pages:
            text = self.clean_text(page.text)
            if not text:
                continue
            if parts:
                parts.append("\n\n")
                cursor += 2

            start = cursor
            parts.append(text)
            cursor += len(text)
            page_spans.append(PageSpan(page_number=page.page_number, char_start=start, char_end=cursor))

        return "".join(parts), page_spans

    def _find_chunk_end(self, text: str, start: int, max_end: int) -> int:
        min_end = min(start + self._min_chunk_size, max_end)
        window = text[min_end:max_end]

        paragraph_break = window.rfind("\n\n")
        if paragraph_break >= 0:
            return min_end + paragraph_break + 2

        sentence_breaks = [window.rfind(marker) for marker in (". ", "! ", "? ", ".\n", "!\n", "?\n")]
        sentence_break = max(sentence_breaks)
        if sentence_break >= 0:
            return min_end + sentence_break + 1

        space_break = window.rfind(" ")
        if space_break >= 0:
            return min_end + space_break

        return max_end

    def _pages_for_span(self, page_spans: list[PageSpan], start: int, end: int) -> tuple[int | None, int | None]:
        pages = [
            span.page_number
            for span in page_spans
            if span.page_number is not None and span.char_start < end and span.char_end > start
        ]
        if not pages:
            return None, None
        return min(pages), max(pages)

    def _skip_leading_whitespace(self, text: str, start: int) -> int:
        while start < len(text) and text[start].isspace():
            start += 1
        return start
