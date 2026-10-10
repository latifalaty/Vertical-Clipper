"""Run with: python -m pytest tests  (needs ffmpeg). Builds a tiny 2-scene video and checks the pipeline."""
import os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import clipper


def make_video(path):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=red:s=640x360:d=6:r=25", "-f", "lavfi", "-i", "testsrc=s=640x360:d=6:r=25",
        "-f", "lavfi", "-i", "sine=d=12", "-filter_complex", "[0:v][1:v]concat=n=2:v=1[v]",
        "-map", "[v]", "-map", "2:a", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-shortest", path], check=True)


def test_pipeline(tmp_path):
    src, out = str(tmp_path / "src.mp4"), str(tmp_path / "out.mp4")
    make_video(src)
    info = clipper.probe(src)
    assert abs(info["duration"] - 12) < 0.5
    clips = clipper.find_segments(src, info, min_len=3, max_len=60)
    assert len(clips) == 2 and abs(clips[0][1] - 6) < 1
    clipper.render_vertical(src, 0, 5, out, info)
    probe = clipper.probe(out)
    assert (probe["width"], probe["height"]) == (720, 1280)
    assert abs(probe["duration"] - 5) < 0.5
