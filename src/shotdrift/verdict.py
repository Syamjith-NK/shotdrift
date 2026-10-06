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
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .path import MOVED

CLEAN, SOFT, BROKEN, UNKNOWN = "clean", "soft", "broken", "unknown"
_RANK = {CLEAN: 0, SOFT: 1, BROKEN: 2, UNKNOWN: 0}

# --- bounds: frame-width units or dimensionless. calibration.md has the data. --
# Measured maxima over 11 real single-camera shots are in brackets.
INCOHERENCE_SOFT, INCOHERENCE_BROKEN = 0.004, 0.012      # [real max 0.00117]
JERK_SOFT, JERK_BROKEN = 1.9, 2.5                        # [real max 1.78]
WANDER_SOFT = 4.0                                        # soft-capped on purpose
WANDER_MIN_TRAVEL = 0.05                                 # must be visible travel
BREATHING_SOFT, BREATHING_BROKEN = 4.0, 10.0
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
            f"real footage measures under 0.0012)",
            "Expected when a subject crosses a locked-off shot - that is not a fault. "
            "It is a fault when the whole frame should be rigid, which usually means "
            "parts of the picture are being moved independently of a camera.",
        ))

    if n_pairs >= MIN_PAIRS_FOR_SHAPE:
        moved_now = {"pan": p.net_pan >= MOVED_PAN,
                     "zoom": abs(np.log(max(p.zoom, 1e-6))) >= MOVED_ZOOM,
                     "roll": abs(p.net_roll) >= MOVED_ROLL}
        if moved_now.get(p.dominant, False):
            lvl = _lvl(p.jerk, JERK_SOFT, JERK_BROKEN)
            if lvl != CLEAN:
                out.append(Finding(
                    "jerk", lvl,
                    "The camera's speed snaps between values instead of changing smoothly.",
                    f"normalised jerk {p.jerk:.2f} on the {p.dominant} channel "
                    f"(soft {JERK_SOFT}, broken {JERK_BROKEN}; real footage reaches 1.78)",
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
    # idea; the absolute travel gate is what stops a static shot's measurement
    # noise, divided by a zero net change, reporting a tripod as "breathing 23x".
    if p.scale_travel >= MOVED_ZOOM:
        lvl = _lvl(p.breathing, BREATHING_SOFT, BREATHING_BROKEN)
        if lvl != CLEAN:
            out.append(Finding(
                "breathing", lvl,
                "Scale oscillates without going anywhere.",
                f"accumulated absolute scale change is {p.breathing:.1f}x the net change "
                f"(travel {p.scale_travel:.3f}; soft {BREATHING_SOFT}, broken {BREATHING_BROKEN})",
                "The frame is pulsing, not pushing in. On a big screen it reads as the shot "
                "'swimming' even when a viewer cannot say why.",
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
