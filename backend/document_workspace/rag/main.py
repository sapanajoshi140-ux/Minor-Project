"""
main.py
-------
FastAPI RAG service — chat & summarization only.
Document ingestion is handled exclusively by the app's upload pipeline
(app/routes/upload.py → rag/ingest.py).

Run:
    uvicorn main:app --reload

Endpoints:
  POST   /chat                      Q&A over indexed documents (full JSON)
  POST   /chat/stream               Q&A over indexed documents (SSE streaming)
  POST   /summarize                 Summarize arbitrary text (full JSON)
  POST   /summarize/stream          Summarize arbitrary text (SSE streaming)
  GET    /session/{session_id}/history   Retrieve chat history for a session
  DELETE /session/{session_id}           Clear chat history for a session
  GET    /health                    Health check
"""

from __future__ import annotations

import os
import pathlib
import sys
import uuid
from typing import List, Literal, Optional

import re as _re
from dotenv import load_dotenv

load_dotenv()

_HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(_HERE))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from generate import build_context, generate_answer, generate_answer_stream, summarize_text, summarize_text_stream
from retrieve import retrieve, TOP_K, USE_HYBRID

# ── Config from .env ──────────────────────────────────────────────────────────
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title       = "RAG Chat & Summarization API",
    version     = "2.0.0",
    description = (
        "RAG-powered Q&A and summarization service. "
        "Document ingestion is handled by the main app's `/upload` endpoint — "
        "this service only handles chat and summarization."
    ),
)

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
    question: str = Field(
        ...,
        min_length  = 1,
        description = "The question to ask against the indexed documents.",
        examples    = ["What is the main topic of the document?"],
    )
    session_id: Optional[str] = Field(
        default     = None,
        description = (
            "Session ID for multi-turn conversation. "
            "Omit on the first message — the server will generate one and return it. "
            "Pass the returned session_id in all follow-up messages to maintain history."
        ),
        examples    = ["550e8400-e29b-41d4-a716-446655440000"],
    )
    doc_ids: Optional[List[str]] = Field(
        default     = None,
        description = (
            "Restrict retrieval to specific document IDs. "
            "Omit (or pass null) to search across all indexed documents."
        ),
        examples    = [["doc-uuid-1", "doc-uuid-2"]],
    )
    top_k: int = Field(
        default     = TOP_K,
        ge          = 1,
        le          = 20,
        description = "Number of document chunks to retrieve and pass to the LLM as context.",
        examples    = [5],
    )
    use_hybrid: bool = Field(
        default     = USE_HYBRID,
        description = (
            "Enable hybrid retrieval (dense vector search + BM25 keyword search fused via RRF). "
            "Set to false to use dense-only retrieval."
        ),
        examples    = [True],
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "question":   "What are the key findings of the report?",
                "session_id": "550e8400-e29b-41d4-a716-446655440000",
                "doc_ids":    ["your-document-uuid-here"],
                "top_k":      5,
                "use_hybrid": True,
            }
        }
    }


class ChatResponse(BaseModel):
    answer: str = Field(
        description="The LLM-generated answer to the question."
    )
    session_id: str = Field(
        description="Session ID — pass this back in subsequent requests to maintain conversation history."
    )
    citations: List[dict] = Field(
        description=(
            "List of source chunks used to generate the answer. "
            "Each entry contains fields returned by generate_answer — "
            "typically: source_n, doc_id, page, score, text_snippet."
        )
    )
    sources_used: int = Field(
        description="Total number of chunks retrieved and passed to the LLM."
    )


class SummarizeRequest(BaseModel):
    text: str = Field(
        ...,
        min_length  = 1,
        max_length  = 50_000,
        description = "The text to summarize. Maximum 50,000 characters.",
        examples    = ["Paste the document text or selected passage here..."],
    )
    length: Literal["short", "medium", "long", "bullets"] = Field(
        default     = "medium",
        description = (
            "Controls the output length and style:\n"
            "- **short** — 2-3 sentences\n"
            "- **medium** — 1 concise paragraph\n"
            "- **long** — detailed multi-paragraph summary\n"
            "- **bullets** — bullet-point list of key points"
        ),
        examples    = ["medium"],
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "text":   "The quarterly report shows revenue grew by 12% year-over-year...",
                "length": "medium",
            }
        }
    }


