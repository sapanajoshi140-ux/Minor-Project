import asyncio
import os
import io
import requests
import edge_tts
from dotenv import load_dotenv
from sqlalchemy import create_engine, text, Column, String, Text
from sqlalchemy.orm import declarative_base, Session

load_dotenv()

# ─── Database Setup ────────────────────────────────────────────────────────────

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
Base = declarative_base()


class Dictionary(Base):
    __tablename__ = "dictionary"

    word    = Column(String(100), primary_key=True, index=True)
    meaning = Column(Text, nullable=True)
    synonym = Column(Text, nullable=True)
    example = Column(Text, nullable=True)


def init_db():
    """Create the dictionary table and index if they do not exist yet."""
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
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

    with Session(engine) as session:
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


# ═══════════════════════════════════════════════════════════════════════════════
# PRONUNCIATION FUNCTIONS  (Edge TTS — neural voices, free, no API key)
# ═══════════════════════════════════════════════════════════════════════════════

# Change voice here if you want a different one:
#   en-US-JennyNeural      — natural female (US)
#   en-US-GuyNeural        — natural male   (US)
#   en-GB-SoniaNeural      — natural female (British)
#   en-GB-RyanNeural       — natural male   (British)
TTS_VOICE = os.getenv("TTS_VOICE", "en-US-JennyNeural")


async def _edge_tts_to_buffer(text_to_speak: str) -> io.BytesIO:
    """
    Async helper — generates audio via Edge TTS and returns an in-memory MP3 buffer.
    No file saved to disk, no API key needed.
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
    Fetch the phonetic text (e.g. /həˈloʊ/) for a word
    from the free dictionary API.
    Returns an empty string if not available — never raises.
    No database interaction.
    """
    url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word.lower().strip()}"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code != 200:
            return ""

        entry = response.json()[0]

        # Top-level phonetic field (most common)
        phonetic = entry.get("phonetic", "")
        if phonetic:
            return phonetic

        # Fallback: first phonetic object with text
        for p in entry.get("phonetics", []):
            if p.get("text"):
                return p["text"]

    except Exception:
        pass

    return ""


def get_pronunciation_audio(word: str) -> io.BytesIO:
    """
    Generate pronunciation audio via Edge TTS and return as in-memory MP3 buffer.
    No database interaction, no file saved, no API key needed.

    Usage in endpoint:
        audio = get_pronunciation_audio(word)
        return StreamingResponse(audio, media_type="audio/mpeg")
    """
    return asyncio.run(_edge_tts_to_buffer(word.strip()))