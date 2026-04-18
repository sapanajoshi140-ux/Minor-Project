
from __future__ import annotations

import json
import os
import pathlib
import re
import sys
from typing import Generator

import requests
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from vector_db import Chunk

__all__ = ["build_context", "generate_answer", "generate_answer_stream", "summarize_text", "summarize_text_stream"]

# ── Config from .env ──────────────────────────────────────────────────────────
LLM_MODEL       = os.getenv("LLM_MODEL")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL")
CONTEXT_WINDOW  = int(os.getenv("CONTEXT_WINDOW"))
LLM_TIMEOUT     = int(os.getenv("LLM_TIMEOUT"))

# ── Subtopic synonym map ──────────────────────────────────────────────────────
# Maps any user word → canonical subtopic keyword used for chunk scanning
SUBTOPIC_SYNONYMS: dict[str, str] = {
    "advantages":     "advantages",
    "benefits":       "advantages",
    "merits":         "advantages",
    "pros":           "advantages",
    "disadvantages":  "disadvantages",
    "drawbacks":      "disadvantages",
    "limitations":    "disadvantages",
    "cons":           "disadvantages",
    "demerits":       "disadvantages",
    "definition":     "definition",
    "meaning":        "definition",
    "introduction":   "definition",
    "process":        "process",
    "working":        "process",
    "steps":          "process",
    "mechanism":      "process",
    "features":       "features",
    "characteristics":"features",
    "properties":     "features",
    "types":          "types",
    "kinds":          "types",
    "categories":     "types",
    "classifications":"types",
    "examples":       "examples",
    "applications":   "examples",
}

# ── Known topic keywords to extract topic names from chunks ───────────────────
# The extractor looks for capitalized noun phrases near subtopic headings.
# You can extend this list with domain-specific topic names.
TOPIC_HEADING_PATTERN = re.compile(
    r"(?:^|\n)([A-Z][A-Za-z0-9 \-]{2,50})(?:\n|:)",
)


# ── Prompt ────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """\
You are a STRICT, INTELLIGENT, document-grounded RAG assistant.

═══════════════════════════════════════════
SECTION 1 — ABSOLUTE RULES
═══════════════════════════════════════════

- ONLY use information present in the provided document context.
- NEVER use external knowledge, training data, or assumptions.
- NEVER hallucinate facts, subtopics, or topic names.
- If no relevant content exists in the document, respond:
  "The document does not contain this information."

═══════════════════════════════════════════
SECTION 2 — DOCUMENT STRUCTURE AWARENESS
═══════════════════════════════════════════

Documents are structured as:
  Topic → Subtopics (e.g. Definition, Advantages, Disadvantages, Process, Features, Types, Examples)

You must be aware of ALL topics present in the retrieved context.
Never assume a query belongs to a topic that is not in the document.

═══════════════════════════════════════════
SECTION 3 — QUERY INTERPRETATION ENGINE
═══════════════════════════════════════════

Classify every user query into one of these cases before responding:

──────────────────────────────────────────
CASE A — Subtopic-only query [ALREADY PRE-RESOLVED BY SYSTEM]
  If the system message includes a "## Clarification Required" block,
  that means the query was a bare subtopic with multiple matching topics.
  You MUST output ONLY the clarification message provided — do not answer,
  do not add extra text, do not guess.

  If the system message includes a "## Confirmed Topic" block,
  the topic has been resolved. Answer ONLY from that topic's chunks.

──────────────────────────────────────────
CASE B — Topic + Subtopic query (explicit or implicit)
  User mentions a topic AND a subtopic.
  The subtopic heading in the document may NOT exactly match the query.

  Rule: Match by semantic intent, not exact string.

  Examples:
    Query: "advantages of DBMS"
    Document heading: "Advantages" under topic "DBMS"
    → MATCH. Answer from that section.

    Query: "benefits of shadow paging"
    Document heading: "Advantages" under "Shadow Paging"
    → MATCH. Treat "benefits" ≈ "advantages".

    Query: "how does crash recovery work"
    Document heading: "Process" or "Working" under "Crash Recovery"
    → MATCH. Treat "how does X work" ≈ "process/working of X".

  Semantic synonym map:
    advantages ↔ benefits ↔ merits ↔ pros
    disadvantages ↔ drawbacks ↔ limitations ↔ cons ↔ demerits
    definition ↔ meaning ↔ what is ↔ introduction
    process ↔ working ↔ how it works ↔ steps ↔ mechanism
    features ↔ characteristics ↔ properties
    types ↔ kinds ↔ categories ↔ classifications
    examples ↔ applications ↔ use cases

