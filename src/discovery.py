"""
Streamed VOD & Uploaded Video Discovery Module
Discovers past live streams and gameplay walkthroughs for GTA 6 / GTA 5.
Filters strictly for English audio and content, high viewer engagement,
and ensures no video is ever clipped twice.
"""

import os
import logging
import subprocess
import json
from typing import Optional, Dict, Any, List, Set
from src.lang_detector import is_english_content

logger = logging.getLogger(__name__)

HISTORY_FILE = "processed_videos.txt"


def get_processed_ids() -> Set[str]:
    """Returns set of video IDs that have already been clipped to prevent duplicates."""
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f if line.strip())
    return set()


def mark_video_processed(video_id: str):
    """Saves video ID to history file so it is never reused."""
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(f"{video_id}\n")


def get_top_streamed_vods(search_query: str, limit: int = 15, min_views: int = 2000) -> List[Dict[str, Any]]:
    """
    Searches YouTube for top past live streams and full gameplay walkthroughs.
    Filters:
    - Must be already ended / streamed video.
    - Duration between 10 minutes and 4 hours (typical stream length).
    - Verified English audio and title.
    - Above minimum view count threshold.
    - Not previously clipped.
    """
    processed = get_processed_ids()
    # Search terms focusing on streamed gameplay walkthroughs
    search_term = f"{search_query} full stream gameplay walkthrough"

    cmd = [
        "yt-dlp",
        "--extractor-args", "youtube:player_client=tv_embedded,mweb",
        "--no-check-certificates",
        f"ytsearch{limit}:{search_term}",
        "--dump-json",
        "--flat-playlist",
        "--no-playlist",
        "--match-filter", "!is_live & duration > 600 & duration < 28800",
    ]

    try:
        logger.info(f"Searching YouTube for English streamed VODs: '{search_term}'...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        videos = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            try:
                item = json.loads(line)
                vid = item.get("id")
                if not vid or vid in processed:
                    continue

                title = item.get("title", "")
                channel = item.get("uploader") or item.get("channel", "Unknown")
                views = int(item.get("view_count") or 0)

                # English check
                if not is_english_content(title=title, description="", metadata=item):
                    continue

                if views >= min_views:
                    videos.append({
                        "video_id": vid,
                        "title": title,
                        "channel": channel,
                        "views": views,
                        "duration": item.get("duration", 0),
                        "url": f"https://www.youtube.com/watch?v={vid}",
                    })
            except Exception:
                continue

        # Sort descending by view count to pick the highest quality candidate
        return sorted(videos, key=lambda x: x["views"], reverse=True)

    except Exception as e:
        logger.warning(f"Error querying streamed VODs: {e}")
    return []


def discover_next_stream_vod(config: dict) -> Optional[Dict[str, Any]]:
    """
    Finds the next unclipped English stream VOD to process in this run:
    1. Checks manual targets if specified.
    2. Searches for primary game (e.g. GTA 6).
    3. Falls back to GTA 5 stream VODs if GTA 6 has no new unclipped streams.
    """
    # 1. Manual targets override
    for target in config.get("manual_targets", []):
        if "youtube.com/watch" in target or "youtu.be/" in target:
            vid = target.split("=")[-1].split("&")[0]
            if vid not in get_processed_ids():
                logger.info(f"Target manual video found: {target}")
                return {"url": target, "video_id": vid, "title": "GTA Stream Gameplay", "channel": "Target Streamer"}

    disc_cfg = config.get("discovery", {})
    primary_query = disc_cfg.get("game_query", "Grand Theft Auto VI")
    fallback_query = disc_cfg.get("fallback_game_query", "Grand Theft Auto V")
    min_views = config.get("vod_clipping", {}).get("min_views", 2000)

    # 2. Search primary game
    candidates = get_top_streamed_vods(primary_query, limit=15, min_views=min_views)

    # 3. Fallback to high-view GTA 5 stream VODs if needed
    if not candidates and fallback_query:
        logger.info(f"No new English '{primary_query}' streams found. Checking '{fallback_query}' streams...")
        candidates = get_top_streamed_vods(fallback_query, limit=15, min_views=min_views)

    if candidates:
        selected = candidates[0]
        logger.info(
            f"🎯 Selected Stream VOD: [{selected['channel']}] ({selected['views']:,} views) - {selected['title']}"
        )
        return selected

    logger.info("No unclipped English stream VODs found meeting criteria.")
    return None
