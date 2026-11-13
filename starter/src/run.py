"""Suggested pipeline entry point; TODO: implement the orchestration."""
import hashlib
import json
import os
import time
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from .chunking import by_paragraph, fixed_size
from .embeddings import MyEmbedder
from .ingestion import load_pdf
from .metadata import tag_sections
from .store import PgVectorStore
import sys
from .evaluation import evaluate_query, summarize

def main() -> None:
    """TODO:

    1. Load the corpus and benchmark; validate at least 30 content pages.
    2. Build strategies A (fixed), B (paragraph) and C (B + metadata filter).
    3. Embed with the same model and store vectors/metadata per strategy.
    4. Run the same dev/test questions and save full top-3 traces.
    5. Report retrieval metrics and prepare samples for manual assessment.

    Follow the five dimensions in ../../BENCHMARK.md.
    """
    starter = Path(__file__).resolve().parents[1]
    root = starter.parent
    load_dotenv(starter / ".env")

    manifest = json.loads(
        (root / "data/manifest.json").read_text(encoding="utf-8")
    )
    questions = json.loads(
        (root / "benchmark/questions.json").read_text(encoding="utf-8")
    )

    if len(questions) < 20:
        raise ValueError("Benchmark needs at least 20 questions")
    if sum(q["split"] == "dev" for q in questions) < 15:
        raise ValueError("Benchmark needs at least 15 dev questions")
    if sum(q["split"] == "test" for q in questions) < 5:
        raise ValueError("Benchmark needs at least 5 test questions")

    pdf_path = root / manifest["local_path"]
    actual_hash = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    if actual_hash != manifest["file_sha256"]:
        raise ValueError("PDF changed since manifest was created")

    all_pages = load_pdf(
        pdf_path, manifest["document_id"], manifest["local_path"]
    )
    wanted = {item["pdf_page"] for item in manifest["pages"]}
    pages = [page for page in all_pages if page.page in wanted]

    if len(pages) != manifest["content_page_count"] or len(pages) < 30:
        raise ValueError("Content page count does not match manifest")
    if any(not page.text for page in pages):
        raise ValueError("A selected content page has no extracted text")
    if any(
        q["gold_source_id"] != manifest["source_id"]
        or q["gold_page"] not in wanted
        for q in questions
    ):
        raise ValueError("Benchmark source/page does not match manifest")

    chunks_a = [
        chunk for page in pages
        for chunk in fixed_size(page, size=500, overlap=50)
    ]
    chunks_b = [
        chunk for page in pages
        for chunk in by_paragraph(page, max_size=500)
    ]
    tag_sections(pages, chunks_a)
    tag_sections(pages, chunks_b)

    embedder = MyEmbedder(os.environ["EMBEDDING_MODEL"])
    store = PgVectorStore(os.environ["DATABASE_URL"], embedder.dimensions)
    store.create_schema()

    start_a = time.perf_counter()
    tokens_before = embedder.total_tokens
    vectors_a = embedder.embed_documents([c.text for c in chunks_a])
    store.upsert("A", chunks_a, vectors_a)
    a_seconds = time.perf_counter() - start_a
    a_tokens = embedder.total_tokens - tokens_before

    start_b = time.perf_counter()
    tokens_before = embedder.total_tokens
    vectors_b = embedder.embed_documents([c.text for c in chunks_b])
    store.upsert("B", chunks_b, vectors_b)
    b_seconds = time.perf_counter() - start_b
    b_tokens = embedder.total_tokens - tokens_before

    start_c = time.perf_counter()
    store.upsert("C", chunks_b, vectors_b)  # Reuse B vectors
    c_seconds = time.perf_counter() - start_c

    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        counts = dict(connection.execute("""
            SELECT strategy, count(*)
            FROM ingestion_chunks
            WHERE strategy IN ('A', 'B', 'C')
            GROUP BY strategy
        """).fetchall())

    expected = {"A": len(chunks_a), "B": len(chunks_b), "C": len(chunks_b)}
    if counts != expected:
        raise RuntimeError(f"Stored counts {counts} differ from {expected}")

    summary = {
        "provider": "OpenRouter",
        "model": embedder.model_name,
        "dimensions": embedder.dimensions,
        "metric": "cosine",
        "search": "exact",
        "pdf_sha256": actual_hash,
        "strategies": {
            "A": {"chunks": len(chunks_a), "seconds": a_seconds,
                  "embedding_tokens": a_tokens},
            "B": {"chunks": len(chunks_b), "seconds": b_seconds,
                  "embedding_tokens": b_tokens},
            "C": {"chunks": len(chunks_b), "seconds": c_seconds,
                  "embedding_tokens": 0},
        },
        "embedding_tokens_total": embedder.total_tokens,
        "cost_usd": None,  # Điền chi phí thực từ OpenRouter sau khi xem billing
    }

    output = starter / "results/ingest_summary.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("Stored rows:", counts)
    print("Embedding tokens:", embedder.total_tokens)
    print("Summary:", output)

def run_split(split: str) -> None:
    starter = Path(__file__).resolve().parents[1]
    root = starter.parent
    load_dotenv(starter / ".env")

    questions = json.loads(
        (root / "benchmark/questions.json").read_text(encoding="utf-8")
    )
    selected_questions = [q for q in questions if q["split"] == split]
    expected_count = {"dev": 20, "test": 10}[split]
    if len(selected_questions) != expected_count:
        raise ValueError(
            f"Expected {expected_count} {split} questions, got {len(selected_questions)}"
        )

    embedder = MyEmbedder(os.environ["EMBEDDING_MODEL"])
    store = PgVectorStore(os.environ["DATABASE_URL"], embedder.dimensions)
    traces = []
    started = time.perf_counter()

    for question in selected_questions:
        query_vector = embedder.embed_query(question["question"])
        hits_by_strategy = {}

        for strategy in ("A", "B", "C"):
            applied_filter = question.get("filter") if strategy == "C" else None
            hits = store.search(
                strategy, query_vector, top_k=3, filters=applied_filter
            )
            if len(hits) != 3:
                raise RuntimeError(
                    f"{question['id']} / {strategy}: expected 3 hits, got {len(hits)}"
                )

            hits_by_strategy[strategy] = hits
            trace = evaluate_query(question, hits)
            trace["strategy"] = strategy
            trace["applied_filter"] = applied_filter
            traces.append(trace)

        if not question.get("filter"):
            b_ids = [h["chunk_id"] for h in hits_by_strategy["B"]]
            c_ids = [h["chunk_id"] for h in hits_by_strategy["C"]]
            if b_ids != c_ids:
                raise RuntimeError(f"{question['id']}: B/C differ without filter")

    metrics = summarize(traces)
    run_info = {
        "split": split,
        "questions": len(selected_questions),
        "traces": len(traces),
        "model": embedder.model_name,
        "query_embedding_tokens": embedder.total_tokens,
        "elapsed_seconds": time.perf_counter() - started,
        "metrics": metrics,
    }

    results = starter / "results"
    results.mkdir(parents=True, exist_ok=True)
    (results / f"{split}_traces.json").write_text(
        json.dumps(traces, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (results / f"{split}_metrics.json").write_text(
        json.dumps(run_info, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(run_info, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    if len(sys.argv) == 1:
        main()
    elif len(sys.argv) == 2 and sys.argv[1] in ("dev", "test"):
        run_split(sys.argv[1])
    else:
        raise SystemExit("Usage: python -m src.run [dev|test]")