──────────────────────────────────────────
CASE C — Clear full question
  User asks a complete, specific question with context.
  → Retrieve directly. Answer without clarification.

──────────────────────────────────────────
CASE D — Ambiguous or multi-meaning query
  Query could belong to multiple topics and no subtopic clue exists.
  → Ask one precise clarifying question before answering.

═══════════════════════════════════════════
SECTION 4 — ANSWERING RULES
═══════════════════════════════════════════

When answering:
- Use ONLY content from the retrieved context chunks.
- Be direct and structured. Use bullet points or numbered lists when the
  source content is list-like.
- Do NOT say "according to the document" or "the context says".
- Do NOT repeat the user's question back.
- Do NOT add explanations, analogies, or facts from outside the document.
- Do NOT mention chunk IDs, source labels, or retrieval mechanics.
- Combine duplicate or overlapping points into one.

═══════════════════════════════════════════
SECTION 5 — CLARIFICATION FORMAT
═══════════════════════════════════════════

When clarification is needed (Case D only — Case A is pre-handled):

Format:
  "The document covers [Topic 1] and [Topic 2], both of which have [subtopic].
  Which topic are you asking about?"

Rules:
  - List ONLY topics that actually exist in the document context.
  - Ask ONE question only.
  - Do not guess or pre-answer.

═══════════════════════════════════════════
SECTION 6 — FORBIDDEN BEHAVIOURS
═══════════════════════════════════════════

