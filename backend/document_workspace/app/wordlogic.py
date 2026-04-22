import os
import requests
import io
import pygame
from gtts import gTTS
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

    Returns: { word, meaning, synonym, example, source }
    No audio — pronunciation is handled separately.
    """
    word = word.lower().strip()

    with Session(engine) as session:
        row = session.get(Dictionary, word)

        if row:
            return {
                "word":    row.word,
                "meaning": row.meaning or "Meaning not found.",
                "synonym": row.synonym or "",
                "example": row.example or "",
                "source":  "Database",
            }

        api_data = _fetch_from_api(word)

        if api_data["meaning"]:
            session.add(Dictionary(
                word    = word,
                meaning = api_data["meaning"],
                synonym = api_data["synonym"],
                example = api_data["example"],
            ))
            session.commit()

            return {
                "word":    word,
                "meaning": api_data["meaning"],
                "synonym": api_data["synonym"],
                "example": api_data["example"],
                "source":  "API (Learned Word)",
            }

        return {
            "word":    word,
            "meaning": "Meaning not found.",
            "synonym": "",
            "example": "",
            "source":  "Error",
        }


# ═══════════════════════════════════════════════════════════════════════════════
# PRONUNCIATION FUNCTIONS  (audio only — no DB interaction)
# ═══════════════════════════════════════════════════════════════════════════════

def _speak(text_to_speak: str) -> None:
    """
    Internal helper — generates audio via gTTS and plays it in memory.
    Works for both single words and full paragraphs.
    No file is saved to disk.
    """
    tts = gTTS(text=text_to_speak, lang="en")

    mp3_buffer = io.BytesIO()
    tts.write_to_fp(mp3_buffer)
    mp3_buffer.seek(0)

    pygame.mixer.init()
    pygame.mixer.music.load(mp3_buffer, "mp3")
    pygame.mixer.music.play()

    while pygame.mixer.music.get_busy():
        pygame.time.Clock().tick(10)

    pygame.mixer.quit()


def pronounce_word(word: str) -> None:
    """
    Speak a single word aloud.
    No database interaction whatsoever.
    """
    _speak(word.strip())


def pronounce_paragraph(text: str) -> None:
    """
    Speak a full paragraph or any length of text aloud.
    No database interaction whatsoever.
    """
    _speak(text.strip())


