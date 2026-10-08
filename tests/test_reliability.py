"""Regression cases from the independent functionality audit."""

import json
import shutil
import subprocess

import numpy as np
import pytest

from shotdrift import Result, measure_frames, report
from shotdrift.cli import main
from shotdrift.expect import check
from tests.test_core import _blocks, _plate, pan_right, push_in


def test_out_and_back_cannot_pass_as_static():
    plate = _plate()
    positions = np.rint(np.r_[np.linspace(0, 7, 15), np.linspace(7, 0, 15)])
    frames = np.stack([plate[100:420, 100 + int(x):420 + int(x)] for x in positions])
    r = measure_frames(frames, expect="static")
    assert r.complete and r.verdict == "clean"
    assert not r.ok and not r.expect.ok
    assert r.expect.measured > 0.02


@pytest.mark.parametrize("channel", ["logscale", "roll"])
def test_returning_scale_or_roll_is_not_static(channel):
    p = measure_frames(push_in()).path
    p.tx[:] = 0
    p.ty[:] = 0
    p.logscale[:] = 0
    p.roll[:] = 0
    getattr(p, channel)[10:20] = 0.03
    assert not check(p, "static").ok


@pytest.mark.parametrize("move", ["static", "push-in", "pan-right"])
def test_blank_cannot_hold_any_declared_move(move):
    r = measure_frames(np.zeros((20, 128, 128), np.float32), expect=move)
    assert r.verdict == "unknown" and not r.ok and not r.complete
    assert not r.expect.ok and not r.expect.measurable
    assert r.expect.happened is None
    assert "NOT MEASURABLE" in report(r)
    assert "HELD" not in report(r)
    payload = json.loads(json.dumps(r.as_dict(), allow_nan=False))
    assert payload["shots"][0]["path"]["closure"] is None
    assert payload["shots"][0]["expect"]["measured"] is None


@pytest.mark.parametrize("first_frames", [5, 30])
def test_short_segments_are_accounted_for_and_prevent_pass(first_frames):
    frames = np.concatenate([push_in(first_frames), pan_right(5, _blocks())])
    r = measure_frames(frames, expect="push-in")
    assert r.cuts and not r.complete and not r.ok and r.verdict == "unknown"
    assert len(r.shots) == len(r.cuts) + 1
    assert sum(s.frames for s in r.shots) == len(frames)
    assert r.shots[0].start == 0 and r.shots[-1].end == len(frames)
    assert all(a.end == b.start for a, b in zip(r.shots, r.shots[1:]))
    assert any(s.path is None for s in r.shots)
    assert r.as_dict()["coverage"]["unmeasured_spans"]
    json.dumps(r.as_dict(), allow_nan=False)
    assert "INCOMPLETE" in report(r)


@pytest.mark.parametrize("known", ["clean", "soft", "broken"])
@pytest.mark.parametrize("reverse", [False, True])
def test_unknown_aggregate_is_order_independent(known, reverse):
    from shotdrift import Shot
    shots = [Shot(0, 10, None, verdict=known), Shot(10, 20, None, verdict="unknown")]
    r = Result(clip="mixed", shots=shots[::-1] if reverse else shots)
    assert r.verdict == "unknown" and not r.ok


def test_empty_result_cli_is_unmeasurable(monkeypatch, capsys):
    monkeypatch.setattr("shotdrift.cli.measure", lambda *a, **kw: Result(clip="empty"))
    assert main(["empty", "--json"]) == 3
    assert json.loads(capsys.readouterr().out)["clips"][0]["verdict"] == "unknown"


def test_truncated_result_does_not_pass(monkeypatch):
    r = measure_frames(push_in(), expect="push-in")
    r.truncated = True
    assert not r.complete and not r.ok and r.verdict == "unknown"
    monkeypatch.setattr("shotdrift.cli.measure", lambda *a, **kw: r)
    assert main(["truncated"]) == 3


@pytest.mark.parametrize("args", [
    ["--grid", "0"], ["--grid", "1"], ["--anchors", "-1"],
    ["--max-side", "0"], ["--max-frames", "1"], ["--start", "nan"],
    ["--start", "-1"], ["--duration", "0"], ["--sample-fps", "inf"],
])
def test_invalid_options_are_errors_before_file_access(args, capsys):
    assert main(["does-not-exist.mp4"] + args) == 2
    assert "must be" in capsys.readouterr().err


def test_in_memory_invalid_fps_is_refused():
    with pytest.raises(ValueError, match="fps"):
        measure_frames(np.zeros((2, 32, 32)), fps=float("nan"))


@pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
                    reason="FFmpeg and FFprobe required for file boundary")
def test_real_decoder_and_cli_reject_unmeasured_segments(tmp_path, capsys):
    frames = np.concatenate([push_in(5), pan_right(5, _blocks())])
    target = tmp_path / "short.mkv"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo",
                    "-pix_fmt", "gray", "-s", "256x256", "-r", "24", "-i", "-",
                    "-c:v", "ffv1", str(target)],
                   input=np.rint(frames * 255).astype(np.uint8).tobytes(), check=True)
    assert main([str(target), "--expect", "push-in", "--json"]) == 3
    payload = json.loads(capsys.readouterr().out)["clips"][0]
    assert not payload["coverage"]["complete"] and not payload["ok"]