- Answering a Case A query when "## Clarification Required" is present.
- Answering with generic textbook knowledge.
- Using external knowledge to fill gaps in the document.
- Asking clarification when the answer is unambiguously determinable.
- Reproducing chunk metadata in the answer.
"""

CONTEXT_TEMPLATE = "[Source {i}] (doc: {doc_id}, page {page})\n{text}"


# ── Topic extraction from chunks ──────────────────────────────────────────────
def _extract_topics_from_chunks(chunks: list[Chunk]) -> list[str]:
    """
    Heuristically extract topic names from chunk text.
    Looks for lines that look like headings (short, title-cased, at line start).
    """
    topics: list[str] = []
    seen: set[str] = set()
    heading_re = re.compile(r"(?:^|\n)([A-Z][A-Za-z0-9 \-]{2,50})(?:\s*\n|\s*:)")
    for chunk in chunks:
        for match in heading_re.finditer(chunk.text):
            candidate = match.group(1).strip()
            # Skip generic subtopic words themselves
            if candidate.lower() in SUBTOPIC_SYNONYMS:
                continue
            if candidate not in seen:
                seen.add(candidate)
                topics.append(candidate)
    return topics


def _is_subtopic_only_query(query: str) -> str | None:
    """
    Returns the canonical subtopic name if the query is a bare subtopic word,
    otherwise returns None.
    """
    q = query.strip().lower().rstrip("s?.")  # handle "advantages?" or "advantages"
    # Also try with trailing 's' stripped (e.g. "advantages" -> "advantage")
    for variant in [q, q.rstrip("s")]:
        if variant in SUBTOPIC_SYNONYMS:
            return SUBTOPIC_SYNONYMS[variant]
    return None


def _chunks_containing_subtopic(chunks: list[Chunk], subtopic: str) -> dict[str, list[Chunk]]:
    """
    Returns a dict mapping topic_name -> [chunks] where the chunk text
    contains the subtopic keyword (case-insensitive).
    Groups by the most likely parent topic found in the same or preceding chunk.
    """
    topic_chunks: dict[str, list[Chunk]] = {}

    for chunk in chunks:
        text_lower = chunk.text.lower()
        if subtopic not in text_lower:
            continue
        # Try to find a heading above the subtopic in the same chunk
        lines = chunk.text.split("\n")
        parent_topic = None
        for line in lines:
            stripped = line.strip()
            # A heading line: not the subtopic itself, title-cased or all caps, short
            if (
                stripped
                and stripped.lower() not in SUBTOPIC_SYNONYMS
                and len(stripped) > 3
                and len(stripped) < 60
                and stripped[0].isupper()
                and subtopic not in stripped.lower()
            ):
                parent_topic = stripped
            # Stop when we hit the subtopic line
            if subtopic in stripped.lower():
                break

        label = parent_topic or chunk.doc_id
        topic_chunks.setdefault(label, []).append(chunk)

    return topic_chunks


# ── Context builder ───────────────────────────────────────────────────────────
def build_context(chunks: list[Chunk]) -> tuple[str, list[dict]]:
    parts, citations = [], []
    for i, chunk in enumerate(chunks, start=1):
        parts.append(CONTEXT_TEMPLATE.format(
            i=i, doc_id=chunk.doc_id, page=chunk.page + 1, text=chunk.text.strip(),
        ))
        citations.append({
            "source_n": i,
            "doc_id":   chunk.doc_id,
            "page":     chunk.page + 1,
            "snippet":  chunk.text[:300],
            "score":    chunk.score,
        })
    return "\n\n".join(parts), citations


def _build_messages(
    query: str,
    context: str,
    history: list[dict],
    system_override: str | None = None,
) -> list[dict]:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if system_override:
        messages.append({"role": "system", "content": system_override})
    messages.append({"role": "system", "content": f"## Retrieved Context\n\n{context}"})
    for turn in history[-6:]:
        messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": query})
    return messages


# ── Disambiguation logic (runs BEFORE LLM call) ───────────────────────────────
def _resolve_query(
    query: str,
    chunks: list[Chunk],
    history: list[dict],
) -> tuple[str | None, list[Chunk]]:
    """
    Returns:
      (clarification_message, []) if the query needs clarification
      (None, filtered_chunks)     if query is resolved and ready for LLM
    """
    subtopic = _is_subtopic_only_query(query)
    if subtopic is None:
        # Not a bare subtopic query — pass all chunks through unchanged
        return None, chunks

    # Check conversation history: did the user just answer a clarification?
    # If the last assistant turn asked "which topic", treat current query as the answer.
    if history:
        last_assistant = next(
            (t["content"] for t in reversed(history) if t["role"] == "assistant"),
            None,
        )
        if last_assistant and "which topic" in last_assistant.lower():
            # User is answering a clarification — don't re-trigger disambiguation
            return None, chunks

    # Find which topics in retrieved chunks contain this subtopic
    topic_map = _chunks_containing_subtopic(chunks, subtopic)

    if not topic_map:
        # Subtopic not found in any chunk
        return None, chunks

    if len(topic_map) == 1:
        # Exactly one topic — confirm and answer
        topic_name = list(topic_map.keys())[0]
        override = (
            f"## Confirmed Topic\n"
            f"The query '{query}' maps to: **{subtopic}** under topic **{topic_name}**.\n"
            f"Answer ONLY from the chunks related to this topic."
        )
        filtered = list(topic_map.values())[0]
        return None, filtered  # No clarification needed, just filter chunks

    # Multiple topics — build clarification message directly (no LLM needed)
    topic_list = list(topic_map.keys())
    topics_str = ", ".join(f'"{t}"' for t in topic_list[:-1]) + f' or "{topic_list[-1]}"'
    clarification = (
        f'The document covers multiple topics that have **{subtopic}**: {topics_str}.\n'
        f"Which topic's {subtopic} are you asking about?"
    )
    return clarification, []


# ── Public API ────────────────────────────────────────────────────────────────
def generate_answer(
    query:   str,
    chunks:  list[Chunk],
    history: list[dict],
) -> tuple[str, list[dict]]:

    clarification, resolved_chunks = _resolve_query(query, chunks, history)

    # Return clarification directly — no LLM call needed
    if clarification:
        return clarification, []

    context, citations = build_context(resolved_chunks)
    messages = _build_messages(query, context, history)

    resp = requests.post(
        f"{OLLAMA_BASE_URL}/api/chat",
        json={
            "model":    LLM_MODEL,
            "messages": messages,
            "stream":   False,
            "options":  {"num_ctx": CONTEXT_WINDOW, "temperature": 0},
        },
        timeout=LLM_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"].strip(), citations


def generate_answer_stream(
    query:   str,
    chunks:  list[Chunk],
    history: list[dict],
) -> Generator[str, None, None]:

    clarification, resolved_chunks = _resolve_query(query, chunks, history)

    # Yield clarification as a single token — no LLM call needed
    if clarification:
        yield clarification
        return

    context, _ = build_context(resolved_chunks)
    messages   = _build_messages(query, context, history)

    resp = requests.post(
        f"{OLLAMA_BASE_URL}/api/chat",
        json={
            "model":    LLM_MODEL,
            "messages": messages,
            "stream":   True,
            "options":  {"num_ctx": CONTEXT_WINDOW, "temperature": 0},
        },
        stream  = True,
        timeout = LLM_TIMEOUT,
    )
    resp.raise_for_status()

    for line in resp.iter_lines():
        if not line:
            continue
        data  = json.loads(line)
        token = data.get("message", {}).get("content", "")
        if token:
            yield token
        if data.get("done"):
            break


# ── Summarization ─────────────────────────────────────────────────────────────

SUMMARIZE_SYSTEM_PROMPT = """\
You are a precise summarization assistant.