class SummarizeResponse(BaseModel):
    summary:    str   = Field(description="The generated summary.")
    length:     str   = Field(description="The length/style used.")
    char_count: int   = Field(description="Character count of the input text.")


class SessionHistoryResponse(BaseModel):
    session_id: str              = Field(description="The session ID.")
    history:    List[dict]       = Field(description="Ordered list of user/assistant turns.")


class HealthResponse(BaseModel):
    status:   str = Field(description="Service status — always 'ok' if reachable.")
    sessions: int = Field(description="Number of active in-memory sessions.")


# ── Chat (JSON) ───────────────────────────────────────────────────────────────
@app.post(
    "/chat",
    response_model = ChatResponse,
    summary        = "Ask a question (full JSON response)",
    description    = (
        "Send a question and get a full JSON response with the answer and citations. "
        "Use `session_id` to maintain multi-turn conversation history. "
        "Use `doc_ids` to restrict retrieval to specific documents."
    ),
    tags           = ["Chat"],
)
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
            status_code = 404,
            detail      = "No indexed documents found. Please upload a document first.",
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
@app.post(
    "/chat/stream",
    summary     = "Ask a question (SSE streaming)",
    description = (
        "Same as POST `/chat` but streams the answer token-by-token via Server-Sent Events (SSE).\n\n"
        "**SSE event format:**\n"
        "- First event: `event: meta` — JSON with `session_id` and `citations`\n"
        "- Subsequent events: `data: <token>` — answer tokens as they are generated\n"
        "- Final event: `data: [DONE]` — signals end of stream"
    ),
    tags        = ["Chat"],
)
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
    response_model = SummarizeResponse,
    summary        = "Summarize text (full JSON response)",
    description    = (
        "Pass any text (e.g. a copied passage from a document) and receive a concise summary. "
        "Use the `length` field to control output style."
    ),
    tags           = ["Summarize"],
)
def summarize(req: SummarizeRequest):
    cleaned = _clean_text(req.text)
    if not cleaned:
        raise HTTPException(status_code=400, detail="Text cannot be empty.")

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
    summary     = "Summarize text (SSE streaming)",
    description = (
        "Same as POST `/summarize` but streams the summary token-by-token via SSE.\n\n"
        "**SSE event format:**\n"
        "- `data: <token>` — summary tokens as they are generated\n"
        "- `data: [DONE]` — signals end of stream\n"
        "- `event: error` — emitted if summarization fails mid-stream"
    ),
    tags        = ["Summarize"],
)
def summarize_stream(req: SummarizeRequest):
    cleaned = _clean_text(req.text)
    if not cleaned:
        raise HTTPException(status_code=400, detail="Text cannot be empty.")

    def event_stream():
        try:
            for token in summarize_text_stream(cleaned, length=req.length):
                yield f"data: {token}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"event: error\ndata: {e}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── Session management ────────────────────────────────────────────────────────
@app.get(
    "/session/{session_id}/history",
    response_model = SessionHistoryResponse,
    summary        = "Get conversation history",
    description    = "Retrieve the full ordered chat history for a given session ID.",
    tags           = ["Session"],
)
def get_history(session_id: str):
    return SessionHistoryResponse(
        session_id = session_id,
        history    = SESSIONS.get(session_id, []),
    )


@app.delete(
    "/session/{session_id}",
    summary     = "Clear conversation history",
    description = "Delete all chat history for the given session. The session ID can be reused afterwards.",
    tags        = ["Session"],
)
def clear_session(session_id: str):
    SESSIONS.pop(session_id, None)
    return {"status": "cleared", "session_id": session_id}


# ── Health ────────────────────────────────────────────────────────────────────
@app.get(
    "/health",
    response_model = HealthResponse,
    summary        = "Health check",
    description    = "Returns service status and the number of active in-memory sessions.",
    tags           = ["Health"],
)
def health():
    return HealthResponse(
        status   = "ok",
        sessions = len(SESSIONS),
    )