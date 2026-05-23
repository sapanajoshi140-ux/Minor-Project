import asyncio
import io
import requests
import edge_tts
from sqlalchemy import text, Column, String, Text
from sqlalchemy.orm import declarative_base

from database import SessionLocal, engine as _engine

# ─── Database Setup ────────────────────────────────────────────────────────────

# Reuse the engine and session factory from database.py — creating a second
# engine would open a second connection pool to the same DB, wasting resources.
Base = declarative_base()


class Dictionary(Base):
    __tablename__ = "dictionary"

    word    = Column(String(100), primary_key=True, index=True)
    meaning = Column(Text, nullable=True)
    synonym = Column(Text, nullable=True)
    example = Column(Text, nullable=True)


def init_db():
    """Create the dictionary table and index if they do not exist yet."""
    Base.metadata.create_all(bind=_engine)
    with _engine.connect() as conn:
        result = conn.execute(text("""
            SELECT COUNT(*)
            FROM information_schema.statistics
            WHERE table_schema = DATABASE()
              AND table_name   = 'dictionary'
              AND index_name   = 'idx_dictionary_word'
        """))
        if result.scalar() == 0:
            conn.execute(text(
                "CREATE INDEX idx_dictionary_word ON dictionary (word)"
            ))
        conn.commit()


# ═══════════════════════════════════════════════════════════════════════════════
# MEANING FUNCTIONS  (DB + API — no audio)
# ═══════════════════════════════════════════════════════════════════════════════

def _fetch_from_api(word: str) -> dict:
    """
    Fetch meaning, synonym, and example from the free dictionary API.
    Returns empty strings on failure — never raises.
    """
    url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code != 200:
            return {"meaning": "", "synonym": "", "example": ""}

        entry    = response.json()[0]
        meanings = entry.get("meanings", [])

        meaning_text = ""
        synonym_text = ""
        example_text = ""

        for m in meanings:
            definitions = m.get("definitions", [])
            if definitions:
                defn = definitions[0]
                if not meaning_text:
                    meaning_text = defn.get("definition", "")
                if not example_text:
                    example_text = defn.get("example", "")

            syns = m.get("synonyms", [])
            if not syns and definitions:
                syns = definitions[0].get("synonyms", [])
            if syns and not synonym_text:
                synonym_text = ", ".join(syns[:5])

        return {
            "meaning": meaning_text,
            "synonym": synonym_text,
            "example": example_text,
        }

    except Exception:
        return {"meaning": "", "synonym": "", "example": ""}


def get_meaning(word: str) -> dict:
    """
    Look up a word:
      1. Search the MySQL `dictionary` table (indexed on `word`).
      2. If not found, fetch from the API, persist it, then return it.

    Returns: { word, meaning, synonym?, example?, source }
    synonym and example are only present in the dict when they have a value.
    No audio — pronunciation is handled separately.
    """
    word = word.lower().strip()

    session = SessionLocal()
    try:
        row = session.get(Dictionary, word)

        if row:
            result = {
                "word":    row.word,
                "meaning": row.meaning or "Meaning not found.",
                "source":  "Database",
            }
            if row.synonym:
                result["synonym"] = row.synonym
            if row.example:
                result["example"] = row.example
            return result

        api_data = _fetch_from_api(word)

        if api_data["meaning"]:
            session.add(Dictionary(
                word    = word,
                meaning = api_data["meaning"],
                synonym = api_data["synonym"] or None,
                example = api_data["example"] or None,
            ))
            session.commit()

            result = {
                "word":    word,
                "meaning": api_data["meaning"],
                "source":  "API (Learned Word)",
            }
            if api_data["synonym"]:
                result["synonym"] = api_data["synonym"]
            if api_data["example"]:
                result["example"] = api_data["example"]
            return result

        return {
            "word":    word,
            "meaning": "Meaning not found.",
            "source":  "Error",
        }
    finally:
        session.close()


# ═══════════════════════════════════════════════════════════════════════════════
# VOCABULARY LOGGING  (dashboard — Your Vocabulary panel)
# ═══════════════════════════════════════════════════════════════════════════════

def log_vocabulary_lookup(
    user_id: int,
    word: str,
    document_id: str | None = None,
    db_session=None,
) -> None:
    """
    Record that `user_id` looked up `word`, optionally while reading
    `document_id`.  Inserts a row into `user_vocabulary`.

    Called from the /dictionary/{word}/meaning endpoint in main.py.
    A new lookup row is always inserted — repeated lookups of the same word
    are intentional (they reflect genuine learning activity).

    Parameters
    ----------
    user_id     : authenticated user's integer ID.
    word        : lowercase word that was looked up.
    document_id : UUID of the document the user was reading (may be None).
    db_session  : an open SQLAlchemy Session from FastAPI's Depends(get_db).
                  If None, a fresh session is opened and closed internally.

    Never raises — logging failures must not break the dictionary endpoint.
    """
    from datetime import datetime

    try:
        # Import here to avoid circular imports at module load time.
        from database import UserVocabulary

        def _insert(session):
            session.add(UserVocabulary(
                user_id     = user_id,
                word        = word.lower().strip(),
                document_id = document_id or None,
                looked_up_at = datetime.utcnow(),
            ))
            session.commit()

        if db_session is not None:
            _insert(db_session)
        else:
            session = SessionLocal()
            try:
                _insert(session)
            finally:
                session.close()

    except Exception as exc:
        # Swallow silently — vocabulary logging is non-critical.
        import logging
        logging.getLogger(__name__).warning(
            f"Vocabulary log failed for user={user_id} word='{word}': {exc}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# PRONUNCIATION FUNCTIONS  (Edge TTS — neural voices, free, no API key)
# ═══════════════════════════════════════════════════════════════════════════════

TTS_VOICE = "en-US-JennyNeural"


async def _edge_tts_to_buffer(text_to_speak: str) -> io.BytesIO:
    """
    Async helper — generates audio via Edge TTS and returns an in-memory MP3 buffer.
    """
    communicate = edge_tts.Communicate(text_to_speak.strip(), voice=TTS_VOICE)
    mp3_buffer  = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            mp3_buffer.write(chunk["data"])
    mp3_buffer.seek(0)
    return mp3_buffer


def get_phonetic(word: str) -> str:
    """
    Fetch the phonetic text (e.g. /həˈloʊ/) for a word from the free dictionary API.
    Returns an empty string if not available — never raises.
    """
    url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word.lower().strip()}"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code != 200:
            return ""

        entry = response.json()[0]

        phonetic = entry.get("phonetic", "")
        if phonetic:
            return phonetic

        for p in entry.get("phonetics", []):
            if p.get("text"):
                return p["text"]

    except Exception:
        pass

    return ""


def get_pronunciation_audio(word: str) -> io.BytesIO:
    """
    Generate pronunciation audio via Edge TTS and return as in-memory MP3 buffer.

    Uses asyncio.run() which starts a fresh event loop — safe to call from a
    sync context (FastAPI threadpool).  Never call this from inside a running
    event loop (e.g. from an async route directly); use
    ``await _edge_tts_to_buffer(word)`` there instead.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        # We're inside a running event loop (e.g. called from an async route).
        # Schedule the coroutine as a task and block via run_until_complete on
        # a new thread-local loop to avoid deadlocking the main loop.
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, _edge_tts_to_buffer(word.strip()))
            return future.result()

    return asyncio.run(_edge_tts_to_buffer(word.strip()))