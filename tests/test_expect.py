"""The sign convention is camera-relative. These tests are the authority on it.

Getting this backwards made a correctly-measured clean pan report "x went the
other way", so it is pinned from both ends: a synthetic camera move built by
cropping a plate, and the declared move that should match it.
"""

import numpy as np
import pytest
from PIL import Image

from shotdrift.expect import MOVES, check, known
from shotdrift.path import analyse


def plate(w=760, h=760, seed=11):
    rng = np.random.default_rng(seed)
    low = rng.random((h // 10, w // 10)).astype(np.float32)
    img = np.asarray(Image.fromarray((low * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC),
                     dtype=np.float32) / 255.0
    yy, xx = np.mgrid[0:h, 0:w]
    return np.clip(img * 0.75 + rng.random((h, w)).astype(np.float32) * 0.18
                   + 0.2 * np.sin(xx / 6.0) * np.cos(yy / 8.0), 0, 1).astype(np.float32)


def crop(p, cx, cy, size, out=288):
    s = int(round(size))
    x0 = max(0, min(p.shape[1] - s, int(round(cx - s / 2))))
    y0 = max(0, min(p.shape[0] - s, int(round(cy - s / 2))))
    im = Image.fromarray((p[y0:y0 + s, x0:x0 + s] * 255).astype(np.uint8)).resize((out, out), Image.BICUBIC)
    return np.asarray(im, dtype=np.float32) / 255.0


def ease(n):
    t = np.linspace(0, 1, n)
    return t * t * (3 - 2 * t)


def pan_right_clip(n=30):
    """The CAMERA pans right: the viewport slides right across the plate."""
    p = plate()
    return np.stack([crop(p, 230 + 280 * e, 380, 380) for e in ease(n)])


def push_in_clip(n=30):
    p = plate()
    return np.stack([crop(p, 380, 380, 600 - 220 * e) for e in ease(n)])


def test_camera_panning_right_moves_the_picture_left():
    p = analyse(pan_right_clip())
    assert p.tx[-1] < 0, (
        "a camera panning right must measure as NEGATIVE picture-x; "
        f"got {p.tx[-1]:+.4f}")


def test_pan_right_is_held_and_pan_left_is_not():
    p = analyse(pan_right_clip())
    assert check(p, "pan-right").ok
    left = check(p, "pan-left")
    assert not left.ok and left.happened and not left.direction_ok


def test_push_in_is_held_and_pull_out_is_not():
    p = analyse(push_in_clip())
    assert p.zoom > 1.0, p.zoom
    assert check(p, "push-in").ok
    assert check(p, "dolly-in").ok
    out = check(p, "pull-out")
    assert not out.ok and not out.direction_ok


def test_a_pan_is_not_a_push_in():
    p = analyse(pan_right_clip())
    e = check(p, "push-in")
    assert not e.ok
    assert not e.happened, "a pure pan must not register as any amount of push-in"


def test_static_declared_on_a_moving_clip_fails_and_names_the_channel():
    p = analyse(pan_right_clip())
    e = check(p, "static")
    assert not e.ok
    assert "pan" in e.detail


def test_static_declared_on_a_still_clip_holds():
    f = plate()
    clip = np.stack([crop(f, 380, 380, 400) for _ in range(20)])
    p = analyse(clip)
    assert check(p, "locked").ok
    assert check(p, "static").ok


def test_every_move_name_resolves_and_signs_are_non_zero_except_static():
    for name in known():
        chan, sign, human = MOVES[name]
        assert human
        if chan == "none":
            assert sign == 0
        else:
            assert sign in (-1, 1)


def test_unknown_move_raises_and_lists_the_known_ones():
    f = plate()
    p = analyse(np.stack([crop(f, 380, 380, 400) for _ in range(12)]))
    with pytest.raises(KeyError) as ei:
        check(p, "crane-up")
    assert "pan-left" in str(ei.value)


def test_underscores_and_case_are_accepted():
    p = analyse(push_in_clip())
    assert check(p, "Push_In").ok
