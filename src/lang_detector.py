"""
Language Detection & Verification Utility
Ensures all selected videos and audio are English.
Filters out Spanish, Russian, German, Portuguese, Hindi, Japanese, and other non-English content.
"""

import re
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

NON_ENGLISH_KEYWORDS = [
    "español", "espanol", "русский", "deutsch", "francais", "français",
    "italiano", "portugues", "português", "hindi", "tamil", "telugu",
    "vídeo", "completo", "capítulo", "capitulo", "jugando", "día", "dia",
    "estuve", "aquí", "aqui", "directo", "primer", "primera", "juego",
    "le jeu", "est là", "spielt", "aus", "mit", "und", "der", "die", "das",
    "en vivo", "ao vivo", "versão", "stunden", "alles", "tage", "heures",
    "hombres", "sin camisa", "hoy", "vamos", "con", "amaldiçoada"
]

COMMON_ENGLISH_WORDS = {
    "the", "in", "of", "to", "and", "a", "is", "for", "first", "time",
    "with", "day", "on", "i", "im", "we", "at", "my", "this", "all",
    "playing", "giving", "away", "codes", "new", "drops", "exclusive",
    "gta", "game", "playthrough", "live", "story", "mode", "out", "by",
    "what", "how", "get", "got", "can", "do", "no", "yes", "me", "he",
    "she", "you", "your", "bro", "losing", "mind", "night", "club",
    "super", "cars", "free", "edition", "zealand", "worth", "stream",
    "marathon", "part", "gameplay", "full", "walkthrough", "finishing",
    "continuing", "rolling", "screaming", "boys", "best"
}


def is_english_content(title: str, description: str = "", metadata: Dict[str, Any] = None) -> bool:
    """
    Validates that a video is in English:
    1. Checks explicit audio/subtitles language metadata.
    2. Checks for foreign keywords in title.
    3. Checks for non-Latin script (Cyrillic, Devanagari, East Asian, Arabic).
    4. Matches against common English vocabulary.
    5. Falls back to langdetect for longer text.
    """
    metadata = metadata or {}

    # 1. Check explicit audio metadata if present
    audio_lang = metadata.get("audio_language") or metadata.get("language")
    if audio_lang and not audio_lang.lower().startswith("en"):
        logger.info(f"Filtered out video (non-English audio metadata: {audio_lang})")
        return False

    title_lower = title.lower()

    # 2. Check for explicit foreign keywords
    for kw in NON_ENGLISH_KEYWORDS:
        if kw in title_lower:
            logger.info(f"Filtered out video (detected foreign keyword '{kw}' in title)")
            return False

    # 3. Check for non-Latin scripts (Cyrillic, Hindi, Chinese/Japanese, Arabic)
    non_latin_chars = len(re.findall(r"[\u0400-\u04FF\u0900-\u097F\u4E00-\u9FFF\u3040-\u30FF\u0600-\u06FF]", title))
    if non_latin_chars > 2:
        logger.info(f"Filtered out video (detected non-Latin script in title: {title})")
        return False

    # 4. Check if title contains common English vocabulary
    words = set(re.findall(r"[a-zA-Z]+", title_lower))
    eng_matches = words.intersection(COMMON_ENGLISH_WORDS)
    if len(eng_matches) >= 2:
        return True

    # 5. Fallback to langdetect if text is sufficiently long
    try:
        from langdetect import detect
        clean_text = re.sub(r"[#|🔴\[\]!_0-9]", " ", title + " " + description[:100]).strip()
        if len(clean_text) >= 20:
            lang = detect(clean_text)
            if lang != "en":
                logger.info(f"Filtered out video (langdetect detected '{lang}' for title: '{title}')")
                return False
    except Exception:
        pass

    return True
