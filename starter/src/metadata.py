"""Assign AI RMF Core section metadata to chunks."""

import re
from collections import defaultdict

from .models import Chunk, DocumentPage

_HEADING = re.compile(
    r"\b5\.[1-4]\s+(Govern|Map|Measure|Manage)\b"
    r"|\b6\.\s+AI RMF Profiles\b",
    re.IGNORECASE,
)

def _flat(text: str) -> str:
    text = " ".join(text.split())
    return re.sub(r"\s+([,.;:])", r"\1", text)

def tag_sections(pages: list[DocumentPage], chunks: list[Chunk]) -> None:
    chunks_by_page: dict[int, list[Chunk]] = defaultdict(list)
    for chunk in chunks:
        chunks_by_page[chunk.page].append(chunk)

    current_section: str | None = None

    for page in sorted(pages, key=lambda p: p.page):
        text = _flat(page.text)
        boundaries = [
            (match.start(), match.group(1).upper() if match.group(1) else None)
            for match in _HEADING.finditer(text)
        ]

        def section_at(position: int) -> str | None:
            section = current_section
            for boundary_position, value in boundaries:
                if boundary_position > position:
                    break
                section = value
            return section

        search_from = 0
        for chunk in chunks_by_page[page.page]:
            start = text.find(chunk.text, search_from)
            if start < 0:
                raise ValueError(
                    f"Cannot locate chunk {chunk.chunk_id} on PDF page {page.page}"
                )
            end = start + len(chunk.text)

            first = section_at(start)
            last = section_at(end - 1)
            if first == last and first is not None:
                chunk.metadata["section"] = first
            else:
                chunk.metadata.pop("section", None)

            search_from = start + 1

        if boundaries:
            current_section = boundaries[-1][1]