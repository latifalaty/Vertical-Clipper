# Vertical Clipper

Turns a long 16:9 video into 9:16 clips that follow the speaker's face. 100% free/open source, runs locally.

## Setup (once)
1. Install **Python 3.9+** (python.org) and **FFmpeg**
   - Windows: `winget install ffmpeg` · Mac: `brew install ffmpeg` · Linux: `sudo apt install ffmpeg`
2. In this folder run: `pip install -r requirements.txt`

## Use
1. Run `python app.py`, then open http://localhost:8000
2. Paste a YouTube link or upload a video. Clips are auto-detected (scene changes, 20–60s each).
3. For each clip: change start/end (type a time, use ±1s, or pause the video and press "⏱ here"), press Preview.
4. "Export this clip" or "Export all" (zip). Files are 720x1280 MP4s.

## How it works
- `clipper.py` – scene-cut detection (colour histograms), face tracking (OpenCV Haar), smoothed crop path, FFmpeg encode.
- `app.py` – small Flask server. `static/index.html` – the UI.
- Face tracking follows the largest face, glides smoothly, and holds position when no face is visible.


