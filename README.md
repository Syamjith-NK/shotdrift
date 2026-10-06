# shotdrift

**You asked for a slow push in. Measure whether you got one.**

Generative video is given a camera move and is under no obligation to deliver it.
The usual check is a person watching sixty clips and forming an impression.
`shotdrift` measures the camera path out of the pixels — pan, zoom, roll, frame by
frame — and reports whether one physical camera could have produced it.

```console
$ pip install git+https://github.com/Syamjith-NK/shotdrift
$ shotdrift pan_demo.mp4 --expect push-in
```

```
pan_demo.mp4
  1280x720 -> measured at 512x288, 97 frames @ 24 fps

  camera path
    dominant move      pan
    pan                0.7159 of frame width (x -0.7159, y -0.0000)
    zoom               1.000x
    roll               -0.00 deg
    reversals          0  (measured, not judged)
    jerk               0.35
    incoherence        0.0000
    morph              0.041  (used to find cuts, not judged)
    closure            0.0000
    confidence         0.98

  asked for: push-in
    NOT HELD - asked for push in / dolly in; zoom moved +0.0001, under the 0.02
               floor - that move did not happen

  no findings: the motion is consistent with one physical camera.
```

That clip is a perfectly good shot — smooth, coherent, one physical camera. It is
also not the shot that was ordered: it pans, and the push-in never happened. Both facts matter and they are reported
separately, because "is this a real camera move?" and "is it the move I asked
for?" are different questions.

Exit codes make it usable in a loop: `0` clean, `1` findings at or above
`--min-severity`, `2` could not run, `3` the clip could not be measured.

## Why pixels and not a solve

Nothing else is available. You are handed an mp4 by a model that will not tell you
what it did. No camera metadata, no depth, no solve — so the measurement has to
come from the frames themselves, which means it also works on footage from a
camera, a render, or a competitor's demo reel.

Everything is reported in **fractions of the frame width**, never pixels, so a
bound means the same thing on a 720p proxy and a 4K master.

## What it measures

A grid of tiles is tracked by phase correlation, then one similarity transform is
fitted to all of them:

```
dx = tx + s*x - r*y
dy = ty + s*y + r*x
```

That yields pan, scale and roll — and the part the fit **cannot** explain is the
other half of the product. If tiles refuse to agree with any single camera,
something in the frame is moving independently of one.

| | what it means |
|---|---|
| `incoherence` | tile disagreement the camera model cannot explain |
| `jerk` | third derivative of the path: a carried camera changes speed smoothly |
| `wander` | travelled a long way, arrived nowhere |
| `breathing` | scale oscillates without going anywhere |
| `closure` | adding up every step vs. measuring first-to-last directly |

`closure` is worth a sentence. The per-frame chain says where frame *k* ended up
by summing every step; measuring frame 0 against frame *k* directly asks the same
question using none of those steps. Where both are trustworthy they must agree.
It is an independent route to the same number rather than a second opinion from
the same code.

Severities are `clean`, `soft`, `broken`. `soft` exists so that a real camera with
a person walking through it can be *reported* without being *blocked* — the first
thing anyone does with a noisy alarm is stop reading it. Gate CI on
`--min-severity broken`.

## Declared moves

```console
$ shotdrift *.mp4 --expect push-in --min-severity broken
$ shotdrift --list-moves
```

`static` `locked` `push-in` `dolly-in` `zoom-in` `pull-out` `dolly-out`
`zoom-out` `pan-left` `pan-right` `tilt-up` `tilt-down` `roll-cw` `roll-ccw`

Each is checked three ways, because the three failures need different fixes:
**did it happen** at all, **was it the right way round**, and **was it held** or
did a quarter of the travel run backwards.

The signs are **camera-relative**. A camera panning right makes the picture move
left, so `pan-right` expects a negative picture-x. Writing those the intuitive way
round made a correctly measured clean pan report *"x went the other way"* — the
measurement was right and the vocabulary was wrong.

