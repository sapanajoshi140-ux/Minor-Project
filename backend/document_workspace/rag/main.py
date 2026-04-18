"""
main.py
-------
FastAPI backend for document upload + RAG-based chat.
All config read from .env via python-dotenv.

Run:
    uvicorn main:app --reload

Endpoints:
  POST   /upload                Upload & index a document
  GET    /documents             List indexed document IDs
  DELETE /documents/{doc_id}   Remove a document
  POST   /chat                 Q&A (full JSON response)
  POST   /chat/stream          Q&A (SSE streaming)
  GET    /session/{id}/history Get chat history
  DELETE /session/{id}         Clear chat history
  DELETE /clear                Wipe entire index
  GET    /health               Health check
"""

from __future__ import annotations

import json as _json
import os
import pathlib
import shutil
import sys
import uuid
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

_HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(_HERE))

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from generate import build_context, generate_answer, generate_answer_stream, summarize_text, summarize_text_stream
from ingest import delete_document, ingest_file, list_documents
from retrieve import retrieve, TOP_K, USE_HYBRID
from vector_db import reset_stores

# ── Config from .env ──────────────────────────────────────────────────────────
UPLOAD_DIR = _HERE / os.getenv("UPLOAD_DIR", "data/uploads")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
ALLOWED_EXTENSIONS = set(
    f".{e.lstrip('.')}" for e in
    os.getenv("ALLOWED_EXTENSIONS", ".pdf,.txt,.docx,.doc").split(",")
)

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="Document Chat API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins     = CORS_ORIGINS,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
    allow_credentials = True,
)

# ── Session store ─────────────────────────────────────────────────────────────
SESSIONS: dict[str, list[dict]] = {}


# ── Text cleaning ─────────────────────────────────────────────────────────────
import re as _re

def _clean_text(text: str) -> str:
    """Strip control characters that break JSON encoding (common in PDF text)."""
    text = text.replace('\f',   '\n')
    text = text.replace('\r\n', '\n')
    text = text.replace('\r',   '\n')
    text = text.replace('\x00', '')
    text = _re.sub(r'[\x01-\x08\x0b\x0e-\x1f\x7f]', '', text)
    return text.strip()


# ── Pydantic models ───────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    question:   str
    session_id: Optional[str]       = None
    doc_ids:    Optional[list[str]] = None
    top_k:      int  = TOP_K
    use_hybrid: bool = USE_HYBRID


class ChatResponse(BaseModel):
    answer:       str
    session_id:   str
    citations:    list[dict]
    sources_used: int


class SummarizeRequest(BaseModel):
    text:   str
    length: str = "medium"   # "short" | "medium" | "long" | "bullets"


class SummarizeResponse(BaseModel):
    summary:      str
    length:       str
    char_count:   int


class UploadResponse(BaseModel):
    doc_id:  str
    pages:   int
    chunks:  int
    message: str


# ── Upload ────────────────────────────────────────────────────────────────────
@app.post("/upload", response_model=UploadResponse)
async def upload_document(file: UploadFile = File(...)):
    filename = file.filename or "upload"
    ext      = os.path.splitext(filename)[1].lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported type '{ext}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    base      = os.path.splitext(filename)[0]
    doc_id    = f"{base}_{uuid.uuid4().hex[:6]}"
    save_path = str(UPLOAD_DIR / f"{doc_id}{ext}")

    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        result = ingest_file(save_path, doc_id)
    except Exception as e:
        if os.path.exists(save_path):
            os.remove(save_path)
        raise HTTPException(status_code=422, detail=str(e))

    return UploadResponse(
        doc_id  = doc_id,
        pages   = result["pages"],
        chunks  = result["chunks"],
        message = f"Indexed '{filename}' → {result['chunks']} chunks from {result['pages']} page(s).",
    )


# ── Document management ───────────────────────────────────────────────────────
@app.get("/documents")
def get_documents():
    return {"documents": list_documents()}


@app.delete("/documents/{doc_id}")
def remove_document(doc_id: str):
    delete_document(doc_id)
    return {"status": "deleted", "doc_id": doc_id}


