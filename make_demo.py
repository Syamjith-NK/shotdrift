#!/usr/bin/env python3
"""Build the clip used in the README, so its output can be re-derived.

The example at the top of the README is the first thing anyone reads, and it
quoted numbers from a file that was not in the repository - unreproducible, which
is a poor opening for a tool whose whole argument is that it measures things.

This writes `pan_demo.mp4`: a clean, eased pan across a textured plate. It is a
perfectly good camera move and it is NOT a push-in, which is the point the example
is making - `--expect push-in` must report that the move did not happen while the
motion itself comes back clean.

    python make_demo.py && shotdrift pan_demo.mp4 --expect push-in
"""

from __future__ import annotations

import subprocess
import sys

import numpy as np
from PIL import Image

W = H = 720
OUT = 1280, 720
FRAMES, FPS = 97, 24


def plate(w=1600, h=900, seed=11):
    rng = np.random.default_rng(seed)
    low = rng.random((h // 12, w // 12)).astype(np.float32)
    img = np.asarray(
        Image.fromarray((low * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC),
        dtype=np.float32) / 255.0
    yy, xx = np.mgrid[0:h, 0:w]
    detail = 0.18 * np.sin(xx / 7.0) * np.cos(yy / 9.0)
    return np.clip(img * 0.74 + rng.random((h, w)).astype(np.float32) * 0.14 + detail,
                   0, 1).astype(np.float32)


def main() -> int:
    p = plate()
    ph, pw = p.shape
    cw, ch = 900, 506                       # 16:9 window travelling across the plate
    t = np.linspace(0, 1, FRAMES)
    ease = t * t * (3 - 2 * t)              # smooth start and stop, as a real move has
    x0 = (pw - cw) * ease

    ff = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray",
         "-s", f"{OUT[0]}x{OUT[1]}", "-r", str(FPS), "-i", "-",
         "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", "pan_demo.mp4"],
        stdin=subprocess.PIPE)
    for x in x0:
        xi = int(round(x))
        crop = p[(ph - ch) // 2:(ph - ch) // 2 + ch, xi:xi + cw]
        im = Image.fromarray((crop * 255).astype(np.uint8)).resize(OUT, Image.BICUBIC)
        ff.stdin.write(np.asarray(im, dtype=np.uint8).tobytes())
    ff.stdin.close()
    if ff.wait() != 0:
        print("ffmpeg failed", file=sys.stderr)
        return 1
    print(f"wrote pan_demo.mp4 - {FRAMES} frames @ {FPS} fps, {OUT[0]}x{OUT[1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
