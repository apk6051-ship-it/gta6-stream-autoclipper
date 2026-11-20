"""
AI Metadata Generator using Google Gemini
Generates viral, unique, high-CTR YouTube Shorts titles, descriptions, and tags.
Replaces generic "insane moments" titles with tailored, context-aware metadata.
"""

import os
import json
import re
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def generate_shorts_metadata(
    video_title: str,
    channel_name: str,
    gemini_api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generates YouTube Shorts metadata using Gemini API (or algorithmic fallback if no key).
    """
    api_key = gemini_api_key or os.environ.get("GEMINI_API_KEY")

    if api_key:
        try:
            import requests

            prompt = f"""You are a top-tier viral YouTube Shorts producer for GTA 6 and gaming content.
I have clipped the most replayed viral highlight from this GTA video/stream:
- Channel / Streamer: {channel_name}
- Original Stream Title: {video_title}

Generate metadata for a viral YouTube Short:
1. Title: Catchy, curiosity-inducing, punchy title under 60 characters with 1-2 relevant emojis and '#Shorts'.
   CRITICAL: DO NOT use generic phrases like 'Insane moments', 'Epic moments', or 'Best moment'.
   Make it feel natural, funny, or shocking based on the streamer or game context (e.g., 'Kai Cenat did NOT expect this in GTA 6 💀 #Shorts' or 'Bro found a secret car already?! 🏎️ #Shorts').
2. Description: 2-3 engaging lines encouraging viewers to like and subscribe, with 4-5 hashtags (#GTA6, #Shorts, #Gaming, #{channel_name.replace(' ', '')}).
3. Tags: 6-8 comma-separated search tags (e.g., GTA 6, GTA 6 clips, {channel_name}, Grand Theft Auto 6, GTA 6 gameplay).

Return ONLY valid JSON matching this schema:
{{
  "title": "Your Title Here #Shorts",
  "description": "Your Description Here",
  "tags": ["tag1", "tag2", "tag3"]
}}"""

            for model_name in ["gemini-1.5-flash", "gemini-2.0-flash"]:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"response_mime_type": "application/json"}
                }

                resp = requests.post(url, json=payload, timeout=20)
                if resp.status_code == 200:
                    data = resp.json()
                    text = data["candidates"][0]["content"]["parts"][0]["text"]
                    metadata = json.loads(text)
                    logger.info(f"✨ Gemini ({model_name}) Generated Title: {metadata.get('title')}")
                    return metadata
                else:
                    logger.warning(f"Gemini API ({model_name}) returned status {resp.status_code}: {resp.text[:150]}")
        except Exception as e:
            logger.warning(f"Gemini metadata generation failed: {e}. Using smart fallback.")

    # Smart fallback if Gemini API key is missing or failed
    clean_title = re.sub(r"[#|🔴\[\]!]", "", video_title).strip()
    words = clean_title.split()[:5]
    hook = " ".join(words) if words else "GTA 6 Gameplay"

    fallback_title = f"{channel_name} in GTA 6: {hook} 💀 #Shorts"
    if len(fallback_title) > 90:
        fallback_title = f"{hook} in GTA 6 😱 #Shorts"

    return {
        "title": fallback_title,
        "description": f"Best moment from {channel_name}'s GTA stream!\n\nSubscribe for daily GTA 6 clips & highlights.\n\n#GTA6 #GrandTheftAuto6 #Shorts #Gaming #{channel_name.replace(' ', '')}",
        "tags": ["GTA 6", "Grand Theft Auto VI", "Shorts", "Gaming", channel_name, "GTA 6 Gameplay"],
    }
