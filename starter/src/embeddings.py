"""Choose a real embedding provider (API or local) and implement this contract."""
from typing import Protocol
import math
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


class Embedder(Protocol):
    model_name: str
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per input text, in the same order."""
        ...

    def embed_query(self, question: str) -> list[float]:
        """Return a query vector compatible with the stored document vectors."""
        ...

class MyEmbedder:
    """TODO: implement a provider adapter; do not silently fall back to mock vectors."""

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        if model_name != "openai/text-embedding-3-small":
            raise ValueError(f"Unsupported embedding model: {model_name}")

        api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        if not api_key or "KEY_CUA_BAN" in api_key:
            raise ValueError("Set a real OPENROUTER_API_KEY in starter/.env")

        self.dimensions = 1536
        self.total_tokens = 0
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        })

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts or any(not text.strip() for text in texts):
            raise ValueError("Embedding inputs must be non-empty strings")

        response = self.session.post(
            "https://openrouter.ai/api/v1/embeddings",
            json={
                "model": self.model_name,
                "dimensions": self.dimensions,
                "input": texts,
            },
            timeout=60,
        )
        if not response.ok:
            raise RuntimeError(
                f"OpenRouter embeddings request failed: HTTP {response.status_code}"
            )

        payload = response.json()
        items = sorted(payload["data"], key=lambda item: item["index"])
        if [item["index"] for item in items] != list(range(len(texts))):
            raise RuntimeError("Embedding response indices do not match inputs")

        vectors = [item["embedding"] for item in items]
        if any(
            len(vector) != self.dimensions
            or not all(math.isfinite(value) for value in vector)
            for vector in vectors
        ):
            raise RuntimeError("Invalid embedding dimensions or values")

        self.total_tokens += payload.get("usage", {}).get("total_tokens", 0)
        return vectors

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), 32):
            vectors.extend(self._embed_batch(texts[start : start + 32]))
        return vectors

    def embed_query(self, question: str) -> list[float]:
        return self._embed_batch([question])[0]
