"""Sign conventions and recovery accuracy, checked against transforms applied by
PIL rather than by shotdrift's own warp - otherwise the test and the code share
the bug."""

import numpy as np
import pytest
from PIL import Image

from shotdrift.motion import estimate_pair, phase_shift


def texture(w=256, h=256, seed=3):
    """Broadband texture with structure at several scales, so tiles localise."""
    rng = np.random.default_rng(seed)
    base = rng.random((h // 8, w // 8)).astype(np.float32)
    img = np.asarray(Image.fromarray((base * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC),
                     dtype=np.float32) / 255.0
    fine = rng.random((h, w)).astype(np.float32) * 0.25
    yy, xx = np.mgrid[0:h, 0:w]
    rings = 0.2 * np.sin(xx / 7.0) * np.cos(yy / 9.0)
    return np.clip(img * 0.7 + fine + rings, 0, 1).astype(np.float32)


def affine(img, a, b, c, d, e, f):
    im = Image.fromarray((img * 255).astype(np.uint8))
    out = im.transform(im.size, Image.AFFINE, (a, b, c, d, e, f), resample=Image.BICUBIC)
    return np.asarray(out, dtype=np.float32) / 255.0


def test_phase_shift_sign_is_content_moved_right():
    a = texture()
    b = np.roll(a, 7, axis=1)          # content moves RIGHT by 7 px, exactly
    dx, dy, peak = phase_shift(a, b)
    assert dx == pytest.approx(7.0, abs=0.25), dx
    assert dy == pytest.approx(0.0, abs=0.25), dy
    assert peak > 0.1


def test_phase_shift_sign_is_content_moved_down():
    a = texture()
    b = np.roll(a, 5, axis=0)
    dx, dy, _ = phase_shift(a, b)
    assert dy == pytest.approx(5.0, abs=0.25), dy
    assert dx == pytest.approx(0.0, abs=0.25), dx


def test_pure_pan_recovered_in_frame_width_units():
    a = texture(320, 240)
    b = np.roll(a, 8, axis=1)
    p = estimate_pair(a, b)
    assert p.tx == pytest.approx(8 / 320, abs=0.004), p.tx
    assert abs(p.ty) < 0.004
    assert abs(p.scale) < 0.006
    assert abs(p.roll) < 0.01


def test_zoom_in_gives_positive_scale():
    a = texture(288, 288)
    k = 1.06                                  # content grows by 6%
    cx = cy = (288 - 1) / 2
    b = affine(a, 1 / k, 0, cx - cx / k, 0, 1 / k, cy - cy / k)
    p = estimate_pair(a, b)
    assert p.scale == pytest.approx(0.06, abs=0.012), p.scale
    assert abs(p.tx) < 0.006 and abs(p.ty) < 0.006


def test_zoom_out_gives_negative_scale():
    a = texture(288, 288)
    k = 0.94
    cx = cy = (288 - 1) / 2
    b = affine(a, 1 / k, 0, cx - cx / k, 0, 1 / k, cy - cy / k)
    p = estimate_pair(a, b)
    assert p.scale == pytest.approx(-0.06, abs=0.012), p.scale


def test_roll_recovered_with_a_stated_sign():
    a = texture(288, 288)
    th = np.deg2rad(2.0)
    im = Image.fromarray((a * 255).astype(np.uint8))
    b = np.asarray(im.rotate(2.0, resample=Image.BICUBIC), dtype=np.float32) / 255.0
    p = estimate_pair(a, b)
    # PIL rotates COUNTER-clockwise for a positive angle. The assertion pins the
    # magnitude and the sign together so a later refactor cannot silently flip it.
    assert abs(p.roll) == pytest.approx(th, abs=0.009), p.roll
    assert p.roll < 0, "positive PIL rotation (CCW) must report negative roll"


def test_identical_frames_report_no_motion_and_no_morph():
    a = texture()
    p = estimate_pair(a, a.copy())
    assert abs(p.tx) < 1e-3 and abs(p.ty) < 1e-3
    assert abs(p.scale) < 1e-3 and abs(p.roll) < 1e-3
    assert p.morph < 0.02
    assert p.incoherence < 1e-3


def test_moving_subject_raises_incoherence_without_moving_the_camera():
    """A locked-off frame with something crossing it must NOT read as a pan."""
    a = texture(320, 320)
    b = a.copy()
    blob = texture(48, 48, seed=11)
    b[140:188, 60:108] = blob            # object at one place...
    a2 = a.copy()
    a2[140:188, 20:68] = blob            # ...was 40 px to the left
    p = estimate_pair(a2, b)
    assert abs(p.tx) < 0.015, f"subject motion leaked into the camera pan: {p.tx}"
    clean = estimate_pair(a, a.copy())
    assert p.incoherence > clean.incoherence, "disagreement was not reported"


def test_flat_frames_do_not_report_a_confident_lock():
    flat = np.full((128, 128), 0.5, dtype=np.float32)
    p = estimate_pair(flat, flat.copy())
    assert p.tiles == 0
    assert np.isnan(p.incoherence), "a frame with no texture must not claim a measurement"
