"""
Hybrid retrieval:
  1. Dense  : ChromaDB cosine similarity
  2. Sparse : BM25 keyword search
  3. Fusion : Reciprocal Rank Fusion (RRF)
All config read from .env via python-dotenv.
"""

from __future__ import annotations

import math
import os
import pathlib
import sys
from collections import defaultdict
from typing import Optional

import numpy as np
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from ingest import embed_query
from vector_db import Chunk, get_doc_store as get_store

# ── Config from .env ──────────────────────────────────────────────────────────
TOP_K      = int(os.getenv("TOP_K",    "5"))
USE_HYBRID = os.getenv("USE_HYBRID", "true").lower() == "true"
RRF_K      = int(os.getenv("RRF_K",    "60"))
BM25_K1    = float(os.getenv("BM25_K1",  "1.2"))
BM25_B     = float(os.getenv("BM25_B",   "0.75"))

K1 = BM25_K1
B  = BM25_B


def _tokenize(text: str) -> list[str]:
    return text.lower().split()


def _bm25_scores(query_tokens: list[str], corpus: list[Chunk]) -> dict[str, float]:
    N, df, tfs = len(corpus), defaultdict(int), []

    for chunk in corpus:
        tokens = _tokenize(chunk.text)
        tf: dict[str, int] = defaultdict(int)
        for t in tokens:
            tf[t] += 1
        tfs.append((tokens, tf))
        for t in set(tokens):
            df[t] += 1

    avg_dl = sum(len(t[0]) for t in tfs) / max(N, 1)
    scores = {}
    for chunk, (tokens, tf) in zip(corpus, tfs):
        score, dl = 0.0, len(tokens)
        for qt in query_tokens:
            if qt not in tf:
                continue
            idf    = math.log((N - df[qt] + 0.5) / (df[qt] + 0.5) + 1)
            score += idf * (tf[qt] * (K1 + 1)) / (tf[qt] + K1 * (1 - B + B * dl / avg_dl))
        scores[chunk.chunk_id] = score
    return scores


def _rrf_fusion(
    ranked_lists: list[list[tuple[str, float]]],
    k: int = RRF_K,
) -> list[tuple[str, float]]:
    rrf_scores: dict[str, float] = defaultdict(float)
    for ranked in ranked_lists:
        for rank, (chunk_id, _) in enumerate(ranked):
            rrf_scores[chunk_id] += 1.0 / (k + rank + 1)
    return sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)


def retrieve(
    query:      str,
    doc_ids:    Optional[list[str]] = None,
    top_k:      int  = TOP_K,
    use_hybrid: bool = USE_HYBRID,
) -> list[Chunk]:
    store = get_store()

    # Fetch only chunks for the relevant docs (server-side filter)
    if doc_ids:
        filtered_ids = store._collection.get(
            where   = {"doc_id": {"$in": doc_ids}},
            include = [],
        )["ids"]
    else:
        filtered_ids = store.all_ids()

    if not filtered_ids:
        return []

    corpus = store.get_many(filtered_ids)
    if not corpus:
        return []

    # Dense retrieval
    query_vec     = embed_query(query)
    raw_dense     = store.search(query_vec, k=top_k * 3, doc_ids=doc_ids)
    dense_results = [
        (cid, 1.0 - (dist / 2.0))   # cosine dist → similarity score
        for cid, dist in raw_dense
    ]

    if not use_hybrid:
        merged = dense_results[:top_k]
    else:
        query_tokens  = _tokenize(query)
        bm25          = _bm25_scores(query_tokens, corpus)
        sparse_sorted = sorted(bm25.items(), key=lambda x: x[1], reverse=True)
        merged        = _rrf_fusion([dense_results, sparse_sorted[:top_k * 3]])

    chunk_map     = {c.chunk_id: c for c in corpus}
    result_chunks = []
    for chunk_id, score in merged[:top_k]:
        chunk = chunk_map.get(chunk_id)
        if chunk:
            chunk.score = round(score, 4)
            result_chunks.append(chunk)

    return result_chunks