"""
Single-store layer using ChromaDB.
All config read from .env via python-dotenv.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import sys
from dataclasses import dataclass
from typing import Optional

import numpy as np
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(pathlib.Path(__file__).parent))

# ── Config from .env ──────────────────────────────────────────────────────────
_BASE           = pathlib.Path(__file__).parent
CHROMA_DIR      = os.getenv("CHROMA_DIR",      str(_BASE / "data" / ".chromadb"))
COLLECTION_NAME = os.getenv("CHROMA_COLLECTION")


# ── Data model ────────────────────────────────────────────────────────────────
@dataclass
class Chunk:
    chunk_id:  str
    doc_id:    str
    text:      str
    page:      int   = 0
    start_idx: int   = 0
    score:     float = 0.0


# ── ChromaDB store ────────────────────────────────────────────────────────────
class ChromaStore:
    def __init__(self):
        import chromadb
        os.makedirs(CHROMA_DIR, exist_ok=True)
        self._client     = chromadb.PersistentClient(path=CHROMA_DIR)
        self._collection = self._client.get_or_create_collection(
            name     = COLLECTION_NAME,
            metadata = {"hnsw:space": "cosine"},
        )

    # ── Write ─────────────────────────────────────────────────────────────────

    def add(self, chunks: list[Chunk], embeddings: Optional[np.ndarray] = None):
        if not chunks:
            return
        ids       = [c.chunk_id for c in chunks]
        documents = [c.text     for c in chunks]
        metadatas = [
            {"doc_id": c.doc_id, "page": c.page, "start_idx": c.start_idx}
            for c in chunks
        ]
        kwargs: dict = {"ids": ids, "documents": documents, "metadatas": metadatas}
        if embeddings is not None:
            kwargs["embeddings"] = embeddings.tolist()
        self._collection.add(**kwargs)

    # ── Read ──────────────────────────────────────────────────────────────────

    def get(self, chunk_id: str) -> Optional[Chunk]:
        result = self._collection.get(ids=[chunk_id], include=["documents", "metadatas"])
        if not result["ids"]:
            return None
        return self._row_to_chunk(result["ids"][0], result["documents"][0], result["metadatas"][0])

    def get_many(self, ids: list[str]) -> list[Chunk]:
        if not ids:
            return []
        result = self._collection.get(ids=ids, include=["documents", "metadatas"])
        return [
            self._row_to_chunk(cid, doc, meta)
            for cid, doc, meta in zip(result["ids"], result["documents"], result["metadatas"])
        ]

    def all_ids(self) -> list[str]:
        return self._collection.get(include=[])["ids"]

    def list_docs(self) -> list[str]:
        result = self._collection.get(include=["metadatas"])
        return list({m["doc_id"] for m in result["metadatas"]})

    # ── Search ────────────────────────────────────────────────────────────────

    def search(
        self,
        query_vec: np.ndarray,
        k:         int = 5,
        doc_ids:   Optional[list[str]] = None,
    ) -> list[tuple[str, float]]:
        total = self._collection.count()
        if total == 0:
            return []
        k     = min(k, total)
        where = {"doc_id": {"$in": doc_ids}} if doc_ids else None
        kwargs: dict = {
            "query_embeddings": query_vec.tolist(),
            "n_results":        k,
            "include":          ["distances"],
        }
        if where:
            kwargs["where"] = where
        result = self._collection.query(**kwargs)
        return list(zip(result["ids"][0], result["distances"][0]))

    # ── Delete ────────────────────────────────────────────────────────────────

    def delete_doc(self, doc_id: str):
        self._collection.delete(where={"doc_id": {"$eq": doc_id}})

    def clear(self):
        self._client.delete_collection(COLLECTION_NAME)
        self._collection = self._client.get_or_create_collection(
            name     = COLLECTION_NAME,
            metadata = {"hnsw:space": "cosine"},
        )

    # ── Internal ──────────────────────────────────────────────────────────────

    @staticmethod
    def _row_to_chunk(chunk_id: str, document: str, metadata: dict) -> Chunk:
        return Chunk(
            chunk_id  = chunk_id,
            doc_id    = metadata.get("doc_id",    ""),
            text      = document,
            page      = int(metadata.get("page",      0)),
            start_idx = int(metadata.get("start_idx", 0)),
        )


# ── Singleton ─────────────────────────────────────────────────────────────────
_store: Optional[ChromaStore] = None


def get_store() -> ChromaStore:
    global _store
    if _store is None:
        _store = ChromaStore()
    return _store


def get_doc_store()            -> ChromaStore: return get_store()
def get_vector_store(dim=768)  -> ChromaStore: return get_store()


def reset_stores():
    global _store
    if os.path.exists(CHROMA_DIR):
        shutil.rmtree(CHROMA_DIR)
    _store = None