"""Implement fixed-size and structure-aware chunking."""
import re
import textwrap
from .models import Chunk, DocumentPage

_HEADING = re.compile(
    r"^(?:"
    r"\d+(?:\.\d+)*\.?\s+[A-Z]"          # 5.1 Govern
    r"|(?:GOVERN|MAP|MEASURE|MANAGE)\s+\d+(?:\.\d+)?\s*:"
    r"|Appendix [A-D]:"
    r"|Table \d+:"
    r")"
)
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9“])")


def _flat(text: str) -> str:
    text = " ".join(text.split())
    return re.sub(r"\s+([,.;:])", r"\1", text)


def _make_chunk(page: DocumentPage, chunk_id: str, text: str) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        document_id=page.document_id,
        source=page.source,
        page=page.page,
        text=text,
        metadata=page.metadata.copy(),
    )

def fixed_size(page: DocumentPage, size: int, overlap: int) -> list[Chunk]:
    """TODO: split text into overlapping windows and retain page metadata."""
    if size <= 0 or overlap < 0 or overlap >= size:
        raise ValueError("Require size > 0 and 0 <= overlap < size")

    text = _flat(page.text)
    if not text:
        return []

    step = size - overlap
    return [
        _make_chunk(
            page,
            f"{page.document_id}:p{page.page}:fixed:{size}:{overlap}:{index}",
            text[start : start + size],
        )
        for index, start in enumerate(range(0, len(text), step))
    ]

def _blocks(page: DocumentPage) -> list[str]:
    blocks: list[str] = []
    current: list[str] = []

    for line in page.text.splitlines():
        line = line.strip()
        if not line:
            continue
        if _HEADING.match(line) and current:
            blocks.append(_flat(" ".join(current)))
            current = []
        current.append(line)

    if current:
        blocks.append(_flat(" ".join(current)))
    return blocks

def _units(block: str, max_size: int) -> list[str]:
    result: list[str] = []
    for sentence in _SENTENCE_BREAK.split(block):
        if len(sentence) <= max_size:
            result.append(sentence)
        else:
            result.extend(
                textwrap.wrap(
                    sentence,
                    width=max_size,
                    break_long_words=True,
                    break_on_hyphens=False,
                )
            )
    return result

def by_paragraph(page: DocumentPage, max_size: int) -> list[Chunk]:
    if max_size <= 0:
        raise ValueError("max_size must be positive")

    texts: list[str] = []
    for block in _blocks(page):
        current = ""
        for unit in _units(block, max_size):
            candidate = f"{current} {unit}".strip()
            if current and len(candidate) > max_size:
                texts.append(current)
                current = unit
            else:
                current = candidate
        if current:
            texts.append(current)

    return [
        _make_chunk(
            page,
            f"{page.document_id}:p{page.page}:paragraph:{max_size}:{index}",
            text,
        )
        for index, text in enumerate(texts)
    ]
