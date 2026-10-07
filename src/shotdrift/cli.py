"""shotdrift - measure whether a video holds the camera move it was given."""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .core import measure, report
from .expect import known as known_moves
from .frames import DecodeError, FFmpegMissing
from .verdict import (BROKEN, CLEAN, SOFT, UNKNOWN, at_or_above)

EXIT_OK, EXIT_FINDINGS, EXIT_ERROR, EXIT_UNMEASURABLE = 0, 1, 2, 3


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
    ap.add_argument("--min-severity", choices=[CLEAN, SOFT, BROKEN], default=BROKEN,
                    help="which findings make this exit non-zero (default: broken; "
                         "soft findings are always printed either way)")
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

    if args.expect and args.expect not in known_moves():
        ap.error(f"unknown move {args.expect!r}. --list-moves shows them all.")

    results, rc = [], EXIT_OK
    for name in args.clips:
        try:
            r = measure(name, expect=args.expect, max_side=args.max_side,
                        grid=args.grid, start=args.start, duration=args.duration,
                        sample_fps=args.sample_fps, anchors=args.anchors,
                        max_frames=args.max_frames,
                        segment=not args.no_segment)
        except FFmpegMissing as e:
            print(f"shotdrift: {e}", file=sys.stderr)
            return EXIT_ERROR
        except (DecodeError, ValueError) as e:
            print(f"shotdrift: {name}: {e}", file=sys.stderr)
            rc = max(rc, EXIT_ERROR)
            continue

        for s in r.shots:
            if s.verdict == UNKNOWN:
                rc = max(rc, EXIT_UNMEASURABLE)
            elif at_or_above(s.findings, args.min_severity) or \
                    (s.expect is not None and not s.expect.ok):
                rc = max(rc, EXIT_FINDINGS)

        if args.json:
            results.append(r.as_dict())
        else:
            sys.stdout.write(report(r, quiet=args.quiet))

    if args.json:
        print(json.dumps({"shotdrift": __version__, "clips": results}, indent=2))
    return rc


if __name__ == "__main__":
    sys.exit(main())
