"""Check a measured path against the move that was ASKED for.

This is the part that does not exist elsewhere. Everything else here describes
what a clip did; this asks whether it did what it was told, which is the actual
question when you type "slow push in" into a generator and get back something
that drifts left.

A declared move is checked three ways, because each failure is different and the
distinction is what makes the output useful:
  happened  - is there any motion on that channel at all?
  direction - is it the way round you asked?
  held      - was it monotonic, or did it wobble there?
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# name -> (channel, sign, human); sign 0 means "must not move"
# THE SIGNS ARE CAMERA-RELATIVE, NOT CONTENT-RELATIVE, and that is the one thing
# in this file worth reading twice. A camera panning RIGHT makes the picture move
# LEFT, so "pan-right" expects a NEGATIVE x. Writing these the intuitive way round
# made a correctly-measured clean pan report "x went the other way" - the
# measurement was right and the vocabulary was wrong. Verified by test.
MOVES: dict[str, tuple[str, int, str]] = {
    "static":    ("none", 0, "locked off"),
    "locked":    ("none", 0, "locked off"),
    "push-in":   ("zoom", +1, "push in / dolly in"),    # subject grows
    "dolly-in":  ("zoom", +1, "push in / dolly in"),
    "zoom-in":   ("zoom", +1, "zoom in"),
    "pull-out":  ("zoom", -1, "pull out / dolly out"),
    "dolly-out": ("zoom", -1, "pull out / dolly out"),
    "zoom-out":  ("zoom", -1, "zoom out"),
    "pan-left":  ("x", +1, "pan left"),                 # camera left  -> picture right
    "pan-right": ("x", -1, "pan right"),                # camera right -> picture left
    "tilt-up":   ("y", +1, "tilt up"),                  # camera up    -> picture down
    "tilt-down": ("y", -1, "tilt down"),
    "roll-cw":   ("roll", -1, "roll clockwise"),        # camera cw    -> picture ccw
    "roll-ccw":  ("roll", +1, "roll counter-clockwise"),
}

# A move has to clear this to count as having happened at all, in frame widths
# (or radians / log-scale). Below it, the honest answer is "nothing happened".
FLOOR = {"x": 0.02, "y": 0.02, "zoom": 0.02, "roll": 0.02}
# Fraction of the travel allowed to run backwards before the move is not "held".
BACKTRACK_OK = 0.25


@dataclass
class Expectation:
    move: str
    ok: bool
    happened: bool | None
    direction_ok: bool | None
    held: bool | None
    measured: float | None
    backtrack: float | None
    detail: str
    measurable: bool = True

    def as_dict(self) -> dict:
        return dict(move=self.move, ok=self.ok, happened=self.happened,
                    direction_ok=self.direction_ok, held=self.held,
                    measured=round(self.measured, 5) if self.measured is not None else None,
                    backtrack=round(self.backtrack, 4) if self.backtrack is not None else None,
                    detail=self.detail, measurable=self.measurable)


def known() -> list[str]:
    return sorted(MOVES)


def _series(p, chan: str) -> np.ndarray:
    if chan == "x":
        return np.asarray(p.tx, dtype=float)
    if chan == "y":
        return np.asarray(p.ty, dtype=float)
    if chan == "zoom":
        return np.asarray(p.logscale, dtype=float)
    if chan == "roll":
        return np.asarray(p.roll, dtype=float)
    raise KeyError(chan)


def _key(move: str) -> str:
    key = move.strip().lower().replace("_", "-")
    if key not in MOVES:
        raise KeyError(f"unknown move {move!r}; known: {', '.join(known())}")
    return key


def unmeasurable(move: str) -> Expectation:
    return Expectation(_key(move), False, None, None, None, None, None,
                       "the requested move could not be measured", measurable=False)


def check(p, move: str) -> Expectation:
    from .verdict import MIN_CONFIDENCE

    key = _key(move)
    if (p is None or not np.isfinite(p.confidence)
            or p.confidence < MIN_CONFIDENCE or not np.isfinite(p.incoherence)):
        return unmeasurable(key)
    chan, sign, human = MOVES[key]

    if chan == "none":
        # "Locked off" is a claim about every channel at once, so it is the one
        # case that cannot be judged on a single series.
        # Check every point, including moves that return to the starting pose.
        pan = float(np.max(np.hypot(p.tx - p.tx[0], p.ty - p.ty[0])))
        worst_name, worst_val, worst_floor = "pan", pan, FLOOR["x"]
        for nm, val, fl in (("pan", pan, FLOOR["x"]),
                            ("zoom", float(np.ptp(p.logscale)), FLOOR["zoom"]),
                            ("roll", float(np.ptp(p.roll)), FLOOR["roll"])):
            if val / fl > worst_val / worst_floor:
                worst_name, worst_val, worst_floor = nm, val, fl
        still = worst_val < worst_floor
        return Expectation(
            move=key, ok=still, happened=not still, direction_ok=still, held=still,
            measured=worst_val, backtrack=0.0,
            detail=(f"locked off as asked; largest movement was {worst_name} "
                    f"{worst_val:.4f} (floor {worst_floor})") if still else
                   (f"asked for {human}, but {worst_name} moved {worst_val:.4f}, "
                    f"over the {worst_floor} floor"),
        )

    s = _series(p, chan)
    net = float(s[-1] - s[0])
    step = np.diff(s)
    travel = float(np.sum(np.abs(step))) or 1e-9
    against = float(np.sum(np.abs(step[np.sign(step) == -sign])))
    backtrack = against / travel

    happened = abs(net) >= FLOOR[chan]
    direction_ok = bool(np.sign(net) == sign) if happened else False
    held = backtrack <= BACKTRACK_OK
    ok = happened and direction_ok and held

    if not happened:
        detail = (f"asked for {human}; {chan} moved {net:+.4f}, under the "
                  f"{FLOOR[chan]} floor - that move did not happen")
    elif not direction_ok:
        detail = (f"asked for {human}; {chan} went the other way, {net:+.4f}")
    elif not held:
        detail = (f"{human} happened ({net:+.4f}) but {backtrack * 100:.0f}% of the "
                  f"travel ran backwards - the move is not held")
    else:
        detail = f"{human} as asked: {chan} {net:+.4f}, {backtrack * 100:.0f}% backtrack"
    return Expectation(key, ok, happened, direction_ok, held, net, backtrack, detail)
