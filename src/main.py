"""
GTA 6 Stream VOD Highlight Auto-Clipper & Uploader
Autonomous pipeline:
1. Discovers an unclipped English GTA stream VOD / gameplay walkthrough on YouTube.
2. Scans YouTube's 'Most Replayed' heatmap for the peak viral moment.
3. Downloads ONLY the 35s highlight slice (zero full-video download).
4. Converts 16:9 gameplay to 9:16 vertical Short with blurred backdrop & centered game.
5. Uses Google Gemini API to generate unique viral titles, descriptions, and tags.
6. Auto-uploads directly to YouTube Shorts and records processed ID.
"""

import os
import sys
import time
import yaml
import logging
from typing import Optional

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("autoclipper.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("AutoClipper")

from src.discovery import discover_next_stream_vod, mark_video_processed
from src.vod_clipper import get_video_info, find_best_highlight_timestamp, slice_video_highlight
from src.processor import VideoProcessor
from src.uploader import YouTubeUploader
from src.ai_metadata import generate_shorts_metadata


def load_config(path: str = "config.yaml") -> dict:
    if not os.path.exists(path):
        logger.error(f"Config file not found: {path}")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_session():
    logger.info("=== Starting GTA Stream Highlight Clipper Session ===")
    config = load_config()

    processor = VideoProcessor(
        output_width=config.get("video", {}).get("width", 1080),
        output_height=config.get("video", {}).get("height", 1920),
    )

    uploader = None
    if config.get("youtube", {}).get("enabled", True):
        uploader = YouTubeUploader()

    # Step 1: Find next unclipped English stream VOD
    video = discover_next_stream_vod(config)
    if not video:
        logger.info("No new unclipped English stream VODs available. Ending cleanly.")
        sys.exit(0)

    logger.info(f"Locked onto Stream: [{video['channel']}] {video['title'][:60]}")

    # Step 2: Fetch metadata and locate peak replay moment
    info = get_video_info(video["url"])
    clip_duration = config.get("vod_clipping", {}).get("clip_duration_sec", 35)
    start_sec, end_sec = find_best_highlight_timestamp(
        info=info,
        default_duration=float(video.get("duration") or 600.0),
        clip_duration=clip_duration,
    )

    timestamp_str = time.strftime("%Y%m%d_%H%M%S")
    os.makedirs("clips", exist_ok=True)
    raw_slice_path = os.path.join("clips", f"raw_vod_{timestamp_str}.mp4")
    short_clip_path = os.path.join("clips", f"short_vod_{timestamp_str}.mp4")

    # Step 3: Download ONLY the 35s highlight
    if not slice_video_highlight(video["url"], start_sec, end_sec, raw_slice_path):
        logger.warning(f"Failed to download highlight slice for {video['url']}. Marking video as skipped.")
        if video.get("video_id"):
            mark_video_processed(video["video_id"])
        sys.exit(0)

    # Step 4: Convert to 9:16 vertical Short
    if not processor.format_for_shorts(raw_slice_path, short_clip_path):
        logger.error("Failed to render 9:16 vertical Short.")
        sys.exit(1)

    # Clean up raw download to keep workspace clean
    try:
        os.remove(raw_slice_path)
    except Exception:
        pass

    # Step 5: Generate AI Metadata via Gemini
    logger.info("🤖 Generating viral title, description, and tags with Gemini...")
    metadata = generate_shorts_metadata(
        video_title=video["title"],
        channel_name=video["channel"],
    )

    title = metadata.get("title", f"{video['channel']} GTA 6 Moment #Shorts")
    description = metadata.get("description", "")
    tags = metadata.get("tags", ["GTA 6", "Shorts", "Gaming"])

    logger.info(f"Title: {title}")

    # Step 6: Upload to YouTube Shorts
    uploaded_url = None
    if uploader and os.path.exists("client_secret.json"):
        privacy = config.get("youtube", {}).get("privacy_status", "public")
        uploaded_url = uploader.upload_short(
            video_path=short_clip_path,
            title=title,
            description=description,
            tags=tags,
            privacy_status=privacy,
        )
    else:
        logger.info(f"Short saved locally at: {short_clip_path} (No client_secret.json detected)")

    # Step 7: Record video ID as processed so it is never repeated
    if video.get("video_id"):
        mark_video_processed(video["video_id"])

    logger.info(f"🎉 Session Complete! Clip successfully created & processed.")
    if uploaded_url:
        logger.info(f"Watch Short: {uploaded_url}")


if __name__ == "__main__":
    run_session()
