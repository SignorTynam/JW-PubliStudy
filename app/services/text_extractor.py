from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ExtractedPage:
    page_number: int | None
    text: str


@dataclass(frozen=True)
class ExtractedDocument:
    pages: list[ExtractedPage]
    full_text: str


class TextExtractionError(Exception):
    """Base exception for text extraction failures."""


class UnsupportedExtractionTypeError(TextExtractionError):
    """Raised when a file type cannot be extracted."""


class EmptyExtractedTextError(TextExtractionError):
    """Raised when extraction returns no useful text."""


class TextExtractor:
    TEXT_ENCODINGS = ("utf-8", "utf-8-sig", "cp1252", "latin-1")

    def extract(self, file_path: Path, file_type: str) -> ExtractedDocument:
        path = Path(file_path)
        if not path.is_file():
            raise TextExtractionError("missing_file")

        normalized_type = file_type.lower()
        if normalized_type == "txt":
            return self._extract_txt(path)
        if normalized_type == "pdf":
            return self._extract_pdf(path)
        raise UnsupportedExtractionTypeError("unsupported_type")

    def _extract_txt(self, path: Path) -> ExtractedDocument:
        last_error: Exception | None = None
        for encoding in self.TEXT_ENCODINGS:
            try:
                text = path.read_text(encoding=encoding)
            except UnicodeDecodeError as exc:
                last_error = exc
                continue
            except OSError as exc:
                raise TextExtractionError("unreadable_file") from exc

            if not text.strip():
                raise EmptyExtractedTextError("empty_text")
            return ExtractedDocument(pages=[ExtractedPage(page_number=None, text=text)], full_text=text)

        raise TextExtractionError("txt_decode_failed") from last_error

    def _extract_pdf(self, path: Path) -> ExtractedDocument:
        try:
            from pypdf import PdfReader
            from pypdf.errors import PdfReadError
        except ImportError as exc:
            raise TextExtractionError("pypdf_missing") from exc

        try:
            reader = PdfReader(str(path))
        except (OSError, PdfReadError, Exception) as exc:
            raise TextExtractionError("pdf_read_failed") from exc

        pages: list[ExtractedPage] = []
        for index, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception:
                text = ""
            pages.append(ExtractedPage(page_number=index, text=text))

        useful_pages = [page for page in pages if page.text.strip()]
        if not useful_pages:
            raise EmptyExtractedTextError("no_extractable_text")

        full_text = "\n\n".join(page.text for page in useful_pages)
        return ExtractedDocument(pages=useful_pages, full_text=full_text)
