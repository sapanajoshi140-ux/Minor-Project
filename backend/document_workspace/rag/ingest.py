"""
ingest.py
---------
Full ingestion pipeline:
  1. Load & parse document (PDF / TXT / DOCX)
  2. Split into overlapping chunks with page tracking
  3. Embed via Ollama
  4. Store in ChromaDB
All config read from .env via python-dotenv.
"""

from __future__ import annotations

import os
import pathlib
import sys
import uuid

import numpy as np
import requests
from dotenv import load_dotenv
from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

load_dotenv()

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from vector_db import Chunk, get_doc_store, get_vector_store

# ── Config from .env ──────────────────────────────────────────────────────────
EMBEDDING_MODEL  = os.getenv("EMBEDDING_MODEL")
OLLAMA_BASE_URL  = os.getenv("OLLAMA_BASE_URL")
CHUNK_SIZE       = int(os.getenv("CHUNK_SIZE"))
CHUNK_OVERLAP    = int(os.getenv("CHUNK_OVERLAP"))
EMBEDDING_DIM    = int(os.getenv("EMBEDDING_DIM"))
EMBED_BATCH_SIZE = int(os.getenv("EMBED_BATCH_SIZE"))
EMBED_TIMEOUT    = int(os.getenv("EMBED_TIMEOUT"))


# ── Embedding ─────────────────────────────────────────────────────────────────
def embed_texts(texts: list[str]) -> np.ndarray:
    all_vectors = []
    for i in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[i : i + EMBED_BATCH_SIZE]
        resp  = requests.post(
            f"{OLLAMA_BASE_URL}/api/embed",
            json    = {"model": EMBEDDING_MODEL, "input": batch},
            timeout = EMBED_TIMEOUT,
        )
        resp.raise_for_status()
        all_vectors.extend(resp.json()["embeddings"])
    return np.array(all_vectors, dtype=np.float32)


def embed_query(text: str) -> np.ndarray:
    return embed_texts([text])


# ── Loader ────────────────────────────────────────────────────────────────────
def _load_file(path: str):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return PyPDFLoader(path).load()
    elif ext == ".txt":
        return TextLoader(path, encoding="utf-8").load()
    elif ext in (".docx", ".doc"):
        return Docx2txtLoader(path).load()
    else:
        raise ValueError(f"Unsupported file type: {ext}")


# ── Splitter ──────────────────────────────────────────────────────────────────
def _split(docs) -> list[dict]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size      = CHUNK_SIZE,
        chunk_overlap   = CHUNK_OVERLAP,
        length_function = len,
        add_start_index = True,
    )
    return [
        {
            "text":      d.page_content,
            "page":      d.metadata.get("page",        0),
            "start_idx": d.metadata.get("start_index", 0),
        }
        for d in splitter.split_documents(docs)
    ]


# ── Public API ────────────────────────────────────────────────────────────────
def ingest_file(file_path: str, doc_id: str) -> dict:
    store       = get_doc_store()
    raw_docs    = _load_file(file_path)
    split_items = _split(raw_docs)

    if not split_items:
        raise ValueError("Document is empty or could not be parsed.")

    chunks = [
        Chunk(
            chunk_id  = str(uuid.uuid4()),
            doc_id    = doc_id,
            text      = item["text"],
            page      = item["page"],
            start_idx = item["start_idx"],
        )
        for item in split_items
    ]

    embeddings = embed_texts([c.text for c in chunks])
    store.add(chunks, embeddings)

    return {"doc_id": doc_id, "pages": len(raw_docs), "chunks": len(chunks)}


def list_documents() -> list[str]:
    return get_doc_store().list_docs()


def delete_document(doc_id: str):
    get_doc_store().delete_doc(doc_id)


# ── App integration entrypoints ───────────────────────────────────────────────

def ingest_from_db_pages(doc_id: str, pages: list[dict]) -> dict:
    """
    Ingest a SCANNED document whose text lives in DocumentPage rows.

    Parameters
    ----------
    doc_id : the document UUID from the app (used as RAG doc_id too).
    pages  : list of page dicts from the upload pipeline, each with:
               page_number, extracted_text, ocr_type, confidence_score

    Returns
    -------
    {"doc_id": ..., "pages": ..., "chunks": ...}
    """
    store = get_doc_store()

    splitter = RecursiveCharacterTextSplitter(
        chunk_size      = CHUNK_SIZE,
        chunk_overlap   = CHUNK_OVERLAP,
        length_function = len,
        add_start_index = True,
    )

    chunks: list[Chunk] = []
    for page in pages:
        text = (page.get("extracted_text") or "").strip()
        if not text:
            continue
        page_num = page.get("page_number", 1)

        # Split each page's text independently so page numbers stay accurate
        splits = splitter.split_text(text)
        for i, chunk_text in enumerate(splits):
            if not chunk_text.strip():
                continue
            chunks.append(Chunk(
                chunk_id  = str(uuid.uuid4()),
                doc_id    = doc_id,
                text      = chunk_text,
                page      = page_num - 1,   # 0-based to match ingest_file convention
                start_idx = i,
            ))

    if not chunks:
        raise ValueError("No text found in document pages to ingest.")

    embeddings = embed_texts([c.text for c in chunks])
    store.add(chunks, embeddings)

    return {
        "doc_id": doc_id,
        "pages":  len(pages),
        "chunks": len(chunks),
    }


def ingest_from_file_path(doc_id: str, file_path: str) -> dict:
    """
    Ingest a TEXT document directly from its file on disk.
    Same as ingest_file() but uses the app's doc_id instead of generating one.

    Parameters
    ----------
    doc_id    : the document UUID from the app.
    file_path : absolute path to the original uploaded file.
    """
    return ingest_file(file_path, doc_id)