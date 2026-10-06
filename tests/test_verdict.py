"""Verdict gating, and the two false positives that real footage exposed.

Both regressions were the same mistake - a ratio whose denominator is legitimately
zero on a static shot - so both are pinned.
"""

import numpy as np

from shotdrift.path import Path
from shotdrift.verdict import (BROKEN, CLEAN, SOFT, UNKNOWN, at_or_above, judge,
                               worst)


class FakePair:
    def __init__(self, tiles=16):
        self.tiles = tiles


def mkpath(n_pairs=40, **kw):
    """A measured-looking Path with everything quiet unless overridden."""
    z = np.zeros(n_pairs + 1)
    p = Path(tx=z.copy(), ty=z.copy(), logscale=z.copy(), roll=z.copy(),
             pairs=[FakePair() for _ in range(n_pairs)])
    p.frames = n_pairs + 1
    p.confidence = 0.95
    p.incoherence = 0.00003
    p.morph = 0.05
    p.dominant = "static"
    p.zoom = 1.0
    p.wander = 1.0
    p.breathing = 1.0
    for k, v in kw.items():
        setattr(p, k, v)
    return p


def test_quiet_path_is_clean():
    assert judge(mkpath()) == []
    assert worst([]) == CLEAN


def test_low_confidence_is_unmeasurable_not_clean_and_not_broken():
    f = judge(mkpath(confidence=0.1))
    assert [x.code for x in f] == ["unmeasurable"]
    assert worst(f) == UNKNOWN
    # An unmeasurable clip must never satisfy a CI gate by looking like a pass.
    assert at_or_above(f, SOFT) == []


def test_nan_incoherence_is_unmeasurable():
    f = judge(mkpath(incoherence=float("nan")))
    assert [x.code for x in f] == ["unmeasurable"]


def test_static_shot_with_scale_noise_is_not_breathing():
    """REGRESSION: a locked-off real camera reported 'breathing 14.8x' because the
    net scale change was legitimately zero and noise was divided by it."""
    f = judge(mkpath(breathing=14.8, scale_travel=0.0008))
    assert [x.code for x in f] == []


def test_real_pulsing_is_breathing():
    f = judge(mkpath(breathing=46.0, scale_travel=1.29))
    assert [x.code for x in f] == ["breathing"]
    assert worst(f) == BROKEN


def test_static_shot_with_jitter_is_not_wander():
    """REGRESSION: tiny jitter over a near-zero net gave an enormous ratio."""
    assert judge(mkpath(wander=31.1, path_length=0.0128)) == []


def test_real_wander_is_reported_but_never_broken():
    f = judge(mkpath(wander=25.5, path_length=0.185))
    assert [x.code for x in f] == ["wander"]
    # Soft-capped on purpose: an operator reframing and coming back looks the same.
    assert worst(f) == SOFT


def test_jerk_is_silent_below_real_footage_maximum():
    # Real single-camera footage measured up to 1.78; it must not be flagged.
    assert judge(mkpath(dominant="zoom", zoom=1.2, jerk=1.78)) == []


def test_jerk_fires_above_the_bound():
    f = judge(mkpath(dominant="zoom", zoom=1.2, jerk=2.6))
    assert [x.code for x in f] == ["jerk"]
    assert worst(f) == BROKEN


def test_shape_checks_need_enough_frame_pairs():
    """A 20-frame fragment between two cuts was reported BROKEN on a third
    derivative. Below the minimum, shape is not judged at all."""
    assert judge(mkpath(n_pairs=10, dominant="zoom", zoom=1.2, jerk=9.0)) == []


def test_jerk_ignored_on_a_channel_that_never_moved():
    assert judge(mkpath(dominant="zoom", zoom=1.0005, jerk=9.0)) == []


def test_incoherence_levels():
    assert judge(mkpath(incoherence=0.0011)) == []          # real footage maximum
    assert worst(judge(mkpath(incoherence=0.006))) == SOFT
    assert worst(judge(mkpath(incoherence=0.02))) == BROKEN


def test_closure_disagreement_is_reported():
    f = judge(mkpath(closure=0.09))
    assert [x.code for x in f] == ["closure"]
    assert worst(f) == BROKEN


def test_dropped_checks_are_really_gone():
    """morph / morph_rising / reversal did not survive validation against real
    footage. If a refactor reintroduces them, this fails."""
    f = judge(mkpath(morph=0.95, morph_trend=0.02, reversals=27,
                     dominant="zoom", zoom=1.2))
    assert [x.code for x in f] == []


def test_findings_are_sorted_worst_first():
    f = judge(mkpath(incoherence=0.02, wander=25.0, path_length=0.2))
    assert [x.severity for x in f] == [BROKEN, SOFT]


def test_gate_filters_by_severity():
    f = judge(mkpath(wander=25.5, path_length=0.185))
    assert len(at_or_above(f, SOFT)) == 1
    assert at_or_above(f, BROKEN) == []
