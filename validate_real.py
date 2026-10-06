#!/usr/bin/env python3
"""Validate shotdrift against REAL footage and against controls with known faults.

Not shipped in the wheel. This is the file that earns the thresholds in
verdict.py, and it is the reason they are not taste.

Two halves, and both are load-bearing:

  REAL    - footage off real cameras. The requirement is SILENCE. A measurement
            tool that flags genuine material is worse than no tool, because the
            first thing a person does with a noisy alarm is stop reading it.
  CONTROL - synthetic clips built with a fault deliberately in them. The
            requirement is that the specific fault is NAMED. "Something is wrong"
            is not a finding.

Run:  PYTHONPATH=src python validate_real.py [--write-calibration]
"""

from __future__ import annotations

import argparse
import json
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, "src")

from shotdrift.expect import check as check_expect          # noqa: E402
from shotdrift.frames import load                            # noqa: E402
from shotdrift.path import analyse, analyse_clip             # noqa: E402
from shotdrift.verdict import BROKEN, CLEAN, SOFT, judge, worst  # noqa: E402

REAL = [
    ("locked-off stage, 50p", "../livex_tucker_question/LiveX_D1_Panel01_TuckerCarlson_BestQuestion_1080.mp4"),
    ("multi-camera panel cut", "../livex_cities_quotes/LiveX_D1_Cities_AbuDhabiIsTheDifference_1080.mp4"),
    ("panel Q&A, vision mix", "../livex_panel01_qa/LiveX_Panel01_QA_60s.mp4"),
    ("conference stage 720p", "../livex_humancity/LIVEX_HUMANCITY_BEST_MINUTE.mp4"),
    ("main stage wide", "../livex_governing/mainstage_1052.mp4"),
    ("event highlight cut", "../livex_autohighlight/out/s03_highlight.mp4"),
    ("event highlight cut 2", "../livex_autohighlight/out/s19_highlight.mp4"),
]


