"""
VOD & Uploaded Video Highlight Clipper
Extracts the most viral/high-retention moment from ANY Twitch Stream VOD or YouTube Walkthrough:
1. Checks YouTube's 'Most Replayed' Heatmap (for YouTube videos).
2. Checks Twitch game chapter boundaries to target gameplay (skipping intros / Just Chatting).
3. Uses action-center peak heuristic inside the gameplay segment.
4. Downloads ONLY the 35s highlight slice directly without downloading the full stream.
5. Supports cookies.txt if provided in GitHub Secrets.
"""

import os
import time
import subprocess
import json
import logging
from typing import Optional, Tuple, Dict, Any

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def format_timestamp(seconds: float) -> str:
    """Converts seconds into HH:MM:SS format for yt-dlp download sections."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def get_video_info(video_url: str) -> Optional[Dict[str, Any]]:
    """Fetches video metadata including duration, heatmap, chapters, and title."""
    cmd = [
        "yt-dlp",
        "--no-check-certificates",
        "--user-agent", USER_AGENT,
        "--dump-json",
        "--skip-download",
        "--no-playlist",
    ]

    if "youtube.com" in video_url or "youtu.be" in video_url:
        cmd.extend(["--extractor-args", "youtube:player_client=tv_embedded,mweb"])
    if os.path.exists("cookies.txt"):
        cmd.extend(["--cookies", "cookies.txt"])

    cmd.append(video_url)

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=35)
        if res.returncode == 0 and res.stdout.strip():
            return json.loads(res.stdout)
        else:
            logger.warning(f"Metadata notice: {res.stderr[:200]}")
    except Exception as e:
        logger.warning(f"Error fetching metadata for {video_url}: {e}")
    return None


def find_best_highlight_timestamp(
    info: Optional[Dict[str, Any]],
    default_duration: float = 600.0,
    clip_duration: int = 35
) -> Tuple[float, float]:
    """
    Finds the optimal start and end time (in seconds) for a highlight clip:
    - First Priority: YouTube 'Most Replayed' heatmap peak.
    - Second Priority: Gameplay chapter boundaries (e.g., 'Grand Theft Auto VI' chapter).
    - Third Priority: Action-center window inside video.
    """
    duration = float((info.get("duration") if info else None) or default_duration or 600.0)
    heatmap = info.get("heatmap") if info else None

    # 1. YouTube 'Most Replayed' Heatmap Peak
    if heatmap and len(heatmap) > 0:
        valid_points = [
            pt for pt in heatmap
            if (duration * 0.10) <= pt.get("start_time", 0) <= (duration * 0.90)
        ]
        if valid_points:
            peak = max(valid_points, key=lambda x: x.get("value", 0))
            peak_start = float(peak.get("start_time", duration * 0.35))
            clip_start = max(0.0, peak_start - (clip_duration / 2))
            clip_end = min(duration, clip_start + clip_duration)
            logger.info(f"Heatmap Peak detected at {format_timestamp(peak_start)} (Score: {peak.get('value'):.2f})")
            return clip_start, clip_end

    # 2. Check Twitch Game Chapters
    chapters = (info.get("chapters") if info else None) or []
    gta_chapters = [
        c for c in chapters
        if any(g in c.get("title", "").lower() for g in ["grand theft auto", "gta"])
    ]

    if gta_chapters:
        # Pick the longest GTA gameplay chapter
        best_chapter = max(gta_chapters, key=lambda c: c.get("end_time", 0) - c.get("start_time", 0))
        ch_start = float(best_chapter.get("start_time", 0))
        ch_end = float(best_chapter.get("end_time", duration))
        ch_duration = max(clip_duration * 2, ch_end - ch_start)

        # Target 45% into the gameplay chapter (where peak action happens)
        highlight_start = ch_start + (ch_duration * 0.45)
        highlight_end = min(duration, highlight_start + clip_duration)
        logger.info(
            f"🎯 Chapter '{best_chapter.get('title')}' targeted: highlight at {format_timestamp(highlight_start)} "
            f"(Range: {format_timestamp(ch_start)} -> {format_timestamp(ch_end)})"
        )
        return highlight_start, highlight_end

    # 3. Core action-center window (35% to 50% into stream)
    fallback_start = max(30.0, duration * 0.40)
    fallback_end = min(duration, fallback_start + clip_duration)
    logger.info(
        f"Using action-center highlight window at {format_timestamp(fallback_start)} (Total Duration: {format_timestamp(duration)})"
    )
    return fallback_start, fallback_end


def slice_video_highlight(
    video_url: str,
    start_sec: float,
    end_sec: float,
    output_path: str
) -> bool:
    """
    Downloads ONLY the specified time window directly from Twitch or YouTube.
    Avoids downloading the full multi-hour stream.
    """
    start_str = format_timestamp(start_sec)
    end_str = format_timestamp(end_sec)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    if os.path.exists(output_path):
        os.remove(output_path)

    cmd = [
        "yt-dlp",
        "--download-sections", f"*{start_str}-{end_str}",
        "--force-keyframes-at-cuts",
        "--user-agent", USER_AGENT,
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "-o", output_path,
        "--no-check-certificates",
        "--no-playlist",
    ]

    if "youtube.com" in video_url or "youtu.be" in video_url:
        cmd.extend(["--extractor-args", "youtube:player_client=tv_embedded,mweb"])
    if os.path.exists("cookies.txt"):
        cmd.extend(["--cookies", "cookies.txt"])

    cmd.append(video_url)

    logger.info(f"Downloading highlight section [{start_str} -> {end_str}] from {video_url}...")
    try:
        start_time = time.time()
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        elapsed = time.time() - start_time

        if res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 100_000:
            size_mb = os.path.getsize(output_path) / (1024 * 1024)
            logger.info(f"Highlight slice downloaded successfully in {elapsed:.1f}s ({size_mb:.1f} MB): {output_path}")
            return True
        else:
            logger.error(f"Slice download failed: {res.stderr[-300:]}")
            # Try single format fallback if merge format had an issue
            fallback_cmd = [
                "yt-dlp",
                "--download-sections", f"*{start_str}-{end_str}",
                "-f", "best",
                "-o", output_path,
                "--no-check-certificates",
                video_url
            ]
            res2 = subprocess.run(fallback_cmd, capture_output=True, text=True, timeout=120)
            if res2.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 100_000:
                logger.info(f"Highlight slice downloaded successfully via fallback format: {output_path}")
                return True
    except Exception as e:
        logger.error(f"Exception during slice download: {e}")

    return False
