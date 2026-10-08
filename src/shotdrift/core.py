"""One measurement, however the frames arrived, and one way of reporting it.

Both halves of this file are corrections.

`measure()` used to call `analyse` where the command line calls `analyse_clip`,
so the Python API did not segment. On an edited reel that is not a small
difference: measured as one take, a six-shot sequence reports a broken closure
and a pile of reversals, all true and all useless, because no single camera move
was ever there to hold. The command line was fixed for exactly that and the
library was left behind - so `import shotdrift` gave a worse answer than
`shotdrift` did, which nothing warned anyone about.

And the text report lived inside the command line, writing straight to stdout.
Anything else wanting the same words - a node in a generation graph, a CI
comment - had to reimplement them, which is how two surfaces of one tool come to
disagree about what a clip measured. It renders to a string here, and the command
line prints what it returns.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .verdict import BROKEN, CLEAN, SOFT, UNKNOWN, at_or_above

__all__ = ["Shot", "Result", "measure", "measure_frames", "report"]

_MARK = {CLEAN: "ok", SOFT: "soft", BROKEN: "BROKEN", UNKNOWN: "unmeasurable"}
_RANK = {CLEAN: 0, SOFT: 1, BROKEN: 2, UNKNOWN: 0}


@dataclass
class Shot:
    """One continuous take, measured on its own."""
    start: int
    end: int
    path: object = field(repr=False)
    findings: list = field(default_factory=list)
    verdict: str = CLEAN
    expect: object | None = None

    @property
    def frames(self) -> int:
        return self.end - self.start

    @property
    def ok(self) -> bool:
        return self.verdict == CLEAN and (self.expect is None or self.expect.ok)

    def as_dict(self) -> dict:
        return {
            "frames": [self.start, self.end],
            "path": self.path.summary() if self.path is not None else None,
            "verdict": self.verdict,
            "expect": self.expect.as_dict() if self.expect else None,
            "findings": [f.as_dict() for f in self.findings],
        }


@dataclass
class Result:
    clip: str
    shots: list = field(default_factory=list)
    cuts: list = field(default_factory=list)
    src_width: int = 0
    src_height: int = 0
    width: int = 0
    height: int = 0
    frame_count: int = 0
    fps: float = 0.0
    truncated: bool = False

    # --- clip-level views over the shots -------------------------------------
    # A clip with one shot answers exactly as it did before segmentation existed.
    # With several, these summarise, and `shots` is there for anyone who needs the
    # detail - a clip-level verdict on an edited sequence is a summary, not a
    # measurement, and the distinction is kept rather than blurred.

    @property
    def path(self):
        """The dominant shot's path: the longest one, not the first."""
        measured = [s for s in self.shots if s.path is not None]
        if not measured:
            return None
        return max(measured, key=lambda s: s.frames).path

    @property
    def measured_frames(self) -> int:
        return sum(s.frames for s in self.shots if s.verdict != UNKNOWN)

    @property
    def complete(self) -> bool:
        """All requested frames were measured, with no unknown spans or truncation."""
        return (bool(self.shots) and not self.truncated
                and all(s.verdict != UNKNOWN for s in self.shots)
                and (not self.frame_count or self.measured_frames == self.frame_count))

    @property
    def findings(self) -> list:
        return [f for s in self.shots for f in s.findings]

    @property
    def verdict(self) -> str:
        if not self.complete:
            return UNKNOWN
        return max((s.verdict for s in self.shots), key=lambda v: _RANK[v])

    @property
    def expect(self):
        """The failing expectation if any shot failed it, else the dominant one."""
        failed = [s.expect for s in self.shots if s.expect is not None and not s.expect.ok]
        if failed:
            return failed[0]
        with_exp = [s for s in self.shots if s.expect is not None]
        return max(with_exp, key=lambda s: s.frames).expect if with_exp else None

    @property
    def ok(self) -> bool:
        """Every shot clean, and - if a move was declared - every shot held it."""
        return self.complete and all(s.ok for s in self.shots)

    def gated(self, min_severity: str = BROKEN) -> list:
        return at_or_above(self.findings, min_severity)

    def as_dict(self) -> dict:
        return {
            "clip": self.clip,
            "source": {"width": self.src_width, "height": self.src_height,
                       "fps": self.fps},
            "measured_at": {"width": self.width, "height": self.height,
                            "frames": self.frame_count,
                            "truncated": self.truncated},
            "cuts": self.cuts,
            "verdict": self.verdict,
            "ok": self.ok,
            "coverage": {"complete": self.complete,
                         "measured_frames": self.measured_frames,
                         "unmeasured_spans": [[s.start, s.end] for s in self.shots
                                              if s.verdict == UNKNOWN]},
            "shots": [s.as_dict() for s in self.shots],
        }


def _assemble(name: str, frames, grid: int, anchors: int, segment: bool,
              expect: str | None) -> tuple[list, list]:
    from .expect import check as check_expect, unmeasurable
    from .path import analyse_clip
    from .verdict import Finding, judge, worst

    shots_in, cuts = analyse_clip(frames, grid=grid, anchors=anchors,
                                  segment=segment)
    shots = []

    def unknown_span(a, b):
        f = Finding("short_shot", UNKNOWN,
                    "This shot is too short to measure reliably.",
                    f"frames {a}-{b}: {b - a} frames between cuts",
                    "Supply a longer continuous shot; this span has not been passed.")
        shots.append(Shot(a, b, None, [f], UNKNOWN,
                          unmeasurable(expect) if expect else None))

    measured = dict(shots_in)
    bounds = [0] + [cut + 1 for cut in cuts] + [len(frames)]
    for a, b in zip(bounds, bounds[1:]):
        p = measured.get((a, b))
        if p is None:
            unknown_span(a, b)
            continue
        f = judge(p)
        v = worst(f)
        e = (unmeasurable(expect) if v == UNKNOWN else check_expect(p, expect)) if expect else None
        shots.append(Shot(start=a, end=b, path=p, findings=f, verdict=v, expect=e))
    return shots, cuts


