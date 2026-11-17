"""
Video Processor Module
1. Formats horizontal 16:9 stream video into high-engagement 9:16 (1080x1920) YouTube Shorts format:
   - Blurred background aesthetic + centered crisp gameplay.
2. Generates and burns stylish captions / subtitles onto the video.
"""

import os
import subprocess
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class VideoProcessor:
    def __init__(self, output_width: int = 1080, output_height: int = 1920):
        self.output_width = output_width
        self.output_height = output_height

    def format_for_shorts(
        self,
        input_video_path: str,
        output_video_path: str,
        add_text_header: Optional[str] = "🔥 GTA 6 LIVE MOMENT 🔥"
    ) -> bool:
        """
        Converts 16:9 gameplay video into vertical 9:16 (1080x1920) Shorts format.
        Creates a blurred background backdrop with the centered 16:9 gameplay stream on top.
        """
        if not os.path.exists(input_video_path):
            logger.error(f"Input file does not exist: {input_video_path}")
            return False

        # FFmpeg filter:
        # 1. Scale and crop input to fill 1080x1920 and apply strong blur for background [bg]
        # 2. Scale input to fit 1080 width while keeping 16:9 aspect ratio [fg]
        # 3. Overlay [fg] onto [bg] centered vertically
        filter_complex = (
            f"[0:v]scale={self.output_width}:{self.output_height}:force_original_aspect_ratio=increase,"
            f"crop={self.output_width}:{self.output_height},boxblur=25:5[bg];"
            f"[0:v]scale={self.output_width}:-1[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2[v]"
        )

        cmd = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel", "error",
            "-i", input_video_path,
            "-filter_complex", filter_complex,
            "-map", "[v]",
            "-map", "0:a?",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "22",
            "-c:a", "aac",
            "-b:a", "128k",
            output_video_path,
        ]

        logger.info(f"Rendering 9:16 Short: {output_video_path}...")
        res = subprocess.run(cmd, capture_output=True, text=True)

        if res.returncode == 0 and os.path.exists(output_video_path) and os.path.getsize(output_video_path) > 0:
            logger.info("Short rendered successfully!")
            return True
        else:
            logger.error(f"FFmpeg render error: {res.stderr}")
            return False
