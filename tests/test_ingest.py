"""Frames that arrive in memory must measure the same as frames that arrive as a
file, and must be refused clearly when they cannot.

No torch here on purpose: the published package depends on numpy and pillow only,
so its own suite must run without a 2 GB wheel. The torch boundary is tested in
the ComfyUI node package, with real tensors, where that dependency already exists.
"""

import numpy as np
import pytest

from shotdrift.ingest import analysis_size, to_gray_stack


class FakeTensor:
    """Duck-types the two methods asked of a torch tensor, and nothing else."""

    def __init__(self, a):
        self._a = a
        self.detached = False
        self.moved = False

    def detach(self):
        self.detached = True
        return self

    def cpu(self):
        self.moved = True
        return self

    def __array__(self, dtype=None, copy=None):
        return self._a if dtype is None else self._a.astype(dtype)


def frames(n=6, h=64, w=96, c=None, dtype=np.float32):
    rng = np.random.default_rng(1)
    shape = (n, h, w) if c is None else (n, h, w, c)
    a = rng.random(shape)
    return (a * 255).astype(dtype) if dtype == np.uint8 else a.astype(dtype)


# --------------------------------------------------------------- geometry ----
def test_analysis_size_caps_the_long_edge_and_keeps_aspect():
    assert analysis_size(1920, 1080, 512) == (512, 288)
    assert analysis_size(1080, 1920, 512) == (288, 512)


def test_analysis_size_never_upscales():
    assert analysis_size(320, 180, 512) == (320, 180)


def test_analysis_size_is_always_even():
    for sw, sh in [(1001, 667), (999, 333), (1919, 1079)]:
        w, h = analysis_size(sw, sh, 512)
        assert w % 2 == 0 and h % 2 == 0


def test_analysis_size_refuses_a_non_picture():
    with pytest.raises(ValueError, match="not a picture"):
        analysis_size(0, 100, 512)


def test_file_path_and_memory_path_share_one_definition():
    """The two entry points must agree on the analysis resolution or the same
    clip measures differently depending on how it arrived - and every threshold
    in the project is a fraction of the frame width."""
    import inspect

    from shotdrift import frames as fr
    assert "analysis_size(" in inspect.getsource(fr.load)


# ------------------------------------------------------------------ shapes ---
@pytest.mark.parametrize("c", [None, 1, 3, 4])
def test_accepts_grey_and_colour_batches(c):
    stack, sw, sh = to_gray_stack(frames(c=c), max_side=512)
    assert stack.shape == (6, 64, 96) and (sw, sh) == (96, 64)
    assert stack.dtype == np.float32


def test_channels_first_is_named_not_guessed():
    """A (n, c, h, w) batch is the commonest mistake and a silent reinterpretation
    of it would measure three tall frames instead of one picture."""
    with pytest.raises(ValueError, match="channels-first"):
        to_gray_stack(np.zeros((6, 3, 64, 96), dtype=np.float32))


def test_odd_channel_count_is_refused():
    with pytest.raises(ValueError, match="channels"):
        to_gray_stack(np.zeros((6, 64, 96, 5), dtype=np.float32))


def test_wrong_rank_is_refused():
    with pytest.raises(ValueError, match="expected"):
        to_gray_stack(np.zeros((64, 96), dtype=np.float32))


def test_one_frame_is_refused_because_motion_is_between_frames():
    with pytest.raises(ValueError, match="at least two"):
        to_gray_stack(frames(n=1))


# ------------------------------------------------------------------ values ---
def test_uint8_and_float_of_the_same_clip_agree():
    """A 0..255 batch read as 0..1 clips every pixel to white and measures
    nothing at all, so the two must land in the same place."""
    f = frames(dtype=np.float32)
    a, _, _ = to_gray_stack(f)
    b, _, _ = to_gray_stack((f * 255).round().astype(np.uint8))
    assert np.abs(a - b).max() < 0.01


def test_float_batch_in_zero_to_255_is_not_clipped_to_white():
    a, _, _ = to_gray_stack(frames() * 255.0)
    assert 0.0 < float(a.mean()) < 1.0
    assert float((a >= 1.0).mean()) < 0.5


def test_nan_frames_do_not_propagate():
    f = frames()
    f[2, 10, 10] = np.nan
    a, _, _ = to_gray_stack(f)
    assert np.isfinite(a).all()


def test_a_tensor_is_detached_and_moved_before_reading():
    """Reading a tensor that still carries a graph, or sits on a GPU, is how this
    boundary breaks. Both methods must be called."""
    t = FakeTensor(frames(c=3))
    stack, _, _ = to_gray_stack(t)
    assert t.detached and t.moved
    assert stack.shape == (6, 64, 96)


def test_object_array_is_refused_with_advice():
    with pytest.raises(TypeError, match="numeric array"):
        to_gray_stack(np.array([{"not": "a frame"}, {"nor": "this"}], dtype=object))


def test_downscale_preserves_the_picture_not_just_the_shape():
    """A resize that returned zeros would pass every shape assertion above."""
    big = np.zeros((4, 400, 400), dtype=np.float32)
    big[:, 100:300, 100:300] = 1.0
    stack, _, _ = to_gray_stack(big, max_side=100)
    assert stack.shape == (4, 100, 100)
    assert stack[0, 50, 50] > 0.9 and stack[0, 5, 5] < 0.1
