# 🎮 GTA 6 Live Stream Auto-Clipper & YouTube Shorts Bot

> **Autonomous Real-Time Viral Moment Detection, Vertical 9:16 Shorts Formatting, and YouTube Auto-Uploader**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://python.org)
[![FFmpeg](https://img.shields.io/badge/FFmpeg-Enabled-green.svg)](https://ffmpeg.org)
[![Streamlink](https://img.shields.io/badge/Streamlink-Live-orange.svg)](https://streamlink.github.io)
[![License](https://img.shields.io/badge/License-MIT-purple.svg)](LICENSE)

---

## 🚀 Overview

Most gaming clip channels fail because they wait for an 8-hour livestream to end, download the massive VOD overnight, and upload hours late—after the algorithm has already crowned the earliest uploads.

**GTA 6 Auto-Clipper solves this with a zero-latency real-time pipeline:**
1. **Auto-Discovery:** Automatically scans Twitch and YouTube for active, high-traffic GTA 6 livestreams. If no stream meets the reliability threshold (e.g. $\ge 500$ viewers), it cleanly ends the session.
2. **Chat Velocity Spike Detection:** Connects anonymously to live chat (Twitch IRC / YouTube Chat WebSocket) without requiring logins or API keys. When chat burst velocity jumps (e.g. $3\times$ baseline), an epic moment or glitch just happened.
3. **Instant Slicing:** Extracts the preceding 30–60 seconds directly from a rolling circular buffer in seconds with stream copy (`-c copy`) without re-encoding.
4. **9:16 Shorts Reformatting:** Converts standard 16:9 widescreen into aesthetic vertical Shorts format with a blurred backdrop and centered crisp gameplay.
5. **Auto-Upload to YouTube:** Automatically publishes the clip as a YouTube Short tagged `#GTA6 #Shorts` using the official YouTube Data API v3.
6. **2-Hour Automation:** Runs on a recurring 2-hour schedule starting automatically.

---

## 🏗️ Architecture

```
                 [Twitch / YouTube Live Stream]
                               │
            ┌──────────────────┴──────────────────┐
            ▼                                     ▼
     [Streamlink]                      [Chat Velocity Monitor]
(Rolling Circular Buffer)             (Anonymous Twitch IRC / pytchat)
            │                                     │
            │                           Chat Spike Detected! 🔥
            │                         (e.g., 3x rolling baseline)
            │                                     │
            └──────────────────┬──────────────────┘
                               ▼
                    [Instant Buffer Slicing]
              (Extracts 25s pre-spike + 10s post-spike)
                               │
                               ▼
               [FFmpeg 9:16 Vertical Converter]
          (Blurred backdrop + centered gameplay)
                               │
                               ▼
                   [YouTube Data API v3]
         (Auto-uploads to YouTube Shorts with SEO tags)
```

---

## 📦 Installation & Setup

### 1. Prerequisites
- **Python 3.10+**
- **FFmpeg** installed and added to your system `PATH` (Verify with `ffmpeg -version`).

### 2. Install Dependencies
```bash
git clone https://github.com/your-username/gta6-stream-autoclipper.git
cd gta6-stream-autoclipper
pip install -r requirements.txt
```

### 3. YouTube API Authentication (Optional for auto-upload)
If you want automatic uploads directly to your YouTube channel:
1. Go to [Google Cloud Console](https://console.cloud.google.com/).
2. Create a project and enable the **YouTube Data API v3**.
3. Create an **OAuth 2.0 Client ID** (Application Type: *Desktop app*).
4. Download the credentials JSON and save it as `client_secret.json` in the root folder.
5. On the first upload, a browser window will prompt you to authorize your YouTube channel once. The access token is saved securely in `token.json`.

*(If `client_secret.json` is omitted, clips are still automatically cut, rendered to 9:16 vertical video, and saved locally inside the `clips/` directory).*

---

## ⚙️ Configuration (`config.yaml`)

Customize stream discovery, spike sensitivity, and video layouts in `config.yaml`:

```yaml
discovery:
  enabled: true
  game_query: "Grand Theft Auto VI"
  fallback_game_query: "Grand Theft Auto V" # Used for testing before GTA 6 launch
  min_viewers: 500                          # Only latch onto streams with >= 500 viewers
  platforms: ["twitch", "youtube"]

clipping:
  spike_multiplier: 3.0    # Trigger clip when chat is 3x faster than baseline
  min_spike_messages: 15  # Minimum msgs in window
  window_sec: 10          # Velocity evaluation window
  baseline_sec: 60        # Rolling baseline window
  clip_duration_sec: 35   # Total length of output Short
  cooldown_sec: 180       # 3-minute cooldown between clips

video:
  width: 1080
  height: 1920
  layout_mode: "blur_backdrop"

youtube:
  enabled: true
  privacy_status: "public" # "public", "unlisted", or "private"
```

---

## 🚀 Running the Project

### A. Run a Single Detection & Clipping Session
```bash
python -m src.main
```
* If no stream is currently live with $\ge 500$ viewers, it logs the check and **exits cleanly in seconds**.
* If an active stream is found, it monitors, clips, and uploads.

### B. Run on a 2-Hour Schedule Starting Tomorrow
```bash
python scheduler.py
```
*(To test the schedule immediately without waiting for tomorrow, run `python scheduler.py --now`).*

### C. Windows Background Task (Native Task Scheduler)
Double-click `setup_windows_task.bat` (or run in terminal). This registers a Windows scheduled task named **`GTA6_AutoClipper`** that automatically executes `run_clipper.bat` every 2 hours in the background.

---

## 📁 Project Structure

```text
gta6-stream-autoclipper/
├── config.yaml             # Main configuration (discovery, thresholds, YT metadata)
├── requirements.txt        # Python package dependencies
├── scheduler.py            # Automated 2-hour interval scheduler
├── setup_windows_task.bat  # 1-click Windows Task Scheduler installer
├── run_clipper.bat         # Single-session runner script
├── .gitignore              # Ignores temp video buffers, clips, and OAuth keys
├── .env.example            # Environment template
├── src/
│   ├── discovery.py        # Stream discovery (Twitch GQL + YouTube live search)
│   ├── twitch_chat.py      # Anonymous Twitch IRC chat velocity burst tracker
│   ├── youtube_chat.py     # YouTube live chat monitor using pytchat
│   ├── recorder.py         # Streamlink & rolling segment circular buffer
│   ├── processor.py        # FFmpeg vertical 9:16 Shorts reformatting
│   ├── uploader.py         # YouTube Data API v3 uploader
│   └── main.py             # Orchestrator session controller
├── buffer/                 # Temporary rolling video chunks (.ts)
└── clips/                  # Rendered 9:16 YouTube Shorts (.mp4)
```

---

## 🛡️ License
MIT License. Built for creators and developers.
