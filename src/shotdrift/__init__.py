"""shotdrift - measure whether a video holds the camera move it was given.

AI video is asked for a camera move and is not obliged to deliver one. The usual
check is a person watching sixty clips. This measures the camera path out of the
pixels - pan, zoom, roll, frame by frame. It estimates 2D image motion; it does
not recover a physical 3D camera trajectory.

    from shotdrift import measure
    r = measure("take_07.mp4", expect="push-in")
    print(r.verdict, [f.code for f in r.findings])

Frames already in memory - inside a generation graph, say, where the clip was
never written to disk - skip ffmpeg entirely:

    from shotdrift import measure_frames, report
    r = measure_frames(image_batch, expect="push-in")   # (n, h, w, c), 0..1
    print(report(r))
"""

from __future__ import annotations

from .core import Result, Shot, measure, measure_frames, report

__version__ = "0.2.2"
__all__ = ["measure", "measure_frames", "report", "Result", "Shot", "__version__"]