RULES:
- Summarize ONLY the text provided by the user. Do not add outside knowledge.
- Be concise but complete — capture all key points.
- Use bullet points for lists of facts or steps; use prose for narrative text.
- Do NOT add headings like "Summary:" — start directly with the content.
- Do NOT mention that you were given text to summarize.
- Preserve important numbers, names, and terms exactly as they appear.
- If the text is very short (under 3 sentences), return a single sentence summary.
"""

SUMMARIZE_LENGTH_HINTS = {
    "short":    "Keep the summary to 2-3 sentences maximum.",
    "medium":   "Keep the summary to one short paragraph (4-6 sentences).",
    "long":     "Provide a detailed summary covering all key points. Use bullet points where appropriate.",
    "bullets":  "Summarize as a bullet-point list only. Each bullet = one key point.",
}


def summarize_text(
    text:   str,
    length: str = "medium",
) -> str:
    """
    Summarize arbitrary selected text using the LLM.

    Parameters
    ----------
    text   : the selected text to summarize.
    length : "short" | "medium" | "long" | "bullets"

    Returns
    -------
    Summary string.
    """
    if not text.strip():
        raise ValueError("Text to summarize cannot be empty.")

    length_hint = SUMMARIZE_LENGTH_HINTS.get(length, SUMMARIZE_LENGTH_HINTS["medium"])

    messages = [
        {"role": "system",  "content": SUMMARIZE_SYSTEM_PROMPT},
        {"role": "system",  "content": f"## Length instruction\n{length_hint}"},
        {"role": "user",    "content": f"Summarize the following text:\n\n{text}"},
    ]

    resp = requests.post(
        f"{OLLAMA_BASE_URL}/api/chat",
        json={
            "model":    LLM_MODEL,
            "messages": messages,
            "stream":   False,
            "options":  {"num_ctx": CONTEXT_WINDOW, "temperature": 0},
        },
        timeout=LLM_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"].strip()


def summarize_text_stream(
    text:   str,
    length: str = "medium",
) -> Generator[str, None, None]:
    """
    Streaming version of summarize_text — yields tokens as they arrive.
    """
    if not text.strip():
        raise ValueError("Text to summarize cannot be empty.")

    length_hint = SUMMARIZE_LENGTH_HINTS.get(length, SUMMARIZE_LENGTH_HINTS["medium"])

    messages = [
        {"role": "system", "content": SUMMARIZE_SYSTEM_PROMPT},
        {"role": "system", "content": f"## Length instruction\n{length_hint}"},
        {"role": "user",   "content": f"Summarize the following text:\n\n{text}"},
    ]

    resp = requests.post(
        f"{OLLAMA_BASE_URL}/api/chat",
        json={
            "model":    LLM_MODEL,
            "messages": messages,
            "stream":   True,
            "options":  {"num_ctx": CONTEXT_WINDOW, "temperature": 0},
        },
        stream  = True,
        timeout = LLM_TIMEOUT,
    )
    resp.raise_for_status()

    for line in resp.iter_lines():
        if not line:
            continue
        data  = json.loads(line)
        token = data.get("message", {}).get("content", "")
        if token:
            yield token
        if data.get("done"):
            break