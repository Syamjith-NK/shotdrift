"""shotdrift - measure whether a video holds the camera move it was given."""

from __future__ import annotations

import argparse
import json
import sys

import numpy as np

from . import __version__
from .expect import check as check_expect, known as known_moves
from .frames import Clip, DecodeError, FFmpegMissing, load
from .path import analyse_clip
from .verdict import (BROKEN, CLEAN, SOFT, UNKNOWN, at_or_above, judge, worst)

EXIT_OK, EXIT_FINDINGS, EXIT_ERROR, EXIT_UNMEASURABLE = 0, 1, 2, 3

_MARK = {CLEAN: "ok", SOFT: "soft", BROKEN: "BROKEN", UNKNOWN: "unmeasurable"}


def _fmt(v, nd=4):
    if v is None:
        return "-"
    if isinstance(v, float) and not np.isfinite(v):
        return "not measurable"
    return f"{v:.{nd}f}" if isinstance(v, float) else str(v)


def _header(name: str, clip: Clip, cuts: list, n_shots: int) -> None:
    w = sys.stdout.write
    w(f"\n{name}\n")
    w(f"  {clip.src_width}x{clip.src_height} -> measured at {clip.width}x{clip.height}, "
      f"{len(clip)} frames @ {clip.fps:g} fps\n")
    if cuts:
        w(f"  {len(cuts)} cut(s) detected: this is {n_shots} shot(s), not one take. "
          f"Each is measured on its own.\n")


def _report(name: str, clip: Clip, p, findings, exp, args, span=None) -> None:
    w = sys.stdout.write
    if span is not None:
        a, b = span
        w(f"\n  shot {a}-{b} ({b - a} frames)\n")

    w(f"\n  camera path\n")
    w(f"    dominant move      {p.dominant}\n")
    w(f"    pan                {_fmt(p.net_pan)} of frame width "
      f"(x {_fmt(float(p.tx[-1]))}, y {_fmt(float(p.ty[-1]))})\n")
    w(f"    zoom               {_fmt(p.zoom, 3)}x\n")
    w(f"    roll               {_fmt(np.degrees(p.net_roll), 2)} deg\n")
    w(f"    reversals          {p.reversals}  (measured, not judged)\n")
    w(f"    jerk               {_fmt(p.jerk, 2)}\n")
    w(f"    incoherence        {_fmt(p.incoherence)}\n")
    w(f"    morph              {_fmt(p.morph, 3)}  (used to find cuts, not judged)\n")
    w(f"    closure            {_fmt(p.closure)}\n")
    w(f"    confidence         {_fmt(p.confidence, 2)}\n")

    if exp is not None:
        w(f"\n  asked for: {exp.move}\n")
        w(f"    {'HELD' if exp.ok else 'NOT HELD'} - {exp.detail}\n")

    if not findings:
        w("\n  no findings: the motion is consistent with one physical camera.\n")
    else:
        w(f"\n  {len(findings)} finding(s)\n")
        for f in findings:
            w(f"    [{_MARK[f.severity]}] {f.summary}\n")
            w(f"        evidence: {f.evidence}\n")
            if not args.quiet:
                w(f"        {f.advice}\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="shotdrift",
        description="Measure the camera move in a video, and whether it is one a real "
                    "camera could have made.",
        epilog="Exit 0 clean, 1 findings at or above --min-severity, "
               "2 could not run, 3 clip could not be measured.",
    )
    ap.add_argument("clips", nargs="*", metavar="CLIP")
    ap.add_argument("--expect", metavar="MOVE",
                    help="the move you asked for: " + ", ".join(known_moves()))
    ap.add_argument("--list-moves", action="store_true")
    ap.add_argument("--min-severity", choices=[CLEAN, SOFT, BROKEN], default=SOFT,
                    help="which findings make this exit non-zero (default: soft)")
    ap.add_argument("--max-side", type=int, default=512,
                    help="analysis resolution, long edge in px (default 512)")
    ap.add_argument("--grid", type=int, default=4, help="tiles per axis (default 4)")
    ap.add_argument("--start", type=float, default=0.0, metavar="SEC")
    ap.add_argument("--duration", type=float, default=None, metavar="SEC")
    ap.add_argument("--sample-fps", type=float, default=None,
                    help="resample before measuring; changes WHAT is measured, "
                         "not just the cost")
    ap.add_argument("--max-frames", type=int, default=600)
    ap.add_argument("--anchors", type=int, default=4,
                    help="independent first-to-frame-k checks (0 disables closure)")
    ap.add_argument("--no-segment", action="store_true",
                    help="measure the file as one take even if it contains cuts")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--quiet", action="store_true", help="findings without the advice")
    ap.add_argument("--version", action="version", version=f"shotdrift {__version__}")
    args = ap.parse_args(argv)

    if args.list_moves:
        for m in known_moves():
            print(m)
        return EXIT_OK
    if not args.clips:
        ap.error("give at least one CLIP, or --list-moves")

    results, rc = [], EXIT_OK
    for name in args.clips:
        try:
            clip = load(name, max_side=args.max_side, sample_fps=args.sample_fps,
                        start=args.start, duration=args.duration,
                        max_frames=args.max_frames)
            shots, cuts = analyse_clip(clip.frames, grid=args.grid,
                                       anchors=args.anchors,
                                       segment=not args.no_segment)
        except FFmpegMissing as e:
            print(f"shotdrift: {e}", file=sys.stderr)
            return EXIT_ERROR
        except (DecodeError, ValueError) as e:
            print(f"shotdrift: {name}: {e}", file=sys.stderr)
            rc = max(rc, EXIT_ERROR)
            continue

        if not args.json:
            _header(name, clip, cuts, len(shots))

        shot_out = []
        for (a, b), p in shots:
            findings = judge(p)
            exp = None
            if args.expect:
                try:
                    exp = check_expect(p, args.expect)
                except KeyError as e:
                    print(f"shotdrift: {e}", file=sys.stderr)
                    return EXIT_ERROR

            verdict = worst(findings)
            gated = at_or_above(findings, args.min_severity)
            if verdict == UNKNOWN:
                rc = max(rc, EXIT_UNMEASURABLE)
            elif gated or (exp is not None and not exp.ok):
                rc = max(rc, EXIT_FINDINGS)

            if args.json:
                shot_out.append({
                    "frames": [a, b],
                    "path": p.summary(),
                    "verdict": verdict,
                    "expect": exp.as_dict() if exp else None,
                    "findings": [f.as_dict() for f in findings],
                })
            else:
                _report(name, clip, p, findings, exp, args,
                        span=(a, b) if len(shots) > 1 else None)

        if args.json:
            results.append({
                "clip": name,
                "source": {"width": clip.src_width, "height": clip.src_height,
                           "fps": clip.fps},
                "measured_at": {"width": clip.width, "height": clip.height,
                                "frames": len(clip)},
                "cuts": cuts,
                "shots": shot_out,
            })

    if args.json:
        print(json.dumps({"shotdrift": __version__, "clips": results}, indent=2))
    return rc


if __name__ == "__main__":
    sys.exit(main())
