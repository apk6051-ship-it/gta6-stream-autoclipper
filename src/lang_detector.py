"""
Language Detection & Verification Utility
Ensures all selected videos and audio are English.
Filters out Spanish, Russian, German, Hindi, Japanese, and other non-English content.
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
    "le jeu", "est là", "spielt", "aus", "mit", "und", "der", "die", "das"
]


def is_english_content(title: str, description: str = "", metadata: Dict[str, Any] = None) -> bool:
    """
    Validates that a video is in English:
    1. Checks explicit audio/subtitles language metadata from YouTube.
    2. Checks for foreign keywords in title.
    3. Checks for non-Latin script (Cyrillic, Devanagari, East Asian, Arabic).
    4. Runs langdetect text analysis.
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
    # Range covers Cyrillic, Devanagari, CJK, Arabic
    non_latin_chars = len(re.findall(r"[\u0400-\u04FF\u0900-\u097F\u4E00-\u9FFF\u3040-\u30FF\u0600-\u06FF]", title))
    if non_latin_chars > 2:
        logger.info(f"Filtered out video (detected non-Latin script in title: {title})")
        return False

    # 4. Use langdetect if available
    try:
        from langdetect import detect
        clean_text = re.sub(r"[#|🔴\[\]!_0-9]", " ", title + " " + description[:100]).strip()
        if len(clean_text) >= 15:
            lang = detect(clean_text)
            if lang != "en":
                logger.info(f"Filtered out video (langdetect detected '{lang}' for title: '{title}')")
                return False
    except Exception:
        pass

    return True
