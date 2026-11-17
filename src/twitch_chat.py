"""
Twitch Chat Velocity Monitor
Connects anonymously to Twitch IRC (no OAuth / API credentials needed).
Tracks chat message velocity over sliding time windows and fires an event
when a sudden burst/spike occurs (indicating a viral/hype moment).
"""

import socket
import threading
import time
import random
import logging
from collections import deque
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class TwitchChatMonitor:
    def __init__(
        self,
        channel: str,
        on_spike: Callable[[float, int, float], None],
        window_sec: int = 10,
        baseline_sec: int = 60,
        spike_multiplier: float = 3.0,
        min_spike_messages: int = 15,
        cooldown_sec: int = 180,
    ):
        self.channel = channel.lower().replace("#", "")
        self.on_spike = on_spike
        self.window_sec = window_sec
        self.baseline_sec = baseline_sec
        self.spike_multiplier = spike_multiplier
        self.min_spike_messages = min_spike_messages
        self.cooldown_sec = cooldown_sec

        self.running = False
        self.sock: Optional[socket.socket] = None
        self.message_timestamps: deque = deque()
        self.history_windows: deque = deque(maxlen=max(2, baseline_sec // window_sec))
        self.last_spike_time = 0.0
        self._thread: Optional[threading.Thread] = None

    def start(self):
        """Starts the IRC chat listener in a background thread."""
        self.running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info(f"Twitch Chat Monitor started for #{self.channel} (Anonymous mode)")

    def stop(self):
        """Stops the chat listener."""
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
        logger.info(f"Twitch Chat Monitor stopped for #{self.channel}")

    def _connect(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(15)
        s.connect(("irc.chat.twitch.tv", 6667))
        nick = f"justinfan{random.randint(10000, 99999)}"
        s.send(f"PASS oauth:dummy\r\n".encode("utf-8"))
        s.send(f"NICK {nick}\r\n".encode("utf-8"))
        s.send(f"JOIN #{self.channel}\r\n".encode("utf-8"))
        return s

    def _run(self):
        last_eval_time = time.time()
        buf = ""

        while self.running:
            try:
                if not self.sock:
                    self.sock = self._connect()
                    logger.info(f"Connected to Twitch IRC for channel: {self.channel}")

                try:
                    data = self.sock.recv(4096).decode("utf-8", errors="ignore")
                except socket.timeout:
                    data = ""

                now = time.time()

                if data:
                    buf += data
                    lines = buf.split("\r\n")
                    buf = lines.pop()

                    for line in lines:
                        if line.startswith("PING"):
                            self.sock.send("PONG :tmi.twitch.tv\r\n".encode("utf-8"))
                        elif "PRIVMSG" in line:
                            self.message_timestamps.append(now)

                # Periodic evaluation of chat velocity
                if now - last_eval_time >= self.window_sec:
                    self._evaluate_velocity(now)
                    last_eval_time = now

            except Exception as e:
                if self.running:
                    logger.warning(f"IRC connection error: {e}. Reconnecting in 5s...")
                    if self.sock:
                        try:
                            self.sock.close()
                        except Exception:
                            pass
                        self.sock = None
                    time.sleep(5)

    def _evaluate_velocity(self, now: float):
        # Prune messages older than baseline window
        cutoff = now - self.baseline_sec
        while self.message_timestamps and self.message_timestamps[0] < cutoff:
            self.message_timestamps.popleft()

        # Count messages in the latest window
        window_cutoff = now - self.window_sec
        current_window_msgs = sum(1 for t in self.message_timestamps if t >= window_cutoff)

        # Baseline mean
        if self.history_windows:
            baseline_mean = sum(self.history_windows) / len(self.history_windows)
        else:
            baseline_mean = max(1.0, float(current_window_msgs))

        # Check for spike
        is_spike = (
            current_window_msgs >= self.min_spike_messages
            and current_window_msgs >= (baseline_mean * self.spike_multiplier)
            and (now - self.last_spike_time) > self.cooldown_sec
        )

        logger.debug(
            f"Chat Velocity: {current_window_msgs} msgs/{self.window_sec}s | "
            f"Baseline: {baseline_mean:.1f} | Spike: {is_spike}"
        )

        if is_spike:
            self.last_spike_time = now
            logger.info(
                f"🔥 CHAT EXPLODED! {current_window_msgs} msgs in {self.window_sec}s "
                f"(Baseline: {baseline_mean:.1f}, Multiplier: {current_window_msgs / max(1, baseline_mean):.2f}x)"
            )
            try:
                self.on_spike(now, current_window_msgs, baseline_mean)
            except Exception as e:
                logger.error(f"Error executing on_spike callback: {e}")

        # Record this window to history
        self.history_windows.append(current_window_msgs)
