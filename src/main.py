"""
Main Orchestrator (Dual Engine: Live Stream + Uploaded VOD Clipper)
1. Live Stream Mode: Discovers active streams, records circular buffer, catches chat bursts, cuts & uploads Shorts.
2. VOD / Uploaded Video Mode: If no live stream is active, finds top uploaded GTA gameplay videos,
   identifies peak replay/action moment, slices 35s with zero full-video download, converts to 9:16 Shorts & uploads.
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

from src.discovery import discover_content, mark_video_processed
from src.twitch_chat import TwitchChatMonitor
from src.youtube_chat import YouTubeChatMonitor
from src.recorder import StreamRecorder
from src.processor import VideoProcessor
from src.uploader import YouTubeUploader
from src.vod_clipper import get_video_info, find_best_highlight_timestamp, slice_video_highlight


def load_config(path: str = "config.yaml") -> dict:
    if not os.path.exists(path):
        logger.error(f"Config file not found: {path}")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def handle_vod_session(video: dict, config: dict, processor: VideoProcessor, uploader: Optional[YouTubeUploader]):
    """Processes an uploaded video / VOD: locates peak moment, downloads 35s slice, formats and uploads."""
    logger.info(f"Processing Uploaded VOD: [{video.get('channel')}] {video.get('title', '')[:60]}")
    info = get_video_info(video["url"])
    if not info:
        logger.error(f"Could not load metadata for video: {video['url']}")
        return

    clip_duration = config.get("vod_clipping", {}).get("clip_duration_sec", 35)
    start_sec, end_sec = find_best_highlight_timestamp(info, clip_duration=clip_duration)

    timestamp_str = time.strftime("%Y%m%d_%H%M%S")
    os.makedirs("clips", exist_ok=True)
    raw_slice_path = os.path.join("clips", f"raw_vod_{timestamp_str}.mp4")
    short_clip_path = os.path.join("clips", f"short_vod_{timestamp_str}.mp4")

    # 1. Download only the 35s highlight
    if not slice_video_highlight(video["url"], start_sec, end_sec, raw_slice_path):
        logger.error("Failed to extract VOD highlight slice.")
        return

    # 2. Reformat to 9:16 vertical Short
    if not processor.format_for_shorts(raw_slice_path, short_clip_path):
        logger.error("Failed to render 9:16 vertical Short.")
        return

    # 3. Mark video as processed to avoid duplicates
    if video.get("video_id"):
        mark_video_processed(video["video_id"])

    # 4. Upload to YouTube
    if uploader and os.path.exists("client_secret.json"):
        yt_cfg = config.get("youtube", {})
        title = yt_cfg.get("title_template", "INSANE GTA 6 MOMENT! 😱🔥 #{game} #Shorts").replace("{game}", "GTA6")
        uploader.upload_short(
            video_path=short_clip_path,
            title=title,
            description=yt_cfg.get("description", ""),
            tags=yt_cfg.get("tags", ["GTA 6", "Shorts", "Gaming"]),
            privacy_status=yt_cfg.get("privacy_status", "public"),
        )
    else:
        logger.info(f"Short saved locally at: {short_clip_path}")

    # Clean up raw slice to save disk space
    try:
        os.remove(raw_slice_path)
    except Exception:
        pass

    logger.info("🎉 VOD Highlight successfully extracted, formatted and uploaded!")


def run_session():
    logger.info("=== Starting GTA 6 Auto-Clipper Session ===")
    config = load_config()

    processor = VideoProcessor(
        output_width=config.get("video", {}).get("width", 1080),
        output_height=config.get("video", {}).get("height", 1920),
    )

    uploader = None
    if config.get("youtube", {}).get("enabled", True):
        uploader = YouTubeUploader()

    # Step 1: Content Discovery (Live Stream or Uploaded VOD)
    content = discover_content(config)

    if not content:
        logger.info(">>> No reliable live stream or uploaded video available right now. Ending cleanly. <<<")
        sys.exit(0)

    # Branch A: Uploaded VOD Mode
    if content["mode"] == "vod":
        handle_vod_session(content["data"], config, processor, uploader)
        return

    # Branch B: Live Stream Mode
    stream = content["data"]
    logger.info(f"Target Live Stream locked: {stream['display_name']} ({stream['url']}) with {stream['viewers']:,} viewers.")

    recorder = StreamRecorder(
        stream_url=stream["url"],
        buffer_dir="buffer",
        clips_dir="clips",
        segment_duration=4,
        max_buffer_seconds=120,
    )

    def on_viral_moment(timestamp: float, current_msgs: int, baseline: float):
        logger.info(f"⚡ Processing viral spike event ({current_msgs} msgs / baseline {baseline:.1f})...")
        clip_cfg = config.get("clipping", {})
        clip_duration = clip_cfg.get("clip_duration_sec", 35)

        raw_clip = recorder.extract_recent_clip(clip_duration_sec=clip_duration)
        if not raw_clip:
            logger.warning("Failed to extract raw clip from stream buffer.")
            return

        timestamp_str = time.strftime("%Y%m%d_%H%M%S")
        short_clip_path = os.path.join("clips", f"short_{stream['channel']}_{timestamp_str}.mp4")

        rendered = processor.format_for_shorts(
            input_video_path=raw_clip,
            output_video_path=short_clip_path,
        )

        if not rendered:
            logger.warning("Failed to format video for Shorts.")
            return

        if uploader and os.path.exists("client_secret.json"):
            yt_cfg = config.get("youtube", {})
            title = yt_cfg.get("title_template", "INSANE GTA 6 MOMENT! 😱🔥 #{game} #Shorts").replace("{game}", "GTA6")
            uploader.upload_short(
                video_path=short_clip_path,
                title=title,
                description=yt_cfg.get("description", ""),
                tags=yt_cfg.get("tags", ["GTA 6", "Shorts", "Gaming"]),
                privacy_status=yt_cfg.get("privacy_status", "public"),
            )
        else:
            logger.info(f"Short saved locally at: {short_clip_path}")

    recorder.start()

    chat_monitor = None
    clip_cfg = config.get("clipping", {})
    if stream["platform"] == "twitch":
        chat_monitor = TwitchChatMonitor(
            channel=stream["channel"],
            on_spike=on_viral_moment,
            window_sec=clip_cfg.get("window_sec", 10),
            baseline_sec=clip_cfg.get("baseline_sec", 60),
            spike_multiplier=clip_cfg.get("spike_multiplier", 3.0),
            min_spike_messages=clip_cfg.get("min_spike_messages", 15),
            cooldown_sec=clip_cfg.get("cooldown_sec", 180),
        )
    elif stream["platform"] == "youtube" and stream.get("video_id"):
        chat_monitor = YouTubeChatMonitor(
            video_id=stream["video_id"],
            on_spike=on_viral_moment,
            window_sec=clip_cfg.get("window_sec", 10),
            baseline_sec=clip_cfg.get("baseline_sec", 60),
            spike_multiplier=clip_cfg.get("spike_multiplier", 3.0),
            min_spike_messages=clip_cfg.get("min_spike_messages", 15),
            cooldown_sec=clip_cfg.get("cooldown_sec", 180),
        )

    if chat_monitor:
        chat_monitor.start()

    env_mins = os.environ.get("SESSION_MINUTES")
    session_minutes = int(env_mins) if env_mins else config.get("scheduler", {}).get("stream_session_minutes", 115)
    logger.info(f"Clipper active and monitoring for {session_minutes} minutes...")

    try:
        time.sleep(session_minutes * 60)
    except KeyboardInterrupt:
        logger.info("Session manually interrupted by user.")
    finally:
        logger.info("Cleaning up session...")
        if chat_monitor:
            chat_monitor.stop()
        recorder.stop()
        logger.info("Session complete.")


if __name__ == "__main__":
    run_session()
