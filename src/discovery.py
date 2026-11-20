"""
Streamed VOD Discovery Module (Twitch & YouTube)
Discovers past live streams and gameplay walkthroughs for GTA 6 / GTA 5.
Filters strictly for English audio/content and ensures no video is ever clipped twice.
Twitch VODs are prioritized for cloud runners because they have zero bot/CAPTCHA blocks.
"""

import os
import logging
import requests
import subprocess
import json
from typing import Optional, Dict, Any, List, Set
from src.lang_detector import is_english_content

logger = logging.getLogger(__name__)

TWITCH_PUBLIC_CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"
HISTORY_FILE = "processed_videos.txt"

TWITCH_VODS_QUERY = """
query GetGameVideos($game: String!, $first: Int!) {
  game(name: $game) {
    videos(first: $first, sort: VIEWS) {
      edges {
        node {
          id
          title
          lengthSeconds
          viewCount
          owner {
            displayName
            login
          }
        }
      }
    }
  }
}
"""


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


def get_top_twitch_vods(game_name: str, limit: int = 15, min_views: int = 500) -> List[Dict[str, Any]]:
    """
    Fetches top past stream broadcasts (VODs) from Twitch.
    100% immune to cloud datacenter IP blocks.
    """
    processed = get_processed_ids()
    headers = {
        "Client-ID": TWITCH_PUBLIC_CLIENT_ID,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    try:
        logger.info(f"Querying Twitch for '{game_name}' past stream VODs...")
        resp = requests.post(
            "https://gql.twitch.tv/gql",
            json={"query": TWITCH_VODS_QUERY, "variables": {"game": game_name, "first": limit}},
            headers=headers,
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            game_data = data.get("data", {}).get("game")
            if not game_data:
                return []
            edges = game_data.get("videos", {}).get("edges", [])
            results = []
            for edge in edges:
                node = edge["node"]
                vid = str(node["id"])
                if vid in processed:
                    continue

                title = node.get("title", "")
                owner = node.get("owner", {})
                views = int(node.get("viewCount", 0))

                # English check
                if not is_english_content(title=title):
                    continue

                if views >= min_views:
                    results.append({
                        "platform": "twitch",
                        "video_id": vid,
                        "title": title,
                        "channel": owner.get("displayName") or owner.get("login", "Streamer"),
                        "views": views,
                        "duration": float(node.get("lengthSeconds", 3600)),
                        "url": f"https://www.twitch.tv/videos/{vid}",
                    })
            return sorted(results, key=lambda x: x["views"], reverse=True)
    except Exception as e:
        logger.warning(f"Error querying Twitch VODs: {e}")
    return []


def get_top_youtube_vods(search_query: str, limit: int = 10, min_views: int = 2000) -> List[Dict[str, Any]]:
    """Searches YouTube for stream VODs and full gameplay walkthroughs."""
    processed = get_processed_ids()
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

                if not is_english_content(title=title, metadata=item):
                    continue

                if views >= min_views:
                    videos.append({
                        "platform": "youtube",
                        "video_id": vid,
                        "title": title,
                        "channel": channel,
                        "views": views,
                        "duration": float(item.get("duration", 0)),
                        "url": f"https://www.youtube.com/watch?v={vid}",
                    })
            except Exception:
                continue
        return sorted(videos, key=lambda x: x["views"], reverse=True)
    except Exception as e:
        logger.warning(f"Error querying YouTube VODs: {e}")
    return []


def discover_next_stream_vod(config: dict) -> Optional[Dict[str, Any]]:
    """
    Finds the next unclipped English stream VOD:
    1. Checks manual targets first.
    2. Prioritizes Twitch Stream VODs (immune to cloud IP bot blocks).
    3. Falls back to YouTube VODs.
    """
    # 1. Manual targets override
    for target in config.get("manual_targets", []):
        if "twitch.tv" in target or "youtube.com" in target or "youtu.be" in target:
            vid = target.split("/")[-1].split("=")[-1].split("&")[0]
            if vid not in get_processed_ids():
                logger.info(f"Target manual video found: {target}")
                return {"url": target, "video_id": vid, "title": "GTA Stream Gameplay", "channel": "Streamer"}

    disc_cfg = config.get("discovery", {})
    primary_query = disc_cfg.get("game_query", "Grand Theft Auto VI")
    fallback_query = disc_cfg.get("fallback_game_query", "Grand Theft Auto V")
    min_views = config.get("vod_clipping", {}).get("min_views", 500)

    # 2. Check Twitch Stream VODs (Cloud runner friendly)
    twitch_candidates = get_top_twitch_vods(primary_query, limit=15, min_views=min_views)
    if not twitch_candidates and fallback_query:
        twitch_candidates = get_top_twitch_vods(fallback_query, limit=15, min_views=min_views)

    if twitch_candidates:
        selected = twitch_candidates[0]
        logger.info(
            f"🎯 Selected Twitch Stream VOD: [{selected['channel']}] ({selected['views']:,} views) - {selected['title']}"
        )
        return selected

    # 3. Fallback to YouTube VODs
    logger.info("Checking YouTube VODs fallback...")
    yt_candidates = get_top_youtube_vods(primary_query, limit=10, min_views=min_views)
    if not yt_candidates and fallback_query:
        yt_candidates = get_top_youtube_vods(fallback_query, limit=10, min_views=min_views)

    if yt_candidates:
        selected = yt_candidates[0]
        logger.info(
            f"🎯 Selected YouTube Stream VOD: [{selected['channel']}] ({selected['views']:,} views) - {selected['title']}"
        )
        return selected

    logger.info("No unclipped English stream VODs found meeting criteria.")
    return None
