"""
Stream Recorder & Rolling Buffer Manager
Streams video via streamlink / ffmpeg into a circular buffer of small segments.
When a viral spike is detected, extracts the exact window (e.g. 25s pre-spike, 10s post-spike)
seamlessly without interrupting the live recording.
"""

import os
import time
import subprocess
import threading
import logging
from typing import Optional, List

logger = logging.getLogger(__name__)


class StreamRecorder:
    def __init__(
        self,
        stream_url: str,
        buffer_dir: str = "buffer",
        clips_dir: str = "clips",
        segment_duration: int = 4,
        max_buffer_seconds: int = 120,
    ):
        self.stream_url = stream_url
        self.buffer_dir = buffer_dir
        self.clips_dir = clips_dir
        self.segment_duration = segment_duration
        self.max_buffer_seconds = max_buffer_seconds

        os.makedirs(self.buffer_dir, exist_ok=True)
        os.makedirs(self.clips_dir, exist_ok=True)

        self.running = False
        self.process: Optional[subprocess.Popen] = None
        self._cleaner_thread: Optional[threading.Thread] = None

    def start(self):
        """Starts streamlink piped into ffmpeg segmenter."""
        self.running = True
        self._clean_buffer_dir()

        # Command: streamlink -> ffmpeg segments
        # streamlink output piped directly to ffmpeg to create timestamped segments
        streamlink_cmd = [
            "streamlink",
            self.stream_url,
            "best",
            "-O",
            "--loglevel", "error",
        ]

        # FFmpeg reads from pipe and writes rolling segments
        segment_pattern = os.path.join(self.buffer_dir, "seg_%06d.ts")
        ffmpeg_cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            "-i", "pipe:0",
            "-c", "copy",
            "-f", "segment",
            "-segment_time", str(self.segment_duration),
            "-reset_timestamps", "1",
            segment_pattern,
        ]

        logger.info(f"Starting stream capture for: {self.stream_url}")

        try:
            p_streamlink = subprocess.Popen(
                streamlink_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            self.process = subprocess.Popen(
                ffmpeg_cmd,
                stdin=p_streamlink.stdout,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            # Allow p_streamlink to receive a SIGPIPE if ffmpeg exits
            if p_streamlink.stdout:
                p_streamlink.stdout.close()

            # Start cleaner thread to keep only the last max_buffer_seconds of chunks
            self._cleaner_thread = threading.Thread(target=self._buffer_cleaner, daemon=True)
            self._cleaner_thread.start()

        except Exception as e:
            logger.error(f"Failed to start stream recorder: {e}")
            self.stop()

    def stop(self):
        """Stops the recorder and cleans up processes."""
        self.running = False
        if self.process:
            try:
                self.process.terminate()
            except Exception:
                pass
            self.process = None
        logger.info("Stream recorder stopped.")

    def _clean_buffer_dir(self):
        """Empties buffer directory."""
        if os.path.exists(self.buffer_dir):
            for f in os.listdir(self.buffer_dir):
                if f.endswith(".ts") or f.endswith(".txt"):
                    try:
                        os.remove(os.path.join(self.buffer_dir, f))
                    except Exception:
                        pass

    def _buffer_cleaner(self):
        """Removes segments older than max_buffer_seconds to avoid filling disk."""
        max_files = (self.max_buffer_seconds // self.segment_duration) + 4
        while self.running:
            try:
                files = sorted(
                    [
                        os.path.join(self.buffer_dir, f)
                        for f in os.listdir(self.buffer_dir)
                        if f.startswith("seg_") and f.endswith(".ts")
                    ],
                    key=os.path.getmtime,
                )
                if len(files) > max_files:
                    to_delete = files[:-max_files]
                    for f in to_delete:
                        try:
                            os.remove(f)
                        except Exception:
                            pass
            except Exception as e:
                logger.debug(f"Buffer cleaner error: {e}")
            time.sleep(self.segment_duration)

    def extract_recent_clip(self, clip_duration_sec: int = 35) -> Optional[str]:
        """
        Slices the most recent `clip_duration_sec` seconds from the buffer.
        Returns the absolute path to the cut MP4.
        """
        # Wait a few seconds for trailing segments to finish writing
        time.sleep(3)

        files = sorted(
            [
                os.path.join(self.buffer_dir, f)
                for f in os.listdir(self.buffer_dir)
                if f.startswith("seg_") and f.endswith(".ts")
            ],
            key=os.path.getmtime,
        )

        needed_segments_count = (clip_duration_sec // self.segment_duration) + 2
        if len(files) < 3:
            logger.warning("Not enough segments in buffer yet to create a clip.")
            return None

        selected_files = files[-needed_segments_count:]
        logger.info(f"Extracting clip from {len(selected_files)} segments...")

        # Create concat list file
        concat_list_path = os.path.join(self.buffer_dir, f"concat_{int(time.time())}.txt")
        with open(concat_list_path, "w", encoding="utf-8") as f:
            for seg in selected_files:
                # Escape path for ffmpeg concat
                safe_path = seg.replace("\\", "/")
                f.write(f"file '{safe_path}'\n")

        timestamp_str = time.strftime("%Y%m%d_%H%M%S")
        raw_clip_path = os.path.join(self.clips_dir, f"raw_clip_{timestamp_str}.mp4")

        # Concat without re-encoding (-c copy) for maximum speed (<2 seconds)
        cmd = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel", "error",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_list_path,
            "-c", "copy",
            raw_clip_path,
        ]

        res = subprocess.run(cmd, capture_output=True, text=True)
        try:
            os.remove(concat_list_path)
        except Exception:
            pass

        if res.returncode == 0 and os.path.exists(raw_clip_path) and os.path.getsize(raw_clip_path) > 0:
            logger.info(f"Raw clip created successfully: {raw_clip_path}")
            return os.path.abspath(raw_clip_path)
        else:
            logger.error(f"Failed to concat clip: {res.stderr}")
            return None
