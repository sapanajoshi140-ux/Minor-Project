"""
ingest.py
---------
Full ingestion pipeline:
  1. Load & parse document (PDF / TXT / DOCX / PPTX)
     — For DOCX and PPTX the generated searchable PDF is used so we go
       through a single, consistent PyPDFLoader code path.
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
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

load_dotenv()

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from vector_db import Chunk, get_doc_store, get_vector_store

# ── Config from .env ──────────────────────────────────────────────────────────
EMBEDDING_MODEL  = os.getenv("EMBEDDING_MODEL",  "nomic-embed-text")
OLLAMA_BASE_URL  = os.getenv("OLLAMA_BASE_URL",  "http://localhost:11434")
CHUNK_SIZE       = int(os.getenv("CHUNK_SIZE",       "400"))
CHUNK_OVERLAP    = int(os.getenv("CHUNK_OVERLAP",    "80"))
EMBEDDING_DIM    = int(os.getenv("EMBEDDING_DIM",    "768"))
EMBED_BATCH_SIZE = int(os.getenv("EMBED_BATCH_SIZE", "32"))
EMBED_TIMEOUT    = int(os.getenv("EMBED_TIMEOUT",    "60"))


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
def _load_file(path: str, generated_pdf_path: str | None = None):
    """
    Load a document and return a list of LangChain Documents.

    For DOCX / PPTX the upload pipeline already converts the file to a
    searchable PDF (generated_pdf_path).  We load that PDF through
    PyPDFLoader so every file type goes through the same code path and
    page metadata stays consistent.

    Parameters
    ----------
    path               : path to the original uploaded file.
    generated_pdf_path : path to the generated searchable PDF (required for
                         DOCX / DOC / PPTX / PPT).
    """
    ext = os.path.splitext(path)[1].lower()

    if ext == ".pdf":
        return PyPDFLoader(path).load()

    elif ext == ".txt":
        return TextLoader(path, encoding="utf-8").load()

    elif ext in (".docx", ".doc", ".pptx", ".ppt"):
        if not generated_pdf_path or not os.path.exists(generated_pdf_path):
            raise ValueError(
                f"Generated PDF not found for {ext} file '{path}'. "
                "Ensure generate_searchable_pdf ran successfully before ingestion."
            )
        return PyPDFLoader(generated_pdf_path).load()

    elif ext in (".png", ".jpg", ".jpeg"):
        # Images are scanned docs — OCR text is ingested via ingest_from_db_pages.
        return []

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
def ingest_file(
    file_path: str,
    doc_id: str,
    generated_pdf_path: str | None = None,
) -> dict:
    store       = get_doc_store()
    raw_docs    = _load_file(file_path, generated_pdf_path=generated_pdf_path)
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


def ingest_from_file_path(
    doc_id: str,
    file_path: str,
    generated_pdf_path: str | None = None,
) -> dict:
    """
    Ingest a TEXT document directly from its file on disk.

    Parameters
    ----------
    doc_id             : the document UUID from the app.
    file_path          : absolute path to the original uploaded file.
    generated_pdf_path : path to the generated searchable PDF — required for
                         DOCX / DOC / PPTX / PPT so we load the converted PDF
                         instead of the original binary format.
    """
    return ingest_file(file_path, doc_id, generated_pdf_path=generated_pdf_path)