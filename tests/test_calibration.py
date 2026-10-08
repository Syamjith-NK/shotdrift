"""Calibration must fail closed when its real-world evidence is unavailable."""

import importlib.util
import json
from pathlib import Path
import sys

import pytest
import shotdrift  # Load the tested installation before the standalone harness.

spec = importlib.util.spec_from_file_location("calibration_harness", Path(__file__).parents[1] / "validate_real.py")
harness = importlib.util.module_from_spec(spec)
saved_path = sys.path[:]
try:
    spec.loader.exec_module(harness)
finally:
    sys.path[:] = saved_path


@pytest.fixture
def policy_only(monkeypatch):
    # Controls are exercised separately in CI; these tests isolate dataset policy.
    monkeypatch.setattr(harness, "CONTROLS", [])
    monkeypatch.setattr(harness, "LIMITATIONS", [])


def test_missing_real_dataset_fails(policy_only, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(harness, "REAL", [("missing", str(tmp_path / "missing.mp4"))])
    assert harness.main([]) == 1
    assert "VALIDATION PASSED" not in capsys.readouterr().out


def test_empty_dataset_cannot_validate(policy_only, monkeypatch):
    monkeypatch.setattr(harness, "REAL", [])
    assert harness.main([]) == 1


def test_controls_only_does_not_claim_real_validation(policy_only, capsys):
    assert harness.main(["--controls-only"]) == 0
    text = capsys.readouterr().out
    assert "real footage NOT VALIDATED" in text and "VALIDATION PASSED" not in text


def test_manifest_content_mismatch_fails(policy_only, tmp_path, capsys):
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"different content")
    manifest = tmp_path / "clips.json"
    manifest.write_text(json.dumps([dict(label="clip", path="clip.mp4", sha256="0" * 64)]))
    assert harness.main(["--real-manifest", str(manifest)]) == 1
    assert "SHA-256 mismatch" in capsys.readouterr().out


def test_unknown_real_shot_cannot_validate(policy_only, monkeypatch):
    import numpy as np
    from shotdrift import measure_frames
    monkeypatch.setattr(harness, "REAL", [("blank", "unused")])
    monkeypatch.setattr(harness, "measure", lambda *a, **k: measure_frames(np.zeros((10, 64, 64))))
    assert harness.main([]) == 1
