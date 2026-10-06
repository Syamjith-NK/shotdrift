"""Decode a video to small grayscale frames with ffmpeg, and nothing else.

Deliberately no OpenCV and no torch. ffmpeg is already on every machine that
edits video, and a tool that needs a 2 GB wheel to measure a camera move will
not get run.

Everything downstream works in NORMALISED units - fractions of the frame width -
so a threshold means the same thing on a 720p proxy and a 4K master. Reporting
pixels at the analysis resolution would make every bound silently resolution
dependent, which is how a measurement tool ends up with magic numbers.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass

import numpy as np


class FFmpegMissing(RuntimeError):
    pass


class DecodeError(RuntimeError):
    pass


@dataclass
class Clip:
    frames: np.ndarray      # (n, h, w) float32 in 0..1
    width: int              # analysis width  (px)
    height: int             # analysis height (px)
    src_width: int          # original width  (px)
    src_height: int         # original height (px)
    fps: float
    duration: float

    def __len__(self) -> int:
        return int(self.frames.shape[0])


def _exe(name: str) -> str:
    p = shutil.which(name)
    if not p:
        raise FFmpegMissing(
            f"{name} not found on PATH. shotdrift measures video, so it needs "
            "ffmpeg: `brew install ffmpeg` or `apt install ffmpeg`."
        )
    return p


def probe(path: str) -> dict:
    out = subprocess.run(
        [_exe("ffprobe"), "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,avg_frame_rate,nb_read_packets",
         "-show_entries", "format=duration", "-of", "json", path],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise DecodeError(f"ffprobe could not read {path}: {out.stderr.strip()[:300]}")
    d = json.loads(out.stdout or "{}")
    streams = d.get("streams") or []
    if not streams:
        raise DecodeError(f"{path} has no video stream.")
    s = streams[0]
    num, _, den = (s.get("avg_frame_rate") or "0/1").partition("/")
    try:
        fps = float(num) / float(den) if float(den) else 0.0
    except (ValueError, ZeroDivisionError):
        fps = 0.0
    try:
        dur = float((d.get("format") or {}).get("duration") or 0.0)
    except ValueError:
        dur = 0.0
    return {"width": int(s["width"]), "height": int(s["height"]), "fps": fps, "duration": dur}


def load(path: str, max_side: int = 512, sample_fps: float | None = None,
         start: float = 0.0, duration: float | None = None,
         max_frames: int = 600) -> Clip:
    """Decode to grayscale. `sample_fps=None` keeps the clip's own rate.

    Camera motion is measured BETWEEN ADJACENT FRAMES, so dropping the rate
    changes what is being measured, not just the cost of measuring it. The
    default therefore keeps every frame; `--sample-fps` exists for long clips
    and says so in the report.
    """
    meta = probe(path)
    sw, sh = meta["width"], meta["height"]
    if sw <= 0 or sh <= 0:
        raise DecodeError(f"{path} reports a {sw}x{sh} frame size.")

    scale = min(1.0, max_side / max(sw, sh))
    w = max(16, int(round(sw * scale)))
    h = max(16, int(round(sh * scale)))
    w -= w % 2
    h -= h % 2

    cmd = [_exe("ffmpeg"), "-v", "error"]
    if start > 0:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", path]
    if duration is not None:
        cmd += ["-t", f"{duration:.3f}"]
    vf = [f"scale={w}:{h}:flags=bilinear"]
    if sample_fps:
        vf.insert(0, f"fps={sample_fps:g}")
    cmd += ["-vf", ",".join(vf), "-frames:v", str(max_frames),
            "-pix_fmt", "gray", "-f", "rawvideo", "-"]

    out = subprocess.run(cmd, capture_output=True)
    if out.returncode != 0:
        raise DecodeError(f"ffmpeg failed on {path}: {out.stderr.decode(errors='replace').strip()[:300]}")

    buf = np.frombuffer(out.stdout, dtype=np.uint8)
    stride = w * h
    n = buf.size // stride
    if n < 2:
        raise DecodeError(
            f"{path} decoded to {n} frame(s) at {w}x{h}. Camera motion needs at "
            "least two frames; check the file is not truncated and that any "
            "--start/--duration window actually contains picture."
        )
    frames = buf[: n * stride].reshape(n, h, w).astype(np.float32) / 255.0
    eff_fps = float(sample_fps) if sample_fps else meta["fps"]
    return Clip(frames=frames, width=w, height=h, src_width=sw, src_height=sh,
                fps=eff_fps, duration=meta["duration"])
