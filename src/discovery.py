"""
Unified Content Discovery Module
Discovers both:
1. Live Streams: Active high-traffic GTA 6 / GTA 5 livestreams on Twitch and YouTube.
2. Uploaded Videos (VODs): High-performing recently uploaded gameplay walkthroughs and videos.
"""

import os
import logging
import requests
import subprocess
import json
from typing import Optional, Dict, Any, List, Set

logger = logging.getLogger(__name__)

TWITCH_PUBLIC_CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"

GQL_QUERY = """
query GetStreams($game: String!, $first: Int!) {
  game(name: $game) {
    name
    streams(first: $first) {
      edges {
        node {
          id
          title
          viewersCount
          broadcaster {
            login
            displayName
          }
        }
      }
    }
  }
}
"""

HISTORY_FILE = "processed_videos.txt"


def get_processed_ids() -> Set[str]:
    """Returns set of video IDs that have already been clipped to prevent duplicates."""
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f if line.strip())
    return set()


def mark_video_processed(video_id: str):
    """Saves video ID to history file."""
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(f"{video_id}\n")


def get_top_twitch_streams(game_name: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Fetches top active streams for a specific game category on Twitch."""
    headers = {
        "Client-ID": TWITCH_PUBLIC_CLIENT_ID,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    try:
        resp = requests.post(
            "https://gql.twitch.tv/gql",
            json={"query": GQL_QUERY, "variables": {"game": game_name, "first": limit}},
            headers=headers,
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            game_data = data.get("data", {}).get("game")
            if not game_data:
                return []
            edges = game_data.get("streams", {}).get("edges", [])
            results = []
            for edge in edges:
                node = edge["node"]
                broadcaster = node["broadcaster"]
                results.append({
                    "platform": "twitch",
                    "channel": broadcaster["login"],
                    "display_name": broadcaster["displayName"],
                    "title": node.get("title", ""),
                    "viewers": node.get("viewersCount", 0),
                    "url": f"https://twitch.tv/{broadcaster['login']}",
                })
            return results
    except Exception as e:
        logger.warning(f"Error querying Twitch GQL: {e}")
    return []


def get_top_youtube_streams(search_query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Searches for active YouTube livestreams matching query using yt-dlp."""
    try:
        cmd = [
            "yt-dlp",
            f"ytsearch{limit}:{search_query} live",
            "--dump-json",
            "--flat-playlist",
            "--no-playlist",
            "--match-filter", "is_live",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        streams = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            try:
                item = json.loads(line)
                viewers = item.get("concurrent_view_count") or item.get("view_count") or 0
                streams.append({
                    "platform": "youtube",
                    "channel": item.get("uploader", "Unknown"),
                    "display_name": item.get("channel", "Unknown"),
                    "title": item.get("title", ""),
                    "viewers": int(viewers) if viewers else 0,
                    "url": item.get("url") or f"https://www.youtube.com/watch?v={item.get('id')}",
                    "video_id": item.get("id"),
                })
            except Exception:
                continue
        return sorted(streams, key=lambda x: x["viewers"], reverse=True)
    except Exception as e:
        logger.warning(f"Error querying YouTube livestreams: {e}")
    return []


def get_top_uploaded_videos(search_query: str, limit: int = 10, min_views: int = 1000) -> List[Dict[str, Any]]:
    """Searches YouTube for high-performing uploaded videos (non-live VODs)."""
    processed = get_processed_ids()
    try:
        cmd = [
            "yt-dlp",
            f"ytsearch{limit}:{search_query}",
            "--dump-json",
            "--flat-playlist",
            "--no-playlist",
            "--match-filter", "!is_live & duration > 180 & duration < 7200",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
        videos = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            try:
                item = json.loads(line)
                vid = item.get("id")
                if not vid or vid in processed:
                    continue
                views = int(item.get("view_count") or 0)
                if views >= min_views:
                    videos.append({
                        "platform": "youtube",
                        "video_id": vid,
                        "title": item.get("title", ""),
                        "channel": item.get("uploader") or item.get("channel", "Unknown"),
                        "display_name": item.get("channel", "Unknown"),
                        "viewers": views,
                        "views": views,
                        "duration": item.get("duration", 0),
                        "url": f"https://www.youtube.com/watch?v={vid}",
                    })
            except Exception:
                continue
        return sorted(videos, key=lambda x: x["views"], reverse=True)
    except Exception as e:
        logger.warning(f"Error querying uploaded videos: {e}")
    return []


def discover_reliable_stream(config: dict) -> Optional[Dict[str, Any]]:
    """Checks for active reliable live streams."""
    disc_cfg = config.get("discovery", {})
    min_viewers = disc_cfg.get("min_viewers", 500)
    primary_game = disc_cfg.get("game_query", "Grand Theft Auto VI")
    fallback_game = disc_cfg.get("fallback_game_query", "Grand Theft Auto V")
    manual_targets = config.get("manual_targets", [])

    for target in manual_targets:
        if "twitch.tv" in target or not target.startswith("http"):
            username = target.split("/")[-1].replace("@", "")
            streams = get_top_twitch_streams(primary_game, limit=20) + get_top_twitch_streams(fallback_game, limit=20)
            for s in streams:
                if s["channel"].lower() == username.lower():
                    logger.info(f"Target streamer {username} is LIVE with {s['viewers']} viewers!")
                    return s

    candidates: List[Dict[str, Any]] = []
    logger.info(f"Scanning for active '{primary_game}' livestreams...")
    candidates.extend(get_top_twitch_streams(primary_game, limit=10))

    if not candidates and fallback_game:
        logger.info(f"No active '{primary_game}' streams. Checking fallback '{fallback_game}'...")
        candidates.extend(get_top_twitch_streams(fallback_game, limit=10))

    if "youtube" in disc_cfg.get("platforms", []):
        logger.info("Scanning YouTube for active livestreams...")
        yt_candidates = get_top_youtube_streams(primary_game, limit=5)
        if not yt_candidates and fallback_game:
            yt_candidates = get_top_youtube_streams(fallback_game, limit=5)
        candidates.extend(yt_candidates)

    if not candidates:
        return None

    reliable = [s for s in candidates if s["viewers"] >= min_viewers]
    if not reliable:
        top_viewer_count = max(s["viewers"] for s in candidates)
        logger.info(
            f"Live streams exist, but top viewer count ({top_viewer_count}) is below threshold ({min_viewers})."
        )
        return None

    reliable.sort(key=lambda s: s["viewers"], reverse=True)
    best_stream = reliable[0]
    logger.info(
        f"Selected Reliable Stream: [{best_stream['platform'].upper()}] {best_stream['display_name']} "
        f"({best_stream['viewers']:,} viewers) - {best_stream['title'][:60]}"
    )
    return best_stream


def discover_content(config: dict) -> Optional[Dict[str, Any]]:
    """
    Unified Content Discovery (Live Stream + VOD Fallback):
    1. Searches for live streams with >= min_viewers.
    2. If no live stream is active, searches for top uploaded videos/VODs.
    """
    # 1. Live stream
    stream = discover_reliable_stream(config)
    if stream:
        return {"mode": "live", "data": stream}

    # 2. VOD / Uploaded Video fallback
    vod_cfg = config.get("vod_clipping", {})
    if vod_cfg.get("enabled", True):
        disc_cfg = config.get("discovery", {})
        query = disc_cfg.get("game_query", "Grand Theft Auto VI")
        fallback_query = disc_cfg.get("fallback_game_query", "Grand Theft Auto V")
        min_views = vod_cfg.get("min_views", 1000)

        # Check manual targets for uploaded videos
        for target in config.get("manual_targets", []):
            if "youtube.com/watch" in target or "youtu.be/" in target:
                logger.info(f"Target uploaded video configured: {target}")
                return {"mode": "vod", "data": {"url": target, "title": "GTA Gameplay Highlight", "channel": "Target", "video_id": target.split("=")[-1]}}

        logger.info(f"No active livestreams. Searching top uploaded '{query}' videos (VOD Mode)...")
        videos = get_top_uploaded_videos(query, limit=10, min_views=min_views)
        if not videos and fallback_query:
            logger.info(f"Searching fallback '{fallback_query}' uploaded videos...")
            videos = get_top_uploaded_videos(fallback_query, limit=10, min_views=min_views)

        if videos:
            best_video = videos[0]
            logger.info(
                f"Selected Uploaded Video: [{best_video['channel']}] ({best_video['views']:,} views) - {best_video['title'][:60]}"
            )
            return {"mode": "vod", "data": best_video}

    return None