# ---------------------------------------------------------------- controls ----
def _plate(w=900, h=900, seed=7):
    rng = np.random.default_rng(seed)
    low = rng.random((h // 10, w // 10)).astype(np.float32)
    img = np.asarray(Image.fromarray((low * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC),
                     dtype=np.float32) / 255.0
    yy, xx = np.mgrid[0:h, 0:w]
    detail = 0.22 * np.sin(xx / 6.0) * np.cos(yy / 8.0)
    return np.clip(img * 0.72 + rng.random((h, w)).astype(np.float32) * 0.18 + detail, 0, 1).astype(np.float32)


def _crop(plate, cx, cy, size, out=320):
    h, w = plate.shape
    s = int(round(size))
    x0 = int(round(cx - s / 2))
    y0 = int(round(cy - s / 2))
    x0 = max(0, min(w - s, x0))
    y0 = max(0, min(h - s, y0))
    sub = plate[y0:y0 + s, x0:x0 + s]
    im = Image.fromarray((sub * 255).astype(np.uint8)).resize((out, out), Image.BICUBIC)
    return np.asarray(im, dtype=np.float32) / 255.0


def c_clean_push(n=36):
    """A real push-in: size shrinks smoothly, eased in and out."""
    p = _plate()
    t = np.linspace(0, 1, n)
    ease = t * t * (3 - 2 * t)
    return np.stack([_crop(p, 450, 450, 700 - 260 * e) for e in ease])


def c_clean_pan(n=36):
    p = _plate()
    t = np.linspace(0, 1, n)
    ease = t * t * (3 - 2 * t)
    return np.stack([_crop(p, 280 + 330 * e, 450, 420) for e in ease])


def c_reversing_push(n=36):
    """Asked for a push-in; it pushes, backs off, pushes again."""
    p = _plate()
    t = np.linspace(0, 1, n)
    z = 700 - 260 * (t + 0.34 * np.sin(t * 3 * np.pi))
    return np.stack([_crop(p, 450, 450, s) for s in z])


def c_breathing(n=40):
    """Pulses in and out, arrives exactly where it started."""
    p = _plate()
    t = np.linspace(0, 1, n)
    z = 560 + 90 * np.sin(t * 4 * np.pi)
    return np.stack([_crop(p, 450, 450, s) for s in z])


def c_wander(n=40):
    """Meant to be locked off; the frame drifts and corrects, net zero."""
    p = _plate()
    rng = np.random.default_rng(3)
    walk = np.cumsum(rng.normal(0, 7.0, (n, 2)), axis=0)
    walk -= np.linspace(0, 1, n)[:, None] * walk[-1]      # force net zero
    return np.stack([_crop(p, 450 + dx, 450 + dy, 470) for dx, dy in walk])


def c_morphing(n=34):
    """Camera is perfectly still; the WORLD is being redrawn underneath it."""
    a, b = _plate(seed=7), _plate(seed=19)
    out = []
    for i in range(n):
        k = i / (n - 1)
        out.append(_crop(a * (1 - k) + b * k, 450, 450, 470))
    return np.stack(out)


def c_two_layers(n=30):
    """Physically impossible: the top half pans one way, the bottom half the other.

    The positive control for `incoherent`. Nothing else in this set exercises it,
    and a bound with no control behind it is a guess with a comment.
    """
    p = _plate()
    out = []
    for i in range(n):
        d = i * 9
        top = _crop(p, 300 + d, 300, 420)
        bot = _crop(p, 600 - d, 600, 420)
        f = top.copy()
        f[160:, :] = bot[160:, :]
        out.append(f)
    return np.stack(out)


def c_pan_sold_as_push(n=30):
    """Clean, physical, and not the move that was asked for."""
    return c_clean_pan(n)


# label, builder, --expect, required verdict, must-name, must --expect FAIL
CONTROLS = [
    ("clean push-in",         c_clean_push,       "push-in",   CLEAN,  None,          False),
    ("clean pan-right",       c_clean_pan,        "pan-right", CLEAN,  None,          False),
    ("push-in that reverses", c_reversing_push,   "push-in",   CLEAN,  None,          True),
    ("pan sold as push-in",   c_pan_sold_as_push, "push-in",   CLEAN,  None,          True),
    ("breathing, net zero",   c_breathing,        "static",    BROKEN, "breathing",   True),
    ("wander, net zero",      c_wander,           "static",    SOFT,   "wander",      True),
    ("two layers, opposite",  c_two_layers,       None,        BROKEN, "incoherent",  False),
]

# Blind spots, asserted rather than hidden. These clips SHOULD come back clean:
# shotdrift measures camera motion, and in each of these the camera is honest. If
# one of them ever starts reporting a finding, that is a false positive to
# investigate, not an improvement - so the harness pins them.
LIMITATIONS = [
    ("world redrawn under a locked camera", c_morphing,
     "A cross-dissolve between two different worlds. The camera never moves, so a "
     "camera-motion measurement correctly finds nothing. Real footage reaches a "
     "span-morph of 1.06 against this clip's 0.358, so no structural threshold "
     "separates invented geometry from a real scene with things happening in it."),
]

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write-calibration", action="store_true")
    ap.add_argument("--duration", type=float, default=8.0)
    ap.add_argument("--max-side", type=int, default=320)
    args = ap.parse_args()

    fails, rows = [], []

    print("=" * 78)
    print("REAL FOOTAGE - requirement: no BROKEN finding on real camera material")
    print("=" * 78)
    for label, path in REAL:
        try:
            c = load(path, max_side=args.max_side, duration=args.duration)
        except Exception as e:                                    # noqa: BLE001
            print(f"  SKIP {label}: {e}")
            continue
        shots, cuts = analyse_clip(c.frames)
        for i, ((a, b), p) in enumerate(shots):
            f = judge(p)
            v = worst(f)
            codes = ",".join(sorted({x.code for x in f})) or "-"
            tag = "OK " if v in (CLEAN, SOFT) else "FAIL"
            if v == BROKEN:
                fails.append(f"REAL {label} shot{i} -> BROKEN ({codes})")
            print(f"  {tag} {label[:26]:<26} shot{i} {b - a:>4}f  cuts={len(cuts):<3} "
                  f"{v:<6} {codes}")
            rows.append(dict(kind="real", label=label, shot=i, span=int(b - a),
                             cuts=len(cuts), verdict=v,
                             **{k: (None if isinstance(x, float) and not np.isfinite(x) else x)
                                for k, x in p.summary().items()}))

    print()
    print("=" * 78)
    print("CONTROLS - requirement: the named fault is the finding, by name")
    print("=" * 78)
    for label, build, move, must_be, must_name, must_fail_expect in CONTROLS:
        fr = build()
        p = analyse(fr)
        f = judge(p)
        v = worst(f)
        codes = sorted({x.code for x in f})
        e = check_expect(p, move) if move else None
        ok = True
        if v != must_be:
            ok = False
            fails.append(f"CONTROL {label} -> expected {must_be}, got {v} ({codes})")
        if must_name and must_name not in codes:
            ok = False
            fails.append(f"CONTROL {label} -> did not NAME '{must_name}', said {codes}")
        if e is not None:
            if must_fail_expect and e.ok:
                ok = False
                fails.append(f"CONTROL {label} -> --expect {move} wrongly HELD")
            if not must_fail_expect and not e.ok:
                ok = False
                fails.append(f"CONTROL {label} -> --expect {move} wrongly NOT HELD ({e.detail})")
        print(f"  {'OK ' if ok else 'FAIL'} {label[:26]:<26} {v:<6} "
              f"{','.join(codes) or '-':<26} "
              f"expect:{'-' if e is None else ('HELD' if e.ok else 'not held')}")
        rows.append(dict(kind="control", label=label, verdict=v, codes=codes,
                         expect=e.as_dict() if e else None,
                         **{k: (None if isinstance(x, float) and not np.isfinite(x) else x)
                            for k, x in p.summary().items()}))

    print()
    print("=" * 78)
    print("STATED LIMITATIONS - these must stay clean; a finding here is a regression")
    print("=" * 78)
    for label, build, why in LIMITATIONS:
        p = analyse(build())
        f = judge(p)
        v = worst(f)
        ok = (v == CLEAN)
        if not ok:
            fails.append(f"LIMITATION {label} -> expected clean, got {v} "
                         f"({sorted({x.code for x in f})})")
        print(f"  {'OK ' if ok else 'FAIL'} {label[:40]:<40} {v}")
        print(f"      {why}")
        rows.append(dict(kind="limitation", label=label, verdict=v, why=why))

    real = [r for r in rows if r["kind"] == "real"]
    print()
    print("=" * 78)
    print("MEASURED DISTRIBUTIONS - where the thresholds come from")
    print("=" * 78)
    for key in ("incoherence", "morph", "jerk", "closure", "confidence"):
        vals = [r[key] for r in real if r.get(key) is not None]
        if vals:
            print(f"  real {key:<12} min={min(vals):.5f} median={float(np.median(vals)):.5f} "
                  f"max={max(vals):.5f}   (n={len(vals)})")

    if args.write_calibration:
        with open("calibration.json", "w") as fh:
            json.dump(rows, fh, indent=1, default=str)
        print("\n  wrote calibration.json")

    print()
    if fails:
        print(f"VALIDATION FAILED - {len(fails)} problem(s)")
        for x in fails:
            print("  -", x)
        return 1
    print(f"VALIDATION PASSED - {len(real)} real shots silent-or-soft, "
          f"{len(CONTROLS)} controls named correctly")
    return 0


if __name__ == "__main__":
    sys.exit(main())
