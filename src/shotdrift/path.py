"""Integrate per-pair estimates into a camera path, and derive the clip-level facts.

Why integrate at all: a per-frame comparison cannot see a shot slowly leaving the
move it was given. Every adjacent pair looks fine while the frame walks away. The
failures worth catching are properties of the PATH, so everything here is computed
on the accumulated curve, never on one pair.

The noise floor is not a magic number. The similarity fit already reports what it
could not explain (`incoherence`), and that is the measurement's own uncertainty,
so it is what a velocity has to exceed before a sign change counts as a real
reversal. The floor therefore calibrates itself per clip.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field

import numpy as np

from .motion import Pair, estimate_pair

EPS = 1e-9

# A hard cut leaves no structure in common between two frames, so the morph
# residual jumps by an order of magnitude. MEASURED, not chosen: across real
# single-camera footage morph tops out at 0.16, while frames either side of a cut
# in an edited reel read 1.7-8.6. The bound sits in that gap with room on both
# sides. See calibration.md.
CUT_MORPH = 0.8
MIN_SHOT_FRAMES = 8

# How much a channel must move before the shot is "about" that channel, in frame
# widths / log-scale / radians. ONE definition, imported by the verdict layer too:
# when "has it moved?" was answered in two places with two different numbers, a
# locked-off camera was labelled a pan and had its sub-pixel noise counted as ten
# reversals. The label and the judgement must share the floor.
MOVED = {"pan": 0.01, "zoom": 0.01, "roll": 0.01}


@dataclass
class Path:
    tx: np.ndarray = field(repr=False)        # cumulative pan right (frame widths)
    ty: np.ndarray = field(repr=False)        # cumulative pan down
    logscale: np.ndarray = field(repr=False)  # cumulative log scale
    roll: np.ndarray = field(repr=False)      # cumulative radians
    pairs: list[Pair] = field(repr=False)

    # derived
    frames: int = 0
    net_pan: float = 0.0
    path_length: float = 0.0
    wander: float = 1.0
    zoom: float = 1.0
    breathing: float = 1.0
    scale_travel: float = 0.0
    scale_amp: float = 0.0                    # peak-to-peak log scale (length-independent)
    scale_rate: float = 0.0                   # mean per-pair |log scale| change
    net_roll: float = 0.0
    dominant: str = "static"
    reversals: int = 0
    jerk: float = 0.0
    speed: float = 0.0                        # RMS per-pair speed, dominant channel
    incoherence: float = 0.0
    morph: float = 0.0
    morph_trend: float = 0.0
    closure: float = float("nan")
    confidence: float = 0.0
    noise_floor: float = 0.0

    def summary(self) -> dict:
        d = {k: v for k, v in asdict(self).items()
             if not isinstance(v, (np.ndarray, list))}
        return {k: (round(v, 6) if isinstance(v, float) else v) for k, v in d.items()}


def find_cuts(pairs: list[Pair]) -> list[int]:
    """Indices i where frame i -> i+1 is a cut rather than a camera move.

    This exists because of a defect found by running the tool on a real edited
    reel: measured as one shot it reported 13 reversals and a broken closure. All
    true, and useless - it is six shots, and no single camera move was ever there
    to hold. A tool that shouts at an edited sequence is a tool people stop
    running, so a clip is segmented before it is judged.

    A cut has TWO signatures and the second one was nearly missed. Where some
    structure survives the join - a whip transition, a dissolve, a match cut - the
    morph residual spikes an order of magnitude above the 0.36 that real
    within-shot footage reaches. But across a CLEAN cut between unrelated shots,
    no tile correlates at all, so no camera could be fitted and morph is never
    computed: it comes back NaN. The first version only tested the spike, so it
    detected smeared transitions and would have walked straight past an ordinary
    hard cut.

    A pair that cannot be measured inside an otherwise measurable clip is a
    discontinuity. A clip where that is true nearly everywhere is simply
    unmeasurable, which `judge` reports instead - so the healthy-neighbours test
    is what separates "a cut happened here" from "this footage has no texture".
    """
    if not pairs:
        return []
    tiles = np.array([q.tiles for q in pairs], dtype=float)
    clip_healthy = float(np.median(tiles)) >= 6.0
    out = []
    for i, q in enumerate(pairs):
        m = q.morph
        if np.isfinite(m) and m >= CUT_MORPH:
            out.append(i)
        elif clip_healthy and q.tiles < 3:
            out.append(i)
    return out


def shot_ranges(n_frames: int, cuts: list[int], min_frames: int = MIN_SHOT_FRAMES
                ) -> list[tuple[int, int]]:
    """Half-open frame ranges between cuts, dropping fragments too short to judge."""
    bounds = [0] + [c + 1 for c in cuts] + [n_frames]
    out = []
    for a, b in zip(bounds, bounds[1:]):
        if b - a >= min_frames:
            out.append((a, b))
    return out


def _reversals(vel: np.ndarray, floor: float) -> int:
    """Sign changes in a velocity that is actually moving.

    Counting raw sign flips on a near-static channel returns noise - a locked-off
    tripod would score dozens. Only samples above the clip's own measurement floor
    get a vote, and the previous *significant* sign is what the next is compared
    against, so one slow deceleration through zero is not two reversals.
    """
    sig = np.abs(vel) > max(floor, EPS)
    if sig.sum() < 2:
        return 0
    signs = np.sign(vel[sig])
    return int(np.count_nonzero(np.diff(signs) != 0))


def _jerk(pos: np.ndarray, floor: float) -> float:
    """RMS third difference of position, normalised by RMS speed: dimensionless.

    A real camera is carried by something with mass, so its velocity changes
    smoothly. Generated motion snaps between states, which is visible here even
    when the net move is correct.
    """
    if len(pos) < 4:
        return 0.0
    vel = np.diff(pos)
    j = np.diff(vel, n=2)
    speed = float(np.sqrt(np.mean(vel ** 2)))
    if speed < max(floor, EPS):
        return 0.0
    return float(np.sqrt(np.mean(j ** 2)) / speed)


def analyse(frames: np.ndarray, grid: int = 4, anchors: int = 4,
            pairs: list[Pair] | None = None) -> Path:
    n = int(frames.shape[0])
    if n < 2:
        raise ValueError("need at least two frames")

    if pairs is None:
        pairs = [estimate_pair(frames[i], frames[i + 1], grid=grid) for i in range(n - 1)]
    elif len(pairs) != n - 1:
        raise ValueError(f"got {len(pairs)} pairs for {n} frames")

    tx = np.concatenate([[0.0], np.cumsum([p.tx for p in pairs])])
    ty = np.concatenate([[0.0], np.cumsum([p.ty for p in pairs])])
    ls = np.concatenate([[0.0], np.cumsum([np.log1p(max(-0.9, p.scale)) for p in pairs])])
    rl = np.concatenate([[0.0], np.cumsum([p.roll for p in pairs])])

    inc = np.array([p.incoherence for p in pairs], dtype=float)
    mor = np.array([p.morph for p in pairs], dtype=float)
    cnf = np.array([p.confidence for p in pairs], dtype=float)

    floor = float(np.nanmedian(inc)) if np.isfinite(inc).any() else 0.0
    if not np.isfinite(floor):
        floor = 0.0

    step = np.hypot([p.tx for p in pairs], [p.ty for p in pairs])
    path_length = float(np.sum(step))
    net_pan = float(np.hypot(tx[-1], ty[-1]))
    total_abs_ls = float(np.sum(np.abs(np.diff(ls))))

    # Which channel is this shot actually about? Everything judged afterwards -
    # reversals, jerk - is judged on that channel, because a reversal in a channel
    # the shot never used is noise by definition.
    mags = {"pan": net_pan, "zoom": abs(ls[-1]), "roll": abs(rl[-1])}
    # Scale each channel by its own floor so they are comparable before picking a
    # winner; raw magnitudes are in different units and whichever has the smallest
    # unit would always win.
    dominant = max(mags, key=lambda k: mags[k] / MOVED[k])
    if mags[dominant] < MOVED[dominant]:
        dominant = "static"

    if dominant == "pan":
        # project onto the net direction so a diagonal move is one channel
        if net_pan > EPS:
            ux, uy = tx[-1] / net_pan, ty[-1] / net_pan
        else:
            ux, uy = 1.0, 0.0
        chan = tx * ux + ty * uy
    elif dominant == "zoom":
        chan = ls
    elif dominant == "roll":
        chan = rl
    else:
        chan = tx * 0.0

    vel = np.diff(chan) if len(chan) > 1 else np.array([0.0])

    if np.isfinite(mor).sum() >= 3:
        idx = np.arange(len(mor))[np.isfinite(mor)]
        trend = float(np.polyfit(idx, mor[np.isfinite(mor)], 1)[0])
    else:
        trend = 0.0

    p = Path(tx=tx, ty=ty, logscale=ls, roll=rl, pairs=pairs)
    p.frames = n
    p.net_pan = net_pan
    p.path_length = path_length
    p.wander = float(path_length / max(net_pan, 1e-4))
    p.zoom = float(np.exp(ls[-1]))
    p.breathing = float(total_abs_ls / max(abs(ls[-1]), 1e-4))
    # The ratio alone is a trap: on a locked-off shot the denominator is
    # legitimately zero, so sub-pixel noise divided by nothing reported a real
    # tripod as "breathing 14.8x". Keep the absolute travel beside the ratio so
    # the verdict layer can ask whether anything actually happened first.
    p.scale_travel = total_abs_ls
    # ...and scale_travel is NOT the right thing to gate on, which cost four
    # false BROKENs on real footage. It is a CUMULATIVE SUM, so it grows with
    # clip length while the thing it is standing in for - "did the scale visibly
    # move?" - does not. MEASURED on a locked-off stage camera: the per-pair rate
    # is flat at ~2e-5 at every length, and scale_travel walks 0.0025 (100
    # frames) -> 0.0263 (1200 frames), crossing any fixed gate purely by running
    # longer. The amplitude of the scale curve is the length-independent
    # quantity, and it is also the one a viewer can actually see.
    p.scale_amp = float(ls.max() - ls.min()) if len(ls) else 0.0
    p.scale_rate = float(total_abs_ls / max(len(pairs), 1))
    p.net_roll = float(rl[-1])
    p.dominant = dominant
    p.reversals = _reversals(vel, floor)
    p.jerk = _jerk(chan, floor)
    # Jerk is normalised BY SPEED, so the speed has to be reported beside it or
    # the verdict layer cannot tell a snapping move from a camera that is barely
    # moving at all. Net displacement is not a substitute: a locked-off stage
    # camera crept 0.026 of a frame width over 327 frames, cleared the 0.01
    # displacement floor, and had an RMS speed of 2.8e-4 - which is how it came
    # to be reported as the jerkiest shot in the whole real-footage set.
    p.speed = float(np.sqrt(np.mean(vel ** 2))) if len(vel) else 0.0
    p.incoherence = floor
    p.morph = float(np.nanmedian(mor)) if np.isfinite(mor).any() else float("nan")
    p.morph_trend = trend
    p.confidence = float(np.nanmean(cnf)) if np.isfinite(cnf).any() else 0.0
    p.noise_floor = floor
    p.closure = _closure(frames, tx, ty, grid, anchors, floor)
    return p


def _closure(frames: np.ndarray, tx: np.ndarray, ty: np.ndarray,
             grid: int, anchors: int, floor: float) -> float:
    """An independent route to the same number.

    The chain says where frame k ended up by adding up every step. Measuring
    frame 0 against frame k DIRECTLY asks the same question without using any of
    those steps. Where both are trustworthy they must agree; a large gap means the
    chain accumulated error or the content stopped resembling itself.

    Returns the worst disagreement in frame widths, or NaN when no anchor pair
    correlated well enough to be worth comparing - an unmeasurable anchor is not
    evidence of a problem.
    """
    n = int(frames.shape[0])
    if n < 4 or anchors < 1:
        return float("nan")
    ks = np.unique(np.linspace(1, n - 1, min(anchors, n - 1)).round().astype(int))
    worst = float("nan")
    for k in ks:
        d = estimate_pair(frames[0], frames[int(k)], grid=grid)
        # An anchor must earn the right to contradict the chain. Once frame 0 and
        # frame k barely overlap, the direct correlation degrades into a confident
        # wrong answer - measured here at 5 surviving tiles and a fit residual
        # 1000x the clip's own, reporting +0.003 where the truth was +0.270. Taken
        # at face value that reads as a catastrophic closure failure on a clip that
        # is in fact perfect. So the anchor is only believed when its OWN fit is as
        # internally consistent as the per-frame fits are: cannot-measure must
        # never be reported as measured-bad.
        if d.tiles < 6 or d.confidence < 0.25 or not np.isfinite(d.incoherence):
            continue
        if d.incoherence > max(4.0 * floor, 2e-3):
            continue
        gap = float(np.hypot(d.tx - tx[k], d.ty - ty[k]))
        worst = gap if not np.isfinite(worst) else max(worst, gap)
    return worst


def analyse_clip(frames: np.ndarray, grid: int = 4, anchors: int = 4,
                 segment: bool = True) -> tuple[list[tuple[tuple[int, int], Path]], list[int]]:
    """Measure a whole file: one Path per shot, plus where the cuts are.

    The per-pair estimates are computed ONCE and sliced, so segmenting costs
    nothing over measuring the file as a single take.
    """
    n = int(frames.shape[0])
    pairs = [estimate_pair(frames[i], frames[i + 1], grid=grid) for i in range(n - 1)]
    cuts = find_cuts(pairs) if segment else []
    ranges = shot_ranges(n, cuts) if cuts else [(0, n)]
    out = []
    for (a, b) in ranges:
        out.append(((a, b), analyse(frames[a:b], grid=grid, anchors=anchors,
                                    pairs=pairs[a:b - 1])))
    return out, cuts
