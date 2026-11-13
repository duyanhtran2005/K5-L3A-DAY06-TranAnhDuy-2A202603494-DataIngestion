"""TODO: evaluate retrieved evidence and preserve per-query traces."""
from typing import Any
import re
import unicodedata

def _flat(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = " ".join(text.split())
    return re.sub(r"\s+([,.;:])", r"\1", text)

def evaluate_query(question: dict[str, Any], hits: list[dict[str, Any]]) -> dict[str, Any]:
    """TODO: check source/page and enough gold evidence; keep hit@1 and hit@3 trace.

    Accept any documented alternative gold evidence. Do not infer human grounding
    or chunk coherence labels from exact string match.
    """
    gold_items = question.get("gold_evidence") or [{
        "gold_source_id": question["gold_source_id"],
        "gold_page": question["gold_page"],
        "evidence_quote": question["evidence_quote"],
    }]

    traced_hits = []
    for rank, hit in enumerate(hits[:3], start=1):
        metadata = hit["metadata"]
        matched = any(
            metadata.get("document_id") == gold["gold_source_id"]
            and metadata.get("page") == gold["gold_page"]
            and _flat(gold["evidence_quote"]) in _flat(hit["text"])
            for gold in gold_items
        )
        traced_hits.append({
            "rank": rank,
            "chunk_id": hit["chunk_id"],
            "text": hit["text"],
            "score": hit["score"],
            "metadata": metadata,
            "auto_evidence_hit": matched,
        })

    return {
        "id": question["id"],
        "split": question["split"],
        "question": question["question"],
        "expected_answer": question["expected_answer"],
        "filter": question.get("filter"),
        "gold_evidence": gold_items,
        "hits": traced_hits,
        "hit1": bool(traced_hits and traced_hits[0]["auto_evidence_hit"]),
        "hit3": any(hit["auto_evidence_hit"] for hit in traced_hits),
    }


def summarize(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """TODO: aggregate Hit@1 and Evidence Hit@3 by strategy and dev/test split."""
    result: dict[str, dict[str, dict[str, int]]] = {}

    for trace in traces:
        strategy = trace["strategy"]
        split = trace["split"]
        stats = result.setdefault(strategy, {}).setdefault(
            split, {"N": 0, "hit1_n": 0, "hit3_n": 0}
        )
        stats["N"] += 1
        stats["hit1_n"] += int(trace["hit1"])
        stats["hit3_n"] += int(trace["hit3"])

    return result
