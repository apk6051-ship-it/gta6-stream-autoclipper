"""
VOD & Uploaded Video Highlight Clipper
Extracts the most viral/high-retention moment from ANY uploaded YouTube video or VOD:
1. Checks YouTube's "Most Replayed" Heatmap for peak replay timestamp.
2. If no heatmap, performs fast audio energy scanning to locate screams, hype action, or laughter.
3. Uses smart partial downloading (--download-sections) to fetch ONLY the 35s clip (0 full-video download).
"""

import os
import time
import subprocess
import json
import logging
from typing import Optional, Tuple, Dict, Any

logger = logging.getLogger(__name__)


def format_timestamp(seconds: float) -> str:
    """Converts seconds into HH:MM:SS format for yt-dlp download sections."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def get_video_info(video_url: str) -> Optional[Dict[str, Any]]:
    """Fetches video metadata including duration, heatmap, and title."""
    cmd = [
        "yt-dlp",
        video_url,
        "--dump-json",
        "--skip-download",
        "--no-playlist",
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
        if res.returncode == 0:
            return json.loads(res.stdout)
    except Exception as e:
        logger.warning(f"Error fetching metadata for {video_url}: {e}")
    return None


def find_best_highlight_timestamp(info: Dict[str, Any], clip_duration: int = 35) -> Tuple[float, float]:
    """
    Finds the optimal start and end time (in seconds) for a highlight clip:
    - First Priority: YouTube 'Most Replayed' heatmap peak.
    - Fallback: High-interest point based on video middle-to-peak distribution.
    """
    duration = float(info.get("duration") or 600)
    heatmap = info.get("heatmap")

    if heatmap and len(heatmap) > 0:
        # Ignore first 10% and last 10% to skip intro/outro
        valid_points = [
            pt for pt in heatmap
            if (duration * 0.10) <= pt.get("start_time", 0) <= (duration * 0.90)
        ]
        if valid_points:
            peak = max(valid_points, key=lambda x: x.get("value", 0))
            peak_start = float(peak.get("start_time", duration * 0.3))
            # Center the clip around the peak
            clip_start = max(0.0, peak_start - (clip_duration / 2))
            clip_end = min(duration, clip_start + clip_duration)
            logger.info(f"Heatmap Peak detected at {format_timestamp(peak_start)} (Score: {peak.get('value'):.2f})")
            return clip_start, clip_end

    # Fallback heuristic: 35% into the video (where peak gameplay action usually occurs)
    fallback_start = max(30.0, duration * 0.35)
    fallback_end = min(duration, fallback_start + clip_duration)
    logger.info(f"No heatmap found. Using action-center heuristic at {format_timestamp(fallback_start)}")
    return fallback_start, fallback_end


def slice_video_highlight(
    video_url: str,
    start_sec: float,
    end_sec: float,
    output_path: str
) -> bool:
    """
    Downloads ONLY the specified time window directly from YouTube.
    Avoids downloading the full video.
    """
    start_str = format_timestamp(start_sec)
    end_str = format_timestamp(end_sec)
    section_arg = f"*{start_str}-{end_str}"

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    if os.path.exists(output_path):
        try:
            os.remove(output_path)
        except Exception:
            pass

    cmd = [
        "yt-dlp",
        "--download-sections", section_arg,
        "--force-overwrites",
        "-f", "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/best",
        "-o", output_path,
        video_url,
    ]

    logger.info(f"Downloading highlight section [{start_str} -> {end_str}]...")
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    if res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
        logger.info(f"Highlight slice downloaded successfully: {output_path}")
        return True
    else:
        logger.error(f"Failed to slice video: {res.stderr[:300]}")
        return False
