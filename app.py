"""Local web server. Run: python app.py  ->  http://localhost:8000"""
import io, os, re, threading, time, uuid, zipfile
from flask import Flask, abort, jsonify, request, send_file
import yt_dlp
import clipper

app = Flask(__name__, static_folder="static", static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024**3  # reject uploads over 4 GB
YOUTUBE = re.compile(r"^https?://(www\.|m\.)?(youtube\.com|youtu\.be)/", re.I)
MAX_CLIPS_PER_EXPORT, MAX_AGE_H = 50, 24
WORK = os.path.join(os.path.dirname(__file__), "workspace")
os.makedirs(WORK, exist_ok=True)
def cleanup_old_files():
    """Delete downloads/renders older than MAX_AGE_H so the disk does not fill up."""
    for name in os.listdir(WORK):
        f = os.path.join(WORK, name)
        if time.time() - os.path.getmtime(f) > MAX_AGE_H * 3600:
            os.remove(f)


projects = {}  # id -> {status, message, path, info, clips}


def process(pid, url=None):
    p = projects[pid]
    try:
        if url:
            p["message"] = "Downloading from YouTube..."
            opts = {"outtmpl": os.path.join(WORK, pid + ".%(ext)s"), "merge_output_format": "mp4", "quiet": True, "noplaylist": True,
                    "format": "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b"}
            with yt_dlp.YoutubeDL(opts) as y:
                y.download([url])
            p["path"] = os.path.join(WORK, pid + ".mp4")
        p["message"] = "Finding natural clip boundaries..."
        p["info"] = clipper.probe(p["path"])
        p["clips"] = clipper.find_segments(p["path"], p["info"])
        p["status"] = "ready"
    except Exception as e:
        p["status"], p["message"] = "error", str(e)


@app.route("/")
def index():
    return app.send_static_file("index.html")


@app.post("/api/load")
def load():
    url = request.form.get("url", "").strip()
    has_file = "file" in request.files and request.files["file"].filename
    if url and not has_file and not YOUTUBE.match(url):
        return jsonify(error="Only YouTube links are supported. Use the upload for other videos."), 400
    pid = uuid.uuid4().hex[:8]
    projects[pid] = dict(status="working", message="Starting...")
    if has_file:
        path = os.path.join(WORK, pid + ".mp4")
        request.files["file"].save(path)
        projects[pid]["path"] = path
        url = None
    elif not url:
        return jsonify(error="Provide a YouTube URL or a video file"), 400
    threading.Thread(target=process, args=(pid, url), daemon=True).start()
    return jsonify(id=pid)


@app.get("/api/status/<pid>")
def status(pid):
    p = projects.get(pid) or abort(404)
    return jsonify(status=p["status"], message=p["message"] if "message" in p else "",
                   info=p.get("info"), clips=p.get("clips"))


@app.get("/api/video/<pid>")
def video(pid):
    projects.get(pid) or abort(404)
    return send_file(projects[pid]["path"], conditional=True)  # supports seeking



@app.post("/api/export/<pid>")
def export(pid):
    print(f"[EXPORT] Requested pid: {pid}")
    print(f"[EXPORT] Known projects: {list(projects.keys())}")

    p = projects.get(pid)
    if p is None:
        print(f"[EXPORT ERROR] Project {pid} not found")
        return jsonify(error="Project not found. Please load the video again."), 404

    print(f"[EXPORT] Project status: {p.get('status')}")
    print(f"[EXPORT] Project message: {p.get('message')}")

    if p.get("status") != "ready":
        return jsonify(
            error="Video is not ready for export",
            status=p.get("status"),
            message=p.get("message")
        ), 409

    clips = (request.json or {}).get("clips", [])[:MAX_CLIPS_PER_EXPORT]
    if not clips:
        return jsonify(error="No clips selected for export"), 400

    # Keep the existing export logic below this point.
    dur = p["info"]["duration"]
    for c in clips:
        c["start"] = max(0.0, float(c["start"]))
        c["end"] = min(dur, float(c["end"]))
        if c["end"] - c["start"] < 1:
            return jsonify(error="A clip must be at least 1 second long"), 400

    outs = []
    for c in clips:
        out = os.path.join(WORK, f"{pid}_clip_{c['n']:02d}.mp4")
        clipper.render_vertical(
            p["path"], float(c["start"]), float(c["end"]), out, p["info"]
        )
        outs.append(out)

    if len(outs) == 1:
        return send_file(
            outs[0],
            as_attachment=True,
            download_name=f"clip_{clips[0]['n']:02d}.mp4"
        )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for c, o in zip(clips, outs):
            z.write(o, f"clip_{c['n']:02d}.mp4")

    buf.seek(0)
    return send_file(
        buf,
        as_attachment=True,
        download_name="vertical_clips.zip",
        mimetype="application/zip"
    )

if __name__ == "__main__":
    cleanup_old_files()
    print("Open http://localhost:8000 in your browser")
    app.run(host="127.0.0.1", port=8000, threaded=True)  # local only
