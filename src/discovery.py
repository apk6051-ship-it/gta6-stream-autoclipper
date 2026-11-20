"""
Streamed VOD Discovery Module (Twitch Focused Sequencer)
Discovers past live streams and gameplay walkthroughs for GTA 6 / GTA 5.
Sequentially iterates through all top Twitch GTA streams/creators one by one.
Filters strictly for English audio/content and ensures no video is ever clipped twice.
Twitch VODs are prioritized for cloud runners because they have zero bot/CAPTCHA blocks.
"""

import os
import logging
import requests
import json
from typing import Optional, Dict, Any, List, Set
from src.lang_detector import is_english_content

logger = logging.getLogger(__name__)

TWITCH_PUBLIC_CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"
HISTORY_FILE = "processed_videos.txt"

# Top GTA creators to track for VODs
TOP_CREATORS = [
    "kaicenat", "caseoh_", "stableronaldo", "xqc", "jynxzi",
    "ishowspeed", "fanum", "theburntpeanut", "yourragegaming",
    "darkviperau", "nickmercs", "timthetatman", "ludwig", "jasontheween"
]

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
            broadcastSettings {
              language
            }
          }
        }
      }
    }
  }
}
"""

TWITCH_CREATOR_QUERY = """
query GetCreatorVideos($login: String!) {
  user(login: $login) {
    displayName
    login
    videos(first: 5, types: ARCHIVE) {
      edges {
        node {
          id
          title
          viewCount
          lengthSeconds
          game {
            name
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


def get_top_twitch_vods(game_name: str, limit: int = 40, min_views: int = 500) -> List[Dict[str, Any]]:
    """
    Fetches top past stream broadcasts (VODs) from Twitch for a specific game category.
    Filters for verified English broadcasts.
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
                owner_data = node.get("owner") or {}
                owner_name = owner_data.get("displayName") or owner_data.get("login", "Streamer")
                lang = (owner_data.get("broadcastSettings") or {}).get("language", "").lower()
                views = int(node.get("viewCount", 0))

                # If Twitch reports broadcast language and it is not English, skip
                if lang and not lang.startswith("en"):
                    continue

                # Content-based English check
                if not is_english_content(title=title):
                    continue

                if views >= min_views:
                    results.append({
                        "platform": "twitch",
                        "video_id": vid,
                        "title": title,
                        "channel": owner_name,
                        "views": views,
                        "duration": float(node.get("lengthSeconds", 3600)),
                        "url": f"https://www.twitch.tv/videos/{vid}",
                    })
            return results
    except Exception as e:
        logger.warning(f"Error querying Twitch VODs for {game_name}: {e}")
    return []


def get_creator_gta_vods(creators: List[str] = TOP_CREATORS) -> List[Dict[str, Any]]:
    """
    Checks specific top creators for any recent GTA streams or archives.
    """
    processed = get_processed_ids()
    headers = {
        "Client-ID": TWITCH_PUBLIC_CLIENT_ID,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    results = []
    for creator in creators[:6]:  # Check first batch of top creators
        try:
            resp = requests.post(
                "https://gql.twitch.tv/gql",
                json={"query": TWITCH_CREATOR_QUERY, "variables": {"login": creator}},
                headers=headers,
                timeout=5,
            )
            if resp.status_code == 200:
                data = resp.json()
                user_data = data.get("data", {}).get("user")
                if not user_data:
                    continue
                videos = user_data.get("videos", {}).get("edges", [])
                for v in videos:
                    n = v["node"]
                    vid = str(n["id"])
                    if vid in processed:
                        continue
                    title = n.get("title", "")
                    game_info = (n.get("game") or {}).get("name", "")
                    # Match GTA titles or game tag
                    if any(k in title.lower() or k in game_info.lower() for k in ["gta", "grand theft auto"]):
                        if is_english_content(title):
                            results.append({
                                "platform": "twitch",
                                "video_id": vid,
                                "title": title,
                                "channel": user_data.get("displayName", creator),
                                "views": int(n.get("viewCount", 0)),
                                "duration": float(n.get("lengthSeconds", 3600)),
                                "url": f"https://www.twitch.tv/videos/{vid}",
                            })
        except Exception:
            continue
    return results


def discover_next_stream_vod(config: dict) -> Optional[Dict[str, Any]]:
    """
    Finds the next unclipped English Twitch stream VOD in sequence:
    1. Checks manual targets first if specified.
    2. Builds queue of all top Twitch GTA 6 stream VODs + top creators.
    3. Falls back to top Twitch GTA 5 stream VODs if needed.
    4. Picks the next top-ranked stream that hasn't been clipped yet.
    """
    # 1. Manual targets override
    for target in config.get("manual_targets", []):
        if "twitch.tv" in target:
            vid = target.split("/")[-1].split("=")[-1].split("&")[0]
            if vid not in get_processed_ids():
                logger.info(f"Target manual Twitch stream found: {target}")
                return {"url": target, "video_id": vid, "title": "GTA Stream Gameplay", "channel": "Streamer"}

    disc_cfg = config.get("discovery", {})
    primary_query = disc_cfg.get("game_query", "Grand Theft Auto VI")
    fallback_query = disc_cfg.get("fallback_game_query", "Grand Theft Auto V")
    min_views = config.get("vod_clipping", {}).get("min_views", 500)

    # 2. Query Twitch GTA 6 Stream VODs & Creator Archives
    candidates: List[Dict[str, Any]] = []
    seen_ids = set()

    twitch_gta6 = get_top_twitch_vods(primary_query, limit=40, min_views=min_views)
    for c in twitch_gta6:
        if c["video_id"] not in seen_ids:
            seen_ids.add(c["video_id"])
            candidates.append(c)

    # Check top creator archives for any fresh GTA streams
    creator_vods = get_creator_gta_vods()
    for c in creator_vods:
        if c["video_id"] not in seen_ids:
            seen_ids.add(c["video_id"])
            candidates.append(c)

    # 3. Fallback to GTA 5 top VODs if candidates are low
    if len(candidates) < 5 and fallback_query:
        twitch_gta5 = get_top_twitch_vods(fallback_query, limit=30, min_views=min_views)
        for c in twitch_gta5:
            if c["video_id"] not in seen_ids:
                seen_ids.add(c["video_id"])
                candidates.append(c)

    if not candidates:
        logger.info("No unclipped English Twitch stream VODs found meeting criteria.")
        return None

    # Sort remaining candidates by views to clip the highest impact moments first
    candidates.sort(key=lambda x: x["views"], reverse=True)

    selected = candidates[0]
    logger.info(
        f"🎯 Next in Queue: [{selected['channel']}] ({selected['views']:,} views) - {selected['title']}"
    )
    logger.info(f"   URL: {selected['url']} | Remaining in queue: {len(candidates)}")

    return selected
