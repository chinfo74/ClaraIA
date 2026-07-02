"""
Vector store behind a small interface so we can later swap ChromaDB for
pgvector/Qdrant without touching the ingestion or retrieval code.

Embeddings are computed by `core.llm_client.embed_texts` (provider-agnostic) and
passed in explicitly, so the store never needs to know which embedding provider
is configured.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from ..core.config import get_settings
from ..core.llm_client import embed_texts


@dataclass
class SearchHit:
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0


class VectorStore(ABC):
    @abstractmethod
    def add(
        self,
        ids: list[str],
        texts: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict[str, Any]],
    ) -> None: ...

    @abstractmethod
    def query(self, embedding: list[float], n_results: int = 5) -> list[SearchHit]: ...

    @abstractmethod
    def delete_by_source(self, source: str) -> int:
        """Remove all chunks tagged with this source filename. Returns count removed."""

    @abstractmethod
    def count(self) -> int: ...


class ChromaVectorStore(VectorStore):
    def __init__(self, persist_dir: str, collection_name: str) -> None:
        import chromadb

        self._client = chromadb.PersistentClient(path=persist_dir)
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def add(
        self,
        ids: list[str],
        texts: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict[str, Any]],
    ) -> None:
        self._collection.add(
            ids=ids, documents=texts, embeddings=embeddings, metadatas=metadatas
        )

    def query(self, embedding: list[float], n_results: int = 5) -> list[SearchHit]:
        res = self._collection.query(query_embeddings=[embedding], n_results=n_results)
        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        hits: list[SearchHit] = []
        for doc, meta, dist in zip(docs, metas, dists):
            # cosine distance -> similarity
            hits.append(SearchHit(text=doc, metadata=meta or {}, score=round(1.0 - dist, 4)))
        return hits

    def delete_by_source(self, source: str) -> int:
        before = self._collection.count()
        self._collection.delete(where={"source": source})
        return before - self._collection.count()

    def count(self) -> int:
        return self._collection.count()


@lru_cache
def get_vectorstore() -> VectorStore:
    settings = get_settings()
    return ChromaVectorStore(settings.chroma_dir, settings.chroma_collection)


def search(query: str, n_results: int = 5) -> list[SearchHit]:
    """Convenience helper for tests/debug: embed a query and return matching chunks."""
    embedding = embed_texts([query])[0]
    return get_vectorstore().query(embedding, n_results=n_results)
