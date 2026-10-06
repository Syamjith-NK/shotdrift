"""shotdrift - measure whether a video holds the camera move it was given.

AI video is asked for a camera move and is not obliged to deliver one. The usual
check is a person watching sixty clips. This measures the camera path out of the
pixels - pan, zoom, roll, frame by frame - and reports whether one physical camera
could have produced it.

    from shotdrift import measure
    r = measure("take_07.mp4", expect="push-in")
    print(r.verdict, [f.code for f in r.findings])
"""

from __future__ import annotations

from dataclasses import dataclass

__version__ = "0.1.0"
__all__ = ["measure", "Result", "__version__"]


@dataclass
class Result:
    clip: str
    path: object
    findings: list
    verdict: str
    expect: object | None = None

    @property
    def ok(self) -> bool:
        """Clean, and - if a move was declared - that move was held."""
        return self.verdict == "clean" and (self.expect is None or self.expect.ok)


def measure(clip: str, expect: str | None = None, *, max_side: int = 512,
            grid: int = 4, start: float = 0.0, duration: float | None = None,
            sample_fps: float | None = None, anchors: int = 4) -> Result:
    from .expect import check as _check
    from .frames import load as _load
    from .path import analyse as _analyse
    from .verdict import judge as _judge, worst as _worst

    c = _load(clip, max_side=max_side, sample_fps=sample_fps, start=start,
              duration=duration)
    p = _analyse(c.frames, grid=grid, anchors=anchors)
    f = _judge(p)
    return Result(clip=clip, path=p, findings=f, verdict=_worst(f),
                  expect=_check(p, expect) if expect else None)