# ── Chat (JSON) ───────────────────────────────────────────────────────────────
@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    question = _clean_text(req.question)
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    session_id = req.session_id or str(uuid.uuid4())
    history    = SESSIONS.setdefault(session_id, [])

    chunks = retrieve(
        query      = question,
        doc_ids    = req.doc_ids,
        top_k      = req.top_k,
        use_hybrid = req.use_hybrid,
    )
    if not chunks:
        raise HTTPException(
            status_code=404,
            detail="No indexed documents found. Please upload a document first.",
        )

    answer, citations = generate_answer(question, chunks, history)
    history.append({"role": "user",      "content": question})
    history.append({"role": "assistant", "content": answer})

    return ChatResponse(
        answer       = answer,
        session_id   = session_id,
        citations    = citations,
        sources_used = len(chunks),
    )


# ── Chat (SSE streaming) ──────────────────────────────────────────────────────
@app.post("/chat/stream")
def chat_stream(req: ChatRequest):
    question = _clean_text(req.question)
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    session_id = req.session_id or str(uuid.uuid4())
    history    = SESSIONS.setdefault(session_id, [])

    chunks = retrieve(
        query      = question,
        doc_ids    = req.doc_ids,
        top_k      = req.top_k,
        use_hybrid = req.use_hybrid,
    )
    if not chunks:
        raise HTTPException(status_code=404, detail="No indexed documents found.")

    full_answer: list[str] = []

    def event_stream():
        import json as _json
        _, citations = build_context(chunks)
        yield f"event: meta\ndata: {_json.dumps({'session_id': session_id, 'citations': citations})}\n\n"

        for token in generate_answer_stream(question, chunks, history):
            full_answer.append(token)
            yield f"data: {token}\n\n"

        history.append({"role": "user",      "content": question})
        history.append({"role": "assistant", "content": "".join(full_answer)})
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── Summarize (JSON) ──────────────────────────────────────────────────────────
@app.post(
    "/summarize",
    response_model=SummarizeResponse,
    summary="Summarize selected text",
    description=(
        "Pass any selected text from a document and get a concise summary. "
        "Use `length` to control output size: "
        "`short` (2-3 sentences), `medium` (1 paragraph), "
        "`long` (detailed with bullets), `bullets` (bullet points only)."
    ),
    tags=["Summarize"],
)
def summarize(req: SummarizeRequest):
    cleaned = _clean_text(req.text)

    if not cleaned:
        raise HTTPException(status_code=400, detail="Text cannot be empty.")

    allowed_lengths = {"short", "medium", "long", "bullets"}
    if req.length not in allowed_lengths:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid length '{req.length}'. Choose from: {', '.join(allowed_lengths)}.",
        )

    if len(cleaned) > 50_000:
        raise HTTPException(
            status_code=400,
            detail="Text is too long. Maximum 50,000 characters per request.",
        )

    try:
        summary = summarize_text(cleaned, length=req.length)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Summarization failed: {e}")

    return SummarizeResponse(
        summary    = summary,
        length     = req.length,
        char_count = len(cleaned),
    )


# ── Summarize (SSE streaming) ─────────────────────────────────────────────────
@app.post(
    "/summarize/stream",
    summary="Summarize selected text (streaming)",
    description="Same as POST /summarize but streams tokens via SSE as they are generated.",
    tags=["Summarize"],
)
def summarize_stream(req: SummarizeRequest):
    cleaned = _clean_text(req.text)

    if not cleaned:
        raise HTTPException(status_code=400, detail="Text cannot be empty.")

    allowed_lengths = {"short", "medium", "long", "bullets"}
    if req.length not in allowed_lengths:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid length '{req.length}'. Choose from: {', '.join(allowed_lengths)}.",
        )

    if len(cleaned) > 50_000:
        raise HTTPException(
            status_code=400,
            detail="Text is too long. Maximum 50,000 characters per request.",
        )

    def event_stream():
        try:
            for token in summarize_text_stream(cleaned, length=req.length):
                yield f"data: {token}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"event: error\ndata: {e}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── Session management ────────────────────────────────────────────────────────
@app.get("/session/{session_id}/history")
def get_history(session_id: str):
    return {"session_id": session_id, "history": SESSIONS.get(session_id, [])}


@app.delete("/session/{session_id}")
def clear_session(session_id: str):
    SESSIONS.pop(session_id, None)
    return {"status": "cleared", "session_id": session_id}


# ── Index management ──────────────────────────────────────────────────────────
@app.delete("/clear")
def clear_all():
    reset_stores()
    SESSIONS.clear()
    return {"status": "cleared"}


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {
        "status":    "ok",
        "documents": list_documents(),
        "sessions":  len(SESSIONS),
    }