"""
YouTube Live Chat Velocity Monitor
Uses pytchat to connect to public YouTube livestream chat in real time.
Tracks chat velocity and triggers when a viral burst happens.
"""

import threading
import time
import logging
from collections import deque
from typing import Callable, Optional
import pytchat

logger = logging.getLogger(__name__)


class YouTubeChatMonitor:
    def __init__(
        self,
        video_id: str,
        on_spike: Callable[[float, int, float], None],
        window_sec: int = 10,
        baseline_sec: int = 60,
        spike_multiplier: float = 3.0,
        min_spike_messages: int = 15,
        cooldown_sec: int = 180,
    ):
        self.video_id = video_id
        self.on_spike = on_spike
        self.window_sec = window_sec
        self.baseline_sec = baseline_sec
        self.spike_multiplier = spike_multiplier
        self.min_spike_messages = min_spike_messages
        self.cooldown_sec = cooldown_sec

        self.running = False
        self.connected = False
        self.chat = None
        self.message_timestamps: deque = deque()
        self.history_windows: deque = deque(maxlen=max(2, baseline_sec // window_sec))
        self.last_spike_time = 0.0
        self._thread: Optional[threading.Thread] = None

    def start(self):
        self.running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info(f"YouTube Chat Monitor started for video: {self.video_id}")

    def stop(self):
        self.running = False
        if self.chat:
            try:
                self.chat.terminate()
            except Exception:
                pass
        logger.info(f"YouTube Chat Monitor stopped for video: {self.video_id}")

    def _run(self):
        try:
            self.chat = pytchat.create(video_id=self.video_id, interruptable=False)
            self.connected = True
        except Exception as e:
            self.connected = False
            logger.error(f"Failed to attach to YouTube live chat: {e}")
            return

        last_eval_time = time.time()

        while self.running and self.chat.is_alive():
            now = time.time()
            try:
                for c in self.chat.get().sync_items():
                    self.message_timestamps.append(now)

                if now - last_eval_time >= self.window_sec:
                    self._evaluate_velocity(now)
                    last_eval_time = now

                time.sleep(0.5)
            except Exception as e:
                logger.warning(f"Error reading YouTube chat: {e}")
                time.sleep(2)

    def _evaluate_velocity(self, now: float):
        cutoff = now - self.baseline_sec
        while self.message_timestamps and self.message_timestamps[0] < cutoff:
            self.message_timestamps.popleft()

        window_cutoff = now - self.window_sec
        current_window_msgs = sum(1 for t in self.message_timestamps if t >= window_cutoff)

        if self.history_windows:
            baseline_mean = sum(self.history_windows) / len(self.history_windows)
        else:
            baseline_mean = max(1.0, float(current_window_msgs))

        is_spike = (
            current_window_msgs >= self.min_spike_messages
            and current_window_msgs >= (baseline_mean * self.spike_multiplier)
            and (now - self.last_spike_time) > self.cooldown_sec
        )

        logger.debug(
            f"YT Chat Velocity: {current_window_msgs} msgs/{self.window_sec}s | "
            f"Baseline: {baseline_mean:.1f} | Spike: {is_spike}"
        )

        if is_spike:
            self.last_spike_time = now
            logger.info(
                f"🔥 YOUTUBE CHAT EXPLODED! {current_window_msgs} msgs in {self.window_sec}s "
                f"(Baseline: {baseline_mean:.1f}, Multiplier: {current_window_msgs / max(1, baseline_mean):.2f}x)"
            )
            try:
                self.on_spike(now, current_window_msgs, baseline_mean)
            except Exception as e:
                logger.error(f"Error executing on_spike callback: {e}")

        self.history_windows.append(current_window_msgs)