def measure(clip: str, expect: str | None = None, *, max_side: int = 512,
            grid: int = 4, start: float = 0.0, duration: float | None = None,
            sample_fps: float | None = None, anchors: int = 4,
            max_frames: int = 600, segment: bool = True) -> Result:
    """Measure a video file. Cuts are detected and each shot measured on its own."""
    from .frames import load
    from .validation import analysis_options

    analysis_options(grid, anchors)
    c = load(clip, max_side=max_side, sample_fps=sample_fps, start=start,
             duration=duration, max_frames=max_frames)
    shots, cuts = _assemble(clip, c.frames, grid, anchors, segment, expect)
    return Result(clip=clip, shots=shots, cuts=cuts,
                  src_width=c.src_width, src_height=c.src_height,
                  width=c.width, height=c.height, frame_count=len(c),
                  fps=c.fps, truncated=c.truncated)


def measure_frames(frames, expect: str | None = None, *, name: str = "<frames>",
                   max_side: int = 512, grid: int = 4, anchors: int = 4,
                   segment: bool = True, fps: float = 0.0) -> Result:
    """Measure frames that are already in memory - no file, no ffmpeg.

    Takes (n, h, w) or (n, h, w, c) in uint8 0..255 or float 0..1, as a numpy
    array or a torch tensor. This is the entry point a generation graph uses: the
    frames exist, they were never written to disk, and the question is whether
    the move that was asked for is in them.
    """
    from .ingest import to_gray_stack
    from .validation import analysis_options, finite

    analysis_options(grid, anchors)
    finite("fps", fps)
    stack, sw, sh = to_gray_stack(frames, max_side=max_side)
    shots, cuts = _assemble(name, stack, grid, anchors, segment, expect)
    n, h, w = stack.shape
    return Result(clip=name, shots=shots, cuts=cuts, src_width=sw, src_height=sh,
                  width=w, height=h, frame_count=n, fps=fps)


# ------------------------------------------------------------------ report ----
def _fmt(v, nd=4):
    if v is None:
        return "-"
    if isinstance(v, float) and not np.isfinite(v):
        return "not measurable"
    return f"{v:.{nd}f}" if isinstance(v, float) else str(v)


def report(r: Result, *, quiet: bool = False, header: bool = True) -> str:
    """The human-readable report, as a string. The CLI prints this verbatim."""
    out = []
    w = out.append

    if header:
        w(f"\n{r.clip}")
        rate = f" @ {r.fps:g} fps" if r.fps else ""
        w(f"  {r.src_width}x{r.src_height} -> measured at {r.width}x{r.height}, "
          f"{r.frame_count} frames{rate}")
        if r.truncated:
            w(f"  only the first {r.frame_count} frames were measured "
              f"(--max-frames); the rest of the clip was not looked at.")
        if r.cuts:
            w(f"  {len(r.cuts)} cut(s) detected: this is {len(r.shots)} shot(s), "
              f"not one take. Each is measured on its own.")
        if not r.complete:
            w(f"  INCOMPLETE: {r.measured_frames} of {r.frame_count} decoded frames "
              "measurable; the requested clip cannot be passed.")

    multi = len(r.shots) > 1
    for s in r.shots:
        p = s.path
        if multi:
            w(f"\n  shot {s.start}-{s.end} ({s.frames} frames)")
        if p is None:
            w(f"    [unmeasurable] frames {s.start}-{s.end}: too short between cuts.")
            if s.expect is not None:
                w(f"    asked for {s.expect.move}: NOT MEASURABLE")
            continue
        w("\n  camera path")
        w(f"    dominant move      {p.dominant}")
        w(f"    pan                {_fmt(p.net_pan)} of frame width "
          f"(x {_fmt(float(p.tx[-1]))}, y {_fmt(float(p.ty[-1]))})")
        w(f"    zoom               {_fmt(p.zoom, 3)}x")
        w(f"    roll               {_fmt(float(np.degrees(p.net_roll)), 2)} deg")
        w(f"    reversals          {p.reversals}  (measured, not judged)")
        w(f"    jerk               {_fmt(p.jerk, 2)}")
        w(f"    incoherence        {_fmt(p.incoherence)}")
        w(f"    morph              {_fmt(p.morph, 3)}  (used to find cuts, not judged)")
        w(f"    closure            {_fmt(p.closure)}")
        w(f"    confidence         {_fmt(p.confidence, 2)}")

        if s.expect is not None:
            w(f"\n  asked for: {s.expect.move}")
            status = "NOT MEASURABLE" if not s.expect.measurable else ("HELD" if s.expect.ok else "NOT HELD")
            w(f"    {status} - {s.expect.detail}")

        if not s.findings:
            w("\n  no findings in the measured 2D image motion.")
        else:
            w(f"\n  {len(s.findings)} finding(s)")
            for f in s.findings:
                w(f"    [{_MARK[f.severity]}] {f.summary}")
                w(f"        evidence: {f.evidence}")
                if not quiet:
                    w(f"        {f.advice}")
    return "\n".join(out) + "\n"
