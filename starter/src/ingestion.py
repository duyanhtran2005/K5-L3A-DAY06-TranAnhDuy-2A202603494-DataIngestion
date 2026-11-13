"""Read and normalize source data. TODO: implement functions."""
import logging
import re
import unicodedata
from pathlib import Path
from .models import DocumentPage
from pypdf import PdfReader
from .models import DocumentPage

logger = logging.getLogger(__name__)

def load_pdf(path: Path, document_id: str, source: str) -> list[DocumentPage]:
    reader = PdfReader(path)
    pages: list[DocumentPage] = []

    for page_number, pdf_page in enumerate(reader.pages, start=1):
        try:
            raw_text = pdf_page.extract_text() or ""
            text = normalize_text(raw_text)
        except Exception:
            logger.exception("Could not extract PDF page %s: %s", page_number, path)
            text = ""

        if not text:
            logger.warning("Empty PDF page %s: %s", page_number, path)

        pages.append(
            DocumentPage(
                document_id=document_id,
                source=source,
                page=page_number,
                text=text,
            )
        )

    return pages


def normalize_text(text: str) -> str:
    """TODO: normalize Unicode and whitespace without discarding useful structure."""
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ")

    # PDF may split one word across two visual lines: "recommenda-\ntions".
    text = re.sub(r"(?<=\w)-\n(?=\w)", "", text)

    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
