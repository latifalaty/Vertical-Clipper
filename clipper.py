"""Video logic: probing, auto-segmentation, face tracking, 9:16 rendering."""
import math
import subprocess
import cv2
import numpy as np

FACE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
OUT_W, OUT_H = 720, 1280


def probe(path):
    c = cv2.VideoCapture(path)
    fps = c.get(cv2.CAP_PROP_FPS) or 30
    info = dict(fps=fps, duration=c.get(cv2.CAP_PROP_FRAME_COUNT) / fps,
                width=int(c.get(cv2.CAP_PROP_FRAME_WIDTH)), height=int(c.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    c.release()
    return info


def find_segments(path, info, min_len=20, max_len=60, step=0.5, threshold=0.6):
    """Detect scene cuts (colour-histogram change), then merge/split to usable clip lengths."""
    cap, fps = cv2.VideoCapture(path), info["fps"]
    skip, cuts, prev, i = max(1, int(fps * step)), [0.0], None, 0
    while cap.grab():
        if i % skip == 0:
            ok, frame = cap.retrieve()
            if ok:
                hsv = cv2.cvtColor(cv2.resize(frame, (160, 90)), cv2.COLOR_BGR2HSV)
                hist = cv2.calcHist([hsv], [0, 1], None, [16, 16], [0, 180, 0, 256])
                cv2.normalize(hist, hist)
                if prev is not None and cv2.compareHist(prev, hist, cv2.HISTCMP_CORREL) < threshold:
                    cuts.append(i / fps)
                prev = hist
        i += 1
    cap.release()
    end = info["duration"]
    merged, start = [], 0.0
    for c in cuts[1:]:
        if c - start >= min_len:
            merged.append((start, c))
            start = c
    if end - start > 0.5:
        if merged and end - start < min_len:
            merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))
    clips = []
    for s, e in merged:  # split anything too long into equal parts
        n = max(1, math.ceil((e - s) / max_len))
        size = (e - s) / n
        clips += [(round(s + k * size, 2), round(s + (k + 1) * size, 2)) for k in range(n)]
    return clips


def face_track(path, start, end, info):
    """Return a smoothed crop-centre x (source pixels) for every frame of the clip."""
    fps, w = info["fps"], info["width"]
    n, every, scale = int((end - start) * fps), max(1, int(info["fps"] / 3)), 480 / info["width"]
    cap = cv2.VideoCapture(path)
    cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000)
    known = []
    for i in range(n):
        ok, frame = cap.read()
        if not ok:
            break
        if i % every == 0:
            gray = cv2.cvtColor(cv2.resize(frame, None, fx=scale, fy=scale), cv2.COLOR_BGR2GRAY)
            faces = FACE.detectMultiScale(gray, 1.1, 5, minSize=(24, 24))
            if len(faces):
                x, _, fw, fh = max(faces, key=lambda b: b[2] * b[3])  # largest face
                known.append((i, (x + fw / 2) / scale))
    cap.release()
    if not known:
        return np.full(n, w / 2)
    idx, xs = zip(*known)
    path_x = np.interp(np.arange(n), idx, xs)  # holds last known position when no face is found
    k = max(3, int(fps * 1.5))  # ~1.5s moving average = smooth camera, no jitter
    padded = np.pad(path_x, k // 2, mode="edge")
    return np.convolve(padded, np.ones(k) / k, mode="valid")[:n]


def render_vertical(path, start, end, out_path, info):
    fps, w, h = info["fps"], info["width"], info["height"]
    cw = int(h * 9 / 16) // 2 * 2
    xs = face_track(path, start, end, info)
    cap = cv2.VideoCapture(path)
    cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000)
    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24",
         "-s", f"{OUT_W}x{OUT_H}", "-r", str(fps), "-i", "-",
         "-ss", str(start), "-t", str(end - start), "-i", path,
         "-map", "0:v", "-map", "1:a?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", out_path],
        stdin=subprocess.PIPE)
    for cx in xs:
        ok, frame = cap.read()
        if not ok:
            break
        x = int(np.clip(cx - cw / 2, 0, w - cw))
        ff.stdin.write(cv2.resize(frame[:, x:x + cw], (OUT_W, OUT_H)).tobytes())
    ff.stdin.close()
    ff.wait()
    cap.release()
