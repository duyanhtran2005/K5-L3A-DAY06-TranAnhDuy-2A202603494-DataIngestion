"""TODO: store and search vectors using PostgreSQL + pgvector."""
from typing import Any
from .models import Chunk
import psycopg
from psycopg import sql
import json
import math
from collections import defaultdict

class PgVectorStore:
    def __init__(self, database_url: str, dimensions: int) -> None:
        """TODO: retain connection settings; validate model dimensions."""
        if not database_url:
            raise ValueError("DATABASE_URL is required")
        if type(dimensions) is not int or dimensions <= 0:
            raise ValueError("dimensions must be a positive integer")

        self.database_url = database_url
        self.dimensions = dimensions

    def create_schema(self) -> None:
        """TODO: create table with vector column and source/page/filter metadata."""
        create_table = sql.SQL("""
            CREATE TABLE IF NOT EXISTS ingestion_chunks (
                strategy TEXT NOT NULL,
                chunk_id TEXT NOT NULL,
                document_id TEXT NOT NULL,
                source TEXT NOT NULL,
                page INTEGER NOT NULL CHECK (page > 0),
                text TEXT NOT NULL,
                metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                embedding vector({}) NOT NULL,
                PRIMARY KEY (strategy, chunk_id)
            )
        """).format(sql.Literal(self.dimensions))

        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
                cursor.execute(create_table)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS ingestion_chunks_strategy_section_idx
                    ON ingestion_chunks (strategy, (metadata->>'section'))
                """)

    def upsert(self, strategy: str, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        """TODO: validate lengths/dimensions and write stable IDs without duplicates.

        When re-ingesting changed source documents, remove obsolete chunks too.
        """
        if not strategy.strip():
            raise ValueError("strategy is required")
        if not chunks or len(chunks) != len(vectors):
            raise ValueError("chunks and vectors must be non-empty and equal length")

        rows = []
        keep_ids: dict[str, list[str]] = defaultdict(list)
        seen_ids: set[str] = set()

        for chunk, vector in zip(chunks, vectors, strict=True):
            if not chunk.chunk_id or chunk.chunk_id in seen_ids:
                raise ValueError(f"Missing or duplicate chunk ID: {chunk.chunk_id}")
            if not chunk.document_id or not chunk.source or chunk.page <= 0:
                raise ValueError(f"Invalid source metadata: {chunk.chunk_id}")
            if not chunk.text.strip():
                raise ValueError(f"Empty chunk: {chunk.chunk_id}")
            if len(vector) != self.dimensions:
                raise ValueError(f"Wrong vector dimension: {chunk.chunk_id}")

            values = [float(value) for value in vector]
            if not all(math.isfinite(value) for value in values):
                raise ValueError(f"Non-finite vector: {chunk.chunk_id}")

            seen_ids.add(chunk.chunk_id)
            keep_ids[chunk.document_id].append(chunk.chunk_id)
            rows.append((
                strategy,
                chunk.chunk_id,
                chunk.document_id,
                chunk.source,
                chunk.page,
                chunk.text,
                json.dumps(chunk.metadata, ensure_ascii=False),
                json.dumps(values),
            ))

        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.executemany("""
                    INSERT INTO ingestion_chunks
                        (strategy, chunk_id, document_id, source, page,
                         text, metadata, embedding)
                    VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::vector)
                    ON CONFLICT (strategy, chunk_id) DO UPDATE SET
                        document_id = EXCLUDED.document_id,
                        source = EXCLUDED.source,
                        page = EXCLUDED.page,
                        text = EXCLUDED.text,
                        metadata = EXCLUDED.metadata,
                        embedding = EXCLUDED.embedding
                """, rows)

                # This call must contain the complete chunk set for each
                # document_id in this strategy, not one page or one batch.
                for document_id, ids in keep_ids.items():
                    cursor.execute("""
                        DELETE FROM ingestion_chunks
                        WHERE strategy = %s
                          AND document_id = %s
                          AND NOT (chunk_id = ANY(%s::text[]))
                    """, (strategy, document_id, ids))

    def search(self, strategy: str, query_vector: list[float], top_k: int = 3,
               filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """TODO: filter permitted metadata in SQL, rank by cosine distance, return top-k.

        Return chunk ID, text, score and metadata. Parameterize user-supplied values.
        """
        if not strategy.strip():
            raise ValueError("strategy is required")
        if type(top_k) is not int or top_k <= 0:
            raise ValueError("top_k must be a positive integer")
        if len(query_vector) != self.dimensions:
            raise ValueError("Wrong query vector dimension")

        values = [float(value) for value in query_vector]
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Query vector contains non-finite values")
        vector_literal = json.dumps(values)

        filters = filters or {}
        if set(filters) - {"section"}:
            raise ValueError("Only the section filter is supported")
        section = filters.get("section")
        if section is not None and section not in {
            "GOVERN", "MAP", "MEASURE", "MANAGE"
        }:
            raise ValueError(f"Invalid section: {section}")

        section_sql = "AND metadata->>'section' = %s" if section else ""
        query = f"""
            SELECT chunk_id, document_id, source, page, text, metadata,
                   1 - (embedding <=> %s::vector) AS score
            FROM ingestion_chunks
            WHERE strategy = %s
              {section_sql}
            ORDER BY embedding <=> %s::vector, chunk_id
            LIMIT %s
        """
        params = [vector_literal, strategy]
        if section:
            params.append(section)
        params.extend([vector_literal, top_k])

        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()

        hits = []
        for chunk_id, document_id, source, page, text, extra, score in rows:
            metadata = dict(extra or {})
            metadata.update({
                "document_id": document_id,
                "source": source,
                "page": page,
            })
            hits.append({
                "chunk_id": chunk_id,
                "text": text,
                "score": float(score),
                "metadata": metadata,
            })
        return hits
