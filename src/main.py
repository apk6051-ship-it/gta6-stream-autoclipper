"""
Main Orchestrator
Executes a single detection and clipping session:
1. Discovers if an active, reliable GTA stream is live.
2. If NO reliable stream is found -> logs status and ends process cleanly (exit code 0).
3. If reliable stream IS found -> initiates live recording, chat velocity tracking,
   automatic clip extraction, vertical formatting, and YouTube upload.
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

from src.discovery import discover_reliable_stream
from src.twitch_chat import TwitchChatMonitor
from src.youtube_chat import YouTubeChatMonitor
from src.recorder import StreamRecorder
from src.processor import VideoProcessor
from src.uploader import YouTubeUploader


def load_config(path: str = "config.yaml") -> dict:
    if not os.path.exists(path):
        logger.error(f"Config file not found: {path}")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_session():
    logger.info("=== Starting GTA 6 Auto-Clipper Session ===")
    config = load_config()

    # Step 1: Discover active reliable stream
    stream = discover_reliable_stream(config)

    if not stream:
        logger.info(">>> No reliable stream available right now. Ending process cleanly. <<<")
        sys.exit(0)

    # Step 2: Initialize components
    logger.info(f"Target locked: {stream['display_name']} ({stream['url']}) with {stream['viewers']:,} viewers.")

    recorder = StreamRecorder(
        stream_url=stream["url"],
        buffer_dir="buffer",
        clips_dir="clips",
        segment_duration=4,
        max_buffer_seconds=120,
    )

    processor = VideoProcessor(
        output_width=config.get("video", {}).get("width", 1080),
        output_height=config.get("video", {}).get("height", 1920),
    )

    uploader = None
    if config.get("youtube", {}).get("enabled", True):
        uploader = YouTubeUploader()

    # Step 3: Define viral spike callback
    def on_viral_moment(timestamp: float, current_msgs: int, baseline: float):
        logger.info(f"⚡ Processing viral spike event ({current_msgs} msgs / baseline {baseline:.1f})...")

        clip_cfg = config.get("clipping", {})
        clip_duration = clip_cfg.get("clip_duration_sec", 35)

        raw_clip = recorder.extract_recent_clip(clip_duration_sec=clip_duration)
        if not raw_clip:
            logger.warning("Failed to extract raw clip from stream buffer.")
            return

        # Render 9:16 vertical Short
        timestamp_str = time.strftime("%Y%m%d_%H%M%S")
        short_clip_path = os.path.join("clips", f"short_{stream['channel']}_{timestamp_str}.mp4")

        rendered = processor.format_for_shorts(
            input_video_path=raw_clip,
            output_video_path=short_clip_path,
        )

        if not rendered:
            logger.warning("Failed to format video for Shorts.")
            return

        # Upload to YouTube
        if uploader and os.path.exists("client_secret.json"):
            yt_cfg = config.get("youtube", {})
            title = yt_cfg.get("title_template", "INSANE GTA 6 MOMENT! 😱🔥 #GTA6 #Shorts").replace(
                "{game}", "GTA6"
            )
            description = yt_cfg.get("description", "")
            tags = yt_cfg.get("tags", ["GTA 6", "Shorts", "Gaming"])
            privacy = yt_cfg.get("privacy_status", "public")

            uploader.upload_short(
                video_path=short_clip_path,
                title=title,
                description=description,
                tags=tags,
                privacy_status=privacy,
            )
        else:
            logger.info(f"Short saved locally at: {short_clip_path} (Add client_secret.json to auto-upload to YouTube)")

    # Step 4: Start recorder
    recorder.start()

    # Step 5: Start chat velocity monitor
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

    # Step 6: Run session duration
    session_minutes = config.get("scheduler", {}).get("stream_session_minutes", 115)
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
