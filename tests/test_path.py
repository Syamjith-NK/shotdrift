"""Path integration, cut detection and the closure validity gate."""

import numpy as np
from PIL import Image

from shotdrift.motion import estimate_pair
from shotdrift.path import (CUT_MORPH, analyse, analyse_clip, find_cuts,
                            shot_ranges)
from tests.test_expect import crop, ease, plate


def push(n=30, seed=11):
    p = plate(seed=seed)
    return np.stack([crop(p, 380, 380, 600 - 220 * e) for e in ease(n)])


def test_integration_recovers_total_zoom():
    p = analyse(push())
    # viewport 600 -> 380 px, so the subject grows by 600/380
    assert p.zoom == np.testing.assert_allclose(p.zoom, 600 / 380, rtol=0.06) or True
    np.testing.assert_allclose(p.zoom, 600 / 380, rtol=0.06)
    assert p.dominant == "zoom"


def test_static_clip_is_labelled_static_not_a_pan():
    f = plate()
    p = analyse(np.stack([crop(f, 380, 380, 400) for _ in range(20)]))
    assert p.dominant == "static", (
        "sub-pixel noise on a locked-off camera must not be called a pan")


def test_shot_ranges_splits_on_cuts_and_drops_fragments():
    assert shot_ranges(100, [49]) == [(0, 50), (50, 100)]
    # a 3-frame sliver between two cuts is too short to judge
    assert shot_ranges(100, [49, 52]) == [(0, 50), (53, 100)]


def test_shot_ranges_with_no_cuts_is_the_whole_clip():
    assert shot_ranges(60, []) == [(0, 60)]


def test_a_hard_cut_is_detected_and_a_camera_move_is_not():
    a, b = push(16, seed=11), push(16, seed=29)
    spliced = np.concatenate([a, b])
    pairs = [estimate_pair(spliced[i], spliced[i + 1]) for i in range(len(spliced) - 1)]
    cuts = find_cuts(pairs)
    assert cuts == [15], f"expected the splice at 15, got {cuts}"
    # and the move itself never trips the cut bound
    assert max(q.morph for q in pairs[:15]) < CUT_MORPH


def test_analyse_clip_segments_and_reuses_the_same_pair_estimates():
    spliced = np.concatenate([push(16, seed=11), push(16, seed=29)])
    shots, cuts = analyse_clip(spliced)
    assert len(cuts) == 1
    assert len(shots) == 2
    for (a, b), p in shots:
        assert p.dominant == "zoom"
        assert len(p.pairs) == b - a - 1


def test_closure_agrees_with_the_chain_on_an_honest_clip():
    p = analyse(push())
    assert np.isfinite(p.closure)
    assert p.closure < 0.01, p.closure


def test_closure_is_nan_rather_than_huge_when_anchors_cannot_be_trusted():
    """REGRESSION: once frame 0 and frame k barely overlap, the direct estimate
    returns a confident wrong answer. It measured +0.003 where the truth was
    +0.270 and reported that as a catastrophic closure failure on a perfect clip.
    An anchor that cannot be trusted must be skipped, not believed."""
    p = plate(seed=5)
    # a long pan: frame 0 and the last frame share almost nothing
    clip = np.stack([crop(p, 180 + 11 * i, 380, 300) for i in range(26)])
    r = analyse(clip)
    assert not np.isfinite(r.closure) or r.closure < 0.02, (
        f"untrustworthy anchors leaked into closure: {r.closure}")


def test_two_frames_is_enough_and_one_is_not():
    f = plate()
    two = np.stack([crop(f, 380, 380, 400)] * 2)
    assert analyse(two).frames == 2
    try:
        analyse(two[:1])
    except ValueError:
        pass
    else:
        raise AssertionError("one frame should raise")
