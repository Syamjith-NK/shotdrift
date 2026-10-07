"""Turn measurements into a verdict, with the evidence attached to every claim.

Three severities, and the middle one earns the tool its keep. A flat pass/fail
makes every threshold an argument; `soft` lets the common case - a real camera
with a person walking through it - be reported without being blocked, so nobody
has to switch the alarm off to get work done.

Every bound here was set by MEASURING real footage and synthetic controls, and
`validate_real.py` re-derives them on demand. The requirement that shaped this
file is SILENCE ON REAL FOOTAGE: across 11 shots of real single-camera material,
no check fires. A measurement tool that flags genuine work is worse than no tool.

THREE CHECKS WERE REMOVED BECAUSE THEY DID NOT SURVIVE THAT TEST. They are
documented in calibration.md rather than quietly deleted, because what a
measurement cannot do is as useful to a reader as what it can:

  * morph / morph_rising - meant to catch a generator inventing geometry. Real
    footage reached a span-morph of 1.06 while a literal cross-dissolve between
    two different worlds read 0.358. Real scenes contain people, LED walls and
    vision mixes, so they change structure MORE than melting geometry does. No
    threshold separates them, in either direction.
  * reversal - meant to catch a move that changes direction. Real operated
    footage showed 27 direction changes on a slow zoom (an operator riding a
    rocker) against 3 in a deliberately broken control. The real material is
    "worse" than the fault, so the count carries no signal on its own. The
    question it was trying to answer is answered properly by --expect, where
    backtracked travel is measured against the move that was actually asked for.

AND ONE CHECK WAS DEMOTED FROM broken TO soft, for the third instance of exactly
that pattern: `breathing`. An operator zooming in and coming back out IS scale
oscillating without going anywhere. Measured, real operated footage reached a
ratio of 169 at an amplitude of 0.277 against 46 / 0.327 for the synthetic pulse
- so the real material is worse than the fault on the ratio and comparable on the
amplitude, and no bound in either separates them. Reported, never blocking.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .path import MOVED

CLEAN, SOFT, BROKEN, UNKNOWN = "clean", "soft", "broken", "unknown"
_RANK = {CLEAN: 0, SOFT: 1, BROKEN: 2, UNKNOWN: 0}

# --- bounds: frame-width units or dimensionless. calibration.md has the data. --
# Measured maxima over 24 real single-camera shots, two events, at the shipped
# defaults, are in brackets.
INCOHERENCE_SOFT, INCOHERENCE_BROKEN = 0.004, 0.012      # [real max 0.00068]
JERK_SOFT, JERK_BROKEN = 1.9, 2.5
# Jerk is a ratio with SPEED underneath it, so a shot has to be moving before the
# smoothness of its moving means anything. MEASURED over 16 real shots: every one
# that read above jerk 1.0 was a near-static camera, RMS speed 2.8e-4 to 3.0e-3,
# while every control with a genuine move sat at 1.4e-2 to 4.8e-2 - a 4.6x gap
# with nothing in it. Without this floor the jerkiest shot in the real set was a
# locked-off stage camera that crept 2.5% of a frame width in eleven seconds.
JERK_MIN_SPEED = 0.005                                   # frame widths per frame
WANDER_SOFT = 4.0                                        # soft-capped on purpose
WANDER_MIN_TRAVEL = 0.05                                 # must be visible travel
BREATHING_SOFT = 4.0                                     # soft-capped on purpose
# Peak-to-peak log-scale excursion a shot must show before an oscillation in it
# means anything. MEASURED over 24 real shots at the shipped configuration: 20 sit
# under this gate and the highest of those is 0.035 - a 3.5% scale wobble, which
# is a 20-frame fragment's worth of noise - while the synthetic breathing fault
# reaches 0.327. So 8.2x of headroom above and only 1.14x below, stated plainly
# because the asymmetry is real. The consequence of a real shot crossing it is a
# SOFT finding, never a block, which is what makes that margin acceptable.
BREATHING_MIN_AMP = 0.04
CLOSURE_SOFT, CLOSURE_BROKEN = 0.02, 0.06                # [real max 0.0017]
MIN_CONFIDENCE = 0.30
# Jerk is a third derivative. Below this many frame pairs it is noise, and a
# 20-frame fragment between two cuts was reported BROKEN on exactly that basis.
MIN_PAIRS_FOR_SHAPE = 16

MOVED_PAN, MOVED_ZOOM, MOVED_ROLL = MOVED["pan"], MOVED["zoom"], MOVED["roll"]


@dataclass
class Finding:
    code: str
    severity: str
    summary: str
    evidence: str
    advice: str

    def as_dict(self) -> dict:
        return dict(code=self.code, severity=self.severity, summary=self.summary,
                    evidence=self.evidence, advice=self.advice)


def _lvl(v: float, soft: float, broken: float | None) -> str:
    if not np.isfinite(v):
        return CLEAN
    if broken is not None and v >= broken:
        return BROKEN
    if v >= soft:
        return SOFT
    return CLEAN


def judge(p) -> list[Finding]:
    """Findings for a measured Path, worst first. An empty list means clean."""
    out: list[Finding] = []
    n_pairs = len(p.pairs)

    if p.confidence < MIN_CONFIDENCE or not np.isfinite(p.incoherence):
        # Not a pass and not a failure. A clip with nothing to lock onto - a dark
        # frame, a dissolve, heavy grain - cannot be judged, and saying "clean"
        # here would be the most damaging thing this tool could do.
        blind = sum(1 for q in p.pairs if q.tiles < 3)
        return [Finding(
            "unmeasurable", UNKNOWN,
            "This clip cannot be measured, so it is neither passed nor failed.",
            f"confidence {p.confidence:.2f} (floor {MIN_CONFIDENCE:.2f}); "
            f"{blind} of {n_pairs} frame pairs had too little texture to localise",
            "Usually a very dark or very flat shot, a dissolve, or heavy grain. Try "
            "--max-side 768 for more detail, or measure a window that is one shot.",
        )]

    lvl = _lvl(p.incoherence, INCOHERENCE_SOFT, INCOHERENCE_BROKEN)
    if lvl != CLEAN:
        out.append(Finding(
            "incoherent", lvl,
            "No single camera explains how different parts of the frame moved.",
            f"median tile residual {p.incoherence:.5f} of frame width "
            f"(soft {INCOHERENCE_SOFT}, broken {INCOHERENCE_BROKEN}; "
            f"real footage measures under 0.0007)",
            "Expected when a subject crosses a locked-off shot - that is not a fault. "
            "It is a fault when the whole frame should be rigid, which usually means "
            "parts of the picture are being moved independently of a camera.",
        ))

    if n_pairs >= MIN_PAIRS_FOR_SHAPE:
        moved_now = {"pan": p.net_pan >= MOVED_PAN,
                     "zoom": abs(np.log(max(p.zoom, 1e-6))) >= MOVED_ZOOM,
                     "roll": abs(p.net_roll) >= MOVED_ROLL}
        if moved_now.get(p.dominant, False) and p.speed >= JERK_MIN_SPEED:
            lvl = _lvl(p.jerk, JERK_SOFT, JERK_BROKEN)
            if lvl != CLEAN:
                out.append(Finding(
                    "jerk", lvl,
                    "The camera's speed snaps between values instead of changing smoothly.",
                    f"normalised jerk {p.jerk:.2f} on the {p.dominant} channel at speed "
                    f"{p.speed:.1e} (soft {JERK_SOFT}, broken {JERK_BROKEN})",
                    "A camera is carried by something with mass, so its velocity changes "
                    "smoothly. This is what makes a move read as synthetic even when its "
                    "start and end positions are right.",
                ))

    # Same lesson as breathing, and it bit twice: do not also demand that the net
    # displacement be under an absolute floor. The RATIO already expresses "went a
    # long way, arrived nowhere", and the absolute floor made the check miss a
    # control that travelled 0.74 of a frame width and ended 0.047 from where it
    # started. Travel gate + ratio; no net-zero condition.
    if p.path_length >= WANDER_MIN_TRAVEL:
        lvl = _lvl(p.wander, WANDER_SOFT, None)
        if lvl != CLEAN:
            out.append(Finding(
                "wander", lvl,
                "The frame moves a long way and arrives nowhere.",
                f"travelled {p.path_length:.3f} of a frame width, net displacement "
                f"{p.net_pan:.4f} (ratio {p.wander:.1f}, soft {WANDER_SOFT})",
                "If you asked for a locked-off shot, this is it failing to be locked off. "
                "Never reported as broken: a real operator reframing and coming back looks "
                "identical, and on real footage it usually is exactly that.",
            ))

    # No net-zoom condition here. Requiring the net to be ~zero let int-rounding
    # in a control push it over the line, and the ratio already expresses the
    # idea; the gate is what stops a static shot's measurement noise, divided by
    # a zero net change, reporting a tripod as "breathing 23x".
    #
    # The gate is on AMPLITUDE, not on accumulated travel, and that correction is
    # the whole story of this check. Gated on travel - a cumulative sum against a
    # fixed bound - four of seven real clips reported BROKEN, because 600 frames
    # of sub-pixel noise sums past any fixed number while the per-pair rate stays
    # flat. Amplitude does not grow with length, and it is what a viewer sees.
    if p.scale_amp >= BREATHING_MIN_AMP and len(p.pairs) >= MIN_PAIRS_FOR_SHAPE:
        lvl = _lvl(p.breathing, BREATHING_SOFT, None)
        if lvl != CLEAN:
            out.append(Finding(
                "breathing", lvl,
                "Scale oscillates without going anywhere.",
                f"accumulated absolute scale change is {p.breathing:.1f}x the net change "
                f"(amplitude {p.scale_amp:.3f}; soft {BREATHING_SOFT})",
                "The frame is pulsing, not pushing in. On a big screen it reads as the shot "
                "'swimming' even when a viewer cannot say why. Never reported as broken: an "
                "operator riding a zoom rocker in and back out is indistinguishable from "
                "this, and scores worse on it than the deliberate fault does.",
            ))

    lvl = _lvl(p.closure, CLOSURE_SOFT, CLOSURE_BROKEN)
    if lvl != CLEAN:
        out.append(Finding(
            "closure", lvl,
            "Adding up every step disagrees with measuring the first and last frame directly.",
            f"worst disagreement {p.closure:.4f} of frame width "
            f"(soft {CLOSURE_SOFT}, broken {CLOSURE_BROKEN}; real footage under 0.002)",
            "Two independent routes to the same answer did not agree, so at least one is "
            "wrong. Usually the content stopped resembling itself across the clip.",
        ))

    out.sort(key=lambda f: -_RANK[f.severity])
    return out


def worst(findings: list[Finding]) -> str:
    if not findings:
        return CLEAN
    if any(f.severity == UNKNOWN for f in findings):
        return UNKNOWN
    return max((f.severity for f in findings), key=lambda s: _RANK[s])


def at_or_above(findings: list[Finding], gate: str) -> list[Finding]:
    g = _RANK.get(gate, 1)
    return [f for f in findings if f.severity != UNKNOWN and _RANK[f.severity] >= g]