## Edited sequences

A clip containing cuts is segmented and each shot measured on its own. Run as one
take, an edited reel reported 13 reversals and a broken closure: all true, and
useless, because there were six shots and no single camera move was ever there to
hold.

Cuts come free from the morph residual already being computed. There are two
signatures, and the second nearly got missed: where structure survives the join —
a whip transition, a dissolve — morph spikes to 1.7–8.6 against the 0.36 real
within-shot footage reaches. Across a **clean** cut between unrelated shots,
nothing correlates at all, so no camera can be fitted and morph is `NaN`. The
first version only tested for the spike, so it caught smeared transitions and
walked straight past an ordinary hard cut.

Use `--no-segment` to force one measurement over everything.

## What it cannot do

This section is the useful one.

**It does not detect invented geometry.** A tool like this ought to catch the
melting-background tell, and I could not make it work. Measured over a fixed warp
budget, real footage reached a structural residual of **1.06** while a literal
cross-dissolve between two entirely different worlds read **0.358**. Real scenes
contain people, LED walls and vision mixes, so they change structure *more* than
melting geometry does. No threshold separates them in either direction, so that
check is not shipped. A dissolve under a locked-off camera comes back **clean**
here, and that is pinned as a test so it cannot quietly change.

**Direction changes are not a fault signal.** Counting reversals seemed obvious.
Real operated footage showed **27** direction changes on a slow zoom — an operator
riding a rocker — against **3** in a deliberately broken control. The real
material scores worse than the fault, so the count carries no signal alone. The
question it was trying to answer is answered properly by `--expect`, which
measures backtracked travel against the move actually requested.

**Subject motion is a confound, by construction.** A person crossing a locked-off
frame raises `incoherence`. That is reported as `soft`, with advice saying so,
rather than pretended away. Trimmed fitting rejects the worst-fitting quarter of
tiles, which handles a subject occupying part of the frame and will not save you
from one that fills it.

**Cut detection can miss a cut between two visually similar shots**, and
`closure` degrades to `NaN` once the first and last frames no longer overlap. Both
report "not measurable" rather than a number — an anchor that cannot be trusted is
skipped, because *cannot measure* must never be reported as *measured bad*.

## Calibration

Thresholds are not taste. Every bound was set by measuring real single-camera
footage and synthetic controls with known faults; `calibration.md` records the
distributions and `validate_real.py` re-derives them.

The requirement that shaped the tool is **silence on real footage**: across 11
shots of real material, nothing fires except one `soft wander` on a stage camera
that genuinely reframed and came back.

| measured over 11 real shots | max | soft at | broken at |
|---|---|---|---|
| `incoherence` | 0.00117 | 0.004 | 0.012 |
| `jerk` | 1.78 | 1.9 | 2.5 |
| `closure` | 0.0017 | 0.02 | 0.06 |

Three false positives were found by pointing it at real footage rather than at
fixtures, and two of them were the same mistake: a ratio whose denominator is
legitimately zero on a static shot. A locked-off tripod was reported as
"breathing 14.8x", and sub-pixel jitter as wander. Both are regression tests now.

## Python

```python
from shotdrift import measure

r = measure("take_07.mp4", expect="push-in")
print(r.verdict, r.ok)
for f in r.findings:
    print(f.severity, f.code, f.evidence)
```

## Requirements

Python ≥ 3.9, `numpy`, `pillow`, and **ffmpeg on PATH**. No OpenCV, no torch, no
network, no GPU. A tool that needs a 2 GB wheel to measure a camera move does not
get run.

## Development

```console
pip install -e ".[test]"
pytest -q                                  # 43 tests
PYTHONPATH=src python validate_real.py     # real footage + controls
```

MIT. Built by [Syamjith NK](https://syamjithnk.com) — cinematographer and AI
creative technologist, Abu Dhabi.
