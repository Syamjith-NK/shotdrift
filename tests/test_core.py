"""The library API must answer the same question the command line answers.

It did not. `measure()` called `analyse` where the CLI calls `analyse_clip`, so
the Python API never segmented: an edited sequence was measured as one take, which
is the failure the CLI was explicitly fixed for. Pinned here, both ways round.
"""

import numpy as np
import pytest
from PIL import Image

from shotdrift import Result, measure_frames, report


def _plate(w=560, h=560, seed=4):
    """A textured world. The fine detail is SEEDED too, deliberately: with a
    fixed sin/cos term, two plates built from different random seeds still share
    a strong periodic pattern, correlate across a hard cut, and the cut is not
    detected - which looked like a weakness in cut detection and was a flaw in
    the fixture.
    """
    rng = np.random.default_rng(seed)
    low = rng.random((h // 10, w // 10)).astype(np.float32)
    img = np.asarray(
        Image.fromarray((low * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC),
        dtype=np.float32) / 255.0
    yy, xx = np.mgrid[0:h, 0:w]
    fx, fy = 4.0 + seed % 5, 6.0 + seed % 7
    return np.clip(img * 0.72 + 0.2 * np.sin(xx / fx) * np.cos(yy / fy)
                   + 0.12 * rng.random((h, w)), 0, 1).astype(np.float32)


def _crop(p, cx, cy, size, out=256):
    h, w = p.shape
    s = int(round(size))
    x0 = max(0, min(w - s, int(round(cx - s / 2))))
    y0 = max(0, min(h - s, int(round(cy - s / 2))))
    im = Image.fromarray((p[y0:y0 + s, x0:x0 + s] * 255).astype(np.uint8))
    return np.asarray(im.resize((out, out), Image.BICUBIC), dtype=np.float32) / 255.0


def push_in(n=30, plate=None):
    p = _plate() if plate is None else plate
    t = np.linspace(0, 1, n)
    ease = t * t * (3 - 2 * t)
    return np.stack([_crop(p, 280, 280, 460 - 170 * e) for e in ease])


def pan_right(n=30, plate=None):
    p = _plate() if plate is None else plate
    t = np.linspace(0, 1, n)
    ease = t * t * (3 - 2 * t)
    return np.stack([_crop(p, 170 + 220 * e, 280, 280) for e in ease])


def _blocks(w=560, h=560, seed=31):
    """A world with genuinely different STRUCTURE, not just a different seed.

    Measured while writing these tests: a cut between two plates from the same
    generator reads morph 0.62 - under the 0.8 cut bound - because they share a
    spectrum and a luminance distribution however the seed differs, so a "hard
    cut" between them is not a hard cut. Against hard-edged blocks the same join
    reads 2.51, which is inside the 1.7-8.6 band real cuts measure at. A fixture
    sitting on the wrong side of a bound tests the fixture.
    """
    rng = np.random.default_rng(seed)
    low = (rng.random((14, 14)) > 0.5).astype(np.float32)
    im = Image.fromarray((low * 255).astype(np.uint8)).resize((w, h), Image.NEAREST)
    return np.asarray(im, dtype=np.float32) / 255.0


def two_shots():
    """A push-in on one world, a hard cut, a pan on an unrelated one."""
    return np.concatenate([push_in(30, _plate(seed=4)),
                           pan_right(30, _blocks(seed=31))])


# ----------------------------------------------------------- segmentation ----
def test_a_cut_is_detected_and_each_shot_measured_on_its_own():
    r = measure_frames(two_shots())
    assert len(r.cuts) == 1
    assert len(r.shots) == 2
    assert {s.path.dominant for s in r.shots} == {"zoom", "pan"}


def test_no_segment_measures_the_batch_as_one_take():
    r = measure_frames(two_shots(), segment=False)
    assert r.cuts == [] and len(r.shots) == 1


def test_a_single_shot_result_still_reads_like_one_shot():
    r = measure_frames(push_in(), expect="push-in")
    assert len(r.shots) == 1
    assert r.verdict == r.shots[0].verdict
    assert r.path is r.shots[0].path
    assert r.expect is r.shots[0].expect


# ------------------------------------------------------- clip-level views ----
def test_dominant_path_is_the_longest_shot_not_the_first():
    frames = np.concatenate([push_in(20, _plate(seed=4)),
                             pan_right(40, _blocks(seed=31))])
    r = measure_frames(frames)
    assert len(r.shots) == 2
    assert r.path is max(r.shots, key=lambda s: s.frames).path
    assert r.path.dominant == "pan"


def test_verdict_is_the_worst_shot_not_an_average():
    r = measure_frames(two_shots())
    r.shots[0].verdict = "broken"
    r.shots[1].verdict = "clean"
    assert r.verdict == "broken"


def test_expect_reports_the_shot_that_failed_it():
    """On an edited sequence the useful answer is the shot that did NOT hold the
    move, not whichever shot happens to be first or longest."""
    r = measure_frames(two_shots(), expect="push-in")
    assert any(s.expect.ok for s in r.shots)
    assert not r.expect.ok
    assert r.ok is False


def test_ok_requires_every_shot_to_hold_the_move():
    assert measure_frames(push_in(), expect="push-in").ok is True
    assert measure_frames(pan_right(), expect="push-in").ok is False


def test_an_empty_result_is_unknown_not_clean():
    """A clip that produced no shots must never satisfy a gate by looking clean."""
    r = Result(clip="nothing")
    assert r.verdict == "unknown"
    assert r.ok is False


# -------------------------------------------------------------- reporting ----
def test_report_renders_every_shot_with_its_span():
    r = measure_frames(two_shots(), expect="push-in")
    text = report(r)
    assert "1 cut(s) detected" in text
    assert text.count("camera path") == 2
    assert "shot 0-" in text and "HELD" in text


def test_report_is_a_string_and_ends_with_a_newline():
    text = report(measure_frames(push_in()))
    assert isinstance(text, str) and text.endswith("\n")


def test_quiet_drops_the_advice_but_keeps_the_evidence():
    from shotdrift.verdict import Finding
    r = measure_frames(pan_right())
    r.shots[0].findings.append(
        Finding("x", "soft", "a summary", "some evidence", "ADVICE-MARKER"))
    assert "evidence: some evidence" in report(r, quiet=True)
    assert "ADVICE-MARKER" not in report(r, quiet=True)
    assert "ADVICE-MARKER" in report(r, quiet=False)


def test_cli_and_library_print_the_same_report():
    """The CLI must not own a second copy of these words."""
    import inspect

    from shotdrift import cli
    src = inspect.getsource(cli)
    assert "report(r" in src
    assert "camera path" not in src


# ------------------------------------------------------------------- json ----
def test_as_dict_is_json_serialisable_and_keeps_its_shape():
    import json
    d = measure_frames(two_shots(), expect="push-in").as_dict()
    assert sorted(d) == ["clip", "coverage", "cuts", "measured_at", "ok", "shots", "source", "verdict"]
    assert sorted(d["shots"][0]) == ["expect", "findings", "frames", "path", "verdict"]
    json.dumps(d)                                  # must not raise


def test_measure_frames_records_the_source_size_not_the_analysis_size():
    r = measure_frames(np.stack([_crop(_plate(), 280, 280, 400, out=600)] * 4
                                + [_crop(_plate(), 282, 280, 400, out=600)]),
                       max_side=256)
    assert (r.src_width, r.src_height) == (600, 600)
    assert (r.width, r.height) == (256, 256)


def test_a_name_can_be_given_so_a_report_is_identifiable():
    assert "take_07" in report(measure_frames(push_in(), name="take_07"))


def test_unknown_move_is_refused():
    with pytest.raises(KeyError):
        measure_frames(push_in(), expect="crash-zoom-through-a-window")
