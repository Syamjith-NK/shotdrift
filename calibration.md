# Calibration

The tables below are historical measurements, not a fresh validation of the
0.2.2 coverage rules. The original media are not included in this repository.
Full validation requires all configured files, sufficient frame budget, no
unmeasurable spans, and a minimum measurable shot count. Missing evidence fails
the run. Supply a JSON manifest of `label`, `path`, `sha256` entries:

```console
python validate_real.py --real-manifest /path/to/clips.json --min-real-shots 24 --write-calibration
```

Paths are relative to the manifest. Increase `--max-frames` for longer clips;
600 frames cannot validate an entire longer take. For the publicly reproducible
synthetic tests alone, run `python validate_real.py --controls-only`. That command
prints `real footage NOT VALIDATED`; it does not reproduce the tables below.

The governing requirement is **silence on real footage**. A measurement tool that
flags genuine material trains the person reading it to ignore it, so a bound is
only acceptable if real single-camera footage sits clear of it. Everything below
is the evidence for that claim, including the parts that did not work out.

## Real footage — the silence requirement

Twenty-four shots of real single-camera material from **two different events** —
different venues, camera packages and codecs; 720p, 1080p and a graded 4K opener;
30p and 50p; locked-off and operated; wide and long lens. Measured **at the tool's
own defaults** (512 px long edge, 600-frame budget, whole clip), because a control
that does not measure what ships cannot validate what ships. Clips containing cuts
were segmented first and each shot judged on its own.

| shot | frames | verdict | incoherence | jerk | speed | closure | wander | amp | breathing | conf |
|---|---|---|---|---|---|---|---|---|---|---|
| locked-off stage, 50p s0 | 600 | `clean` | 0.00002 | 0.00 | 0.00000 | 0.00067 | 21.7 | 0.0011 | 53.5 | 0.98 |
| multi-camera panel cut s0 | 600 | `clean` | 0.00002 | 0.00 | 0.00000 | 0.00050 | 52.4 | 0.0016 | 14.1 | 0.98 |
| panel Q&A, vision mix s0 | 373 | `clean` | 0.00004 | 0.00 | 0.00000 | 0.00206 | 6.8 | 0.0053 | 6.8 | 0.97 |
| panel Q&A, vision mix s1 | 68 | `clean` | 0.00004 | 0.00 | 0.00000 | 0.00135 | 1.5 | 0.0012 | 1.8 | 0.98 |
| panel Q&A, vision mix s2 | 159 | `clean` | 0.00003 | 0.00 | 0.00000 | 0.00048 | 2.4 | 0.0030 | 3.0 | 0.97 |
| conference stage 720p s0 | 600 | `clean` | 0.00006 | 0.00 | 0.00000 | 0.00045 | 36.0 | 0.0035 | 16.9 | 0.98 |
| main stage wide s0 | 20 | `clean` | 0.00000 | 0.00 | 0.00000 | 0.00000 | 0.0 | 0.0000 | 0.2 | 0.98 |
| main stage wide s1 | 173 | `soft` | 0.00044 | 1.78 | 0.00168 | 0.00000 | 39.1 | 0.0869 | 2.2 | 0.97 |
| main stage wide s2 | 20 | `clean` | 0.00068 | 1.41 | 0.00305 | 0.00000 | 7.2 | 0.0329 | 1.1 | 0.97 |
| main stage wide s3 | 379 | `soft` | 0.00062 | 1.42 | 0.00179 | 0.00000 | 5.4 | 0.1560 | 10.9 | 0.97 |
| event highlight cut s0 | 273 | `clean` | 0.00001 | 0.00 | 0.00000 | 0.00042 | 9.4 | 0.0011 | 13.0 | 0.98 |
| event highlight cut s1 | 327 | `clean` | 0.00004 | 2.35 | 0.00038 | 0.00723 | 3.1 | 0.0035 | 5.5 | 0.98 |
| event highlight cut 2 s0 | 325 | `clean` | 0.00002 | 0.00 | 0.00000 | 0.00158 | 11.1 | 0.0018 | 20.1 | 0.98 |
| event highlight cut 2 s1 | 275 | `clean` | 0.00002 | 0.00 | 0.00000 | 0.00335 | 4.4 | 0.0013 | 7.5 | 0.98 |
| opening remarks, house mix s0 | 600 | `clean` | 0.00002 | 0.00 | 0.00000 | 0.00919 | 9.8 | 0.0024 | 11.3 | 0.98 |
| panel, full answer s0 | 40 | `clean` | 0.00001 | 0.00 | 0.00000 | 0.00021 | 2.2 | 0.0003 | 7.1 | 0.99 |
| panel, full answer s1 | 27 | `clean` | 0.00001 | 0.00 | 0.00000 | 0.00009 | 1.6 | 0.0005 | 1.2 | 0.98 |
| panel, full answer s2 | 533 | `clean` | 0.00005 | 0.00 | 0.00000 | 0.00415 | 7.5 | 0.0122 | 5.8 | 0.98 |
| conference soundbite s0 | 250 | `clean` | 0.00008 | 0.00 | 0.00000 | 0.00159 | 19.3 | 0.0106 | 110.4 | 0.96 |
| conference soundbite 2 s0 | 254 | `soft` | 0.00021 | 0.73 | 0.00079 | 0.00000 | 4.6 | 0.0256 | 3.4 | 0.97 |
| graded 4K opener s0 | 110 | `clean` | 0.00002 | 0.09 | 0.00036 | 0.00214 | 1.0 | 0.0351 | 1.0 | 0.97 |
| graded 4K opener s1 | 85 | `clean` | 0.00013 | 0.22 | 0.00138 | 0.00378 | 1.4 | 0.1039 | 1.0 | 0.97 |
| graded 4K opener s2 | 80 | `clean` | 0.00017 | 0.10 | 0.00194 | 0.00368 | 1.0 | 0.1375 | 1.0 | 0.97 |
| graded 4K opener s3 | 75 | `clean` | 0.00000 | 0.00 | 0.00000 | 0.00000 | 0.0 | 0.0000 | 0.0 | 0.96 |

Three `soft` findings across the set, all of them real operator behaviour: two
stage cameras that reframed and came back (`wander`), one of which also zoomed in
and back out (`breathing`). No `broken` finding on any real shot. `soft` never
fails a gate.

## Distributions

| metric | min | median | max | n |
|---|---|---|---|---|
| `incoherence` | 0.00000 | 0.00003 | **0.00068** | 24 |
| `jerk` | 0.00000 | 0.00000 | **2.34514** | 24 |
| `closure` | 0.00000 | 0.00059 | **0.00919** | 24 |
| `confidence` | 0.96050 | 0.97596 | **0.98632** | 24 |
| `morph` | 0.00000 | 0.07658 | **0.32638** | 24 |
| `speed` | 0.00000 | — | **0.00305** | 24 |
| `scale_amp` | 0.00000 | — | **0.15605** | 24 |

The shipped bounds, and the headroom over the real maximum:

| metric | real max | gate | soft | broken | headroom to soft |
|---|---|---|---|---|---|
| `incoherence` | 0.00068 | — | 0.004 | 0.012 | 5.9x |
| `closure` | 0.00919 | — | 0.02 | 0.06 | 2.2x |
| `jerk` | 2.345 | `speed` ≥ 0.005 | 1.9 | 2.5 | gated |
| `breathing` | 110.4 | `scale_amp` ≥ 0.04 | 4.0 | *(never)* | gated |
| `wander` | 52.4 | `path_length` ≥ 0.05 | 4.0 | *(never)* | gated |

**Three of these five are gated, not thresholded, and that is the finding of this
round.** `jerk`, `breathing` and `wander` are all ratios, and on a locked-off
camera each one's denominator is legitimately near zero — so measurement noise
divided by nothing produces an enormous number on the most ordinary footage there
is. Real maxima of 2.3, 110 and 52 against soft bounds of 1.9 and 4.0 are not
near-misses; they are the ratios coming apart. The bound cannot be raised to cover
them without covering every genuine fault too. What works is refusing to judge the
quality of a move until there demonstrably *was* one:

| gate | real footage reaches | lowest control with a genuine move | gap |
|---|---|---|---|
| `speed` (jerk) | 0.00305 | 0.0144 | 4.7x |
| `scale_amp` (breathing) | 0.035 *(of the 20 shots under the gate)* | 0.327 | 9.3x |

`scale_amp`'s margin is asymmetric and stated as such: 8.2x of room above the
gate, only 1.14x below it. A real shot crossing it gets a `soft` finding, never a
block, which is what makes that margin acceptable rather than lucky.

**`jerk` keeps a `broken` bound that still has no positive control.** Three were
attempted and all three scored *below* real footage: a piecewise-constant velocity
reached 0.71, a push-in with per-frame jitter 0.26, a jittered pan 1.57, against a
real maximum of 2.35. `jerk` is RMS third-difference over RMS speed, so a few
abrupt changes inside a long smooth move average away, while continuous
small-amplitude jitter against a slow mean speed does not. It measures
high-frequency content relative to speed, which is not quite the thing its name
claims. The speed gate removes the false positives; the `broken` bound above it
remains conservative rather than validated.

## Controls — the fault must be named

Synthetic clips built by cropping a textured plate, each with one deliberate fault.
"Something is wrong" is not a finding, so the harness asserts the specific code.

| control | verdict | named | jerk | speed | wander | amp | breathing | --expect |
|---|---|---|---|---|---|---|---|---|
| clean push-in | `clean` | - | 0.14 | 0.0144 | 28.6 | 0.460 | 1.0 | HELD |
| clean pan-right | `clean` | - | 0.11 | 0.0248 | 1.0 | 0.000 | 2.7 | HELD |
| push-in that reverses | `clean` | - | 0.11 | 0.0333 | 25.8 | 0.561 | 2.3 | not held |
| pan sold as push-in | `clean` | - | 0.15 | 0.0296 | 1.0 | 0.000 | 2.3 | not held |
| breathing, net zero | `soft` | breathing | 0.13 | 0.0369 | 12.4 | 0.327 | 46.1 | not held |
| wander, net zero | `soft` | jerk,wander | 2.28 | 0.0156 | 15.7 | 0.000 | 5.6 | not held |
| two layers, opposite | `broken` | incoherent | 0.00 | 0.0481 | 1.3 | 0.010 | 3.0 | - |

Two of these exist only to pin `--expect`: *push-in that reverses* and *pan sold as
push-in* are both physically clean shots that are not the shot that was ordered. The
unprompted verdict stays conservative and the hard verdict comes from declared
intent — which is the right division, because without knowing what was asked for a
reversal is suspicious and not impossible.

`two layers, opposite` is the positive control for `incoherent`: the top half of the
frame pans one way and the bottom half the other, which no single camera can do. It
was added because `incoherent` otherwise had a bound with no control behind it, and
a bound with no control is a guess with a comment.

**`breathing, net zero` required `broken` until 0.2.0 and now requires `soft`.** Not
a weakening of the harness but a correction to it: real operated footage reached a
breathing ratio of **169 at an amplitude of 0.277**, against this control's **46 at
0.327** — worse on the ratio, comparable on the amplitude. An operator zooming in
and coming back out *is* scale oscillating without going anywhere. There is no
bound in either quantity that separates them, so the fault is still named and no
longer blocks. `--expect static` fails on it either way, which is where the hard
answer belongs: the question "is this a camera?" and the question "is this the shot
I ordered?" have different answers here, and only the second one is certain.

## Three checks did not survive, and one was demoted

### morph / morph_rising — invented geometry

The intended headline feature: catch the melting-background tell. It does not work,
and the numbers say so clearly.

Structural residual was measured over an **adaptive span** — the comparison frame
chosen so the amount of warp between the two frames stays constant, so the
resampling residue is comparable across clips:

| clip | span residual |
|---|---|
| real: main stage wide s2 | **1.062** |
| real: main stage wide s3 | 0.867 |
| real: main stage wide s1 | 0.781 |
| real: panel Q&A s0 | 0.423 |
| **control: cross-dissolve between two different worlds** | **0.358** |
| control: clean push-in | 0.114 |
| control: clean pan | 0.107 |

Real footage changes structure *more* than a literal dissolve between two unrelated
worlds, because real scenes contain people, LED walls and vision mixes. The ordering
is not marginal — it is reversed by a factor of three. No threshold separates them
in either direction, so the check is not shipped, and the dissolve control is pinned
as a **stated limitation** that must keep reading `clean`.

Per-pair morph is kept, doing the job it is genuinely good at: finding cuts. Real
within-shot footage reaches 0.36 and a cut reads 1.7–8.6.

### reversal — direction changes

| source | reversals |
|---|---|
| real: main stage wide s1 (operated slow zoom) | **27** |
| real: panel Q&A s0 | 16 |
| control: push-in that deliberately reverses twice | **3** |

An operator riding a zoom rocker reverses constantly. The real material scores nine
times worse than the deliberate fault, and normalising by clip length makes it
worse, not better. The count carries no signal on its own.

What the check was reaching for is real, and `--expect` answers it properly: given
the declared move, measure what fraction of the travel ran *backwards*. That is
intent-relative, which is where the question belonged.

## False positives found by pointing it at real footage

Three, and two shared one root cause — **a ratio whose denominator is legitimately
zero on a static shot**. All three are regression tests now.

1. **A locked-off tripod reported `breathing 14.8x`.** Net scale change on a static
   shot is genuinely zero, so sub-pixel measurement noise divided by nothing gave a
   huge ratio. Fixed by requiring absolute scale *travel* to clear a floor.
2. **Sub-pixel jitter reported as `wander`.** Same shape: path length divided by a
   near-zero net. Fixed by requiring visibly large travel (0.05 of a frame width).
   Then the fix was applied *inconsistently* — `wander` kept an additional
   net-below-floor condition which made it miss a control that travelled 0.74 of a
   frame width and ended 0.047 from where it started. The ratio plus a travel gate
   is sufficient; the net-zero condition is redundant and harmful.
3. **A 20-frame fragment between two cuts was reported `broken` on `jerk`**, a third
   derivative measured over 19 samples. Shape is no longer judged below 16 frame
   pairs.

A fourth was not a false positive but a false *negative*, and it was worse: the
first `closure` implementation believed any anchor it could compute. Once frame 0
and frame *k* barely overlap, the direct correlation returns a confident wrong
answer — measured at 5 surviving tiles and a fit residual a thousand times the
clip's own, reporting +0.003 where the truth was +0.270. Taken at face value that
reads as a catastrophic failure on a clip that is in fact perfect. An anchor now has
to earn the right to contradict the chain, and an untrustworthy one is skipped:
*cannot measure* must never be reported as *measured bad*.

## Held-out footage — the check that is not circular

The bounds above were set against the 24 shots in the calibration set, so measuring
those same shots cannot tell you whether the bounds generalise or whether they were
fitted to the sample. **21 further real clips were therefore run once, after the
thresholds were frozen, and are not in the calibration set and not used to derive
anything.** Conference soundbites, assembled previews, a one-minute panel.

| | 21 held-out clips |
|---|---|
| `broken` | **0** |
| `soft` | 7, every one `wander` |
| clean | 14 |
| failed to measure | 0 |

The same clips under the **previous** rule — `breathing` gated on accumulated scale
travel, with a `broken` bound above it — would have reported **`BROKEN` on 10 shots**.
The scale amplitudes of those ten run from **0.0036 to 0.0229**: wobbles of a third of
a percent to two percent, invisible to anyone watching. One of them reads a breathing
ratio of **273** at an amplitude of 0.0044.

That is the fix measured on footage it was not tuned against, and it is better evidence
than the calibration table above, which by construction cannot surprise anyone.

## The harness passed while the tool was wrong

The expensive one, found in 0.2.0, and the reason the defaults above are the
tool's own.

`shotdrift <clip>` reported **`BROKEN` on four of seven real clips**. This file,
at the same moment, said `VALIDATION PASSED`. Both were running the same code on
the same files.

The harness measured the **first 8 seconds**; the tool measures **600 frames** —
twelve seconds at 50p, twenty at 30p. And the quantity gating `breathing` was
`scale_travel`, the *accumulated* absolute scale change, compared against a fixed
bound of 0.01. Accumulated. Measured on a locked-off stage camera:

| frames measured | scale_travel | per-pair rate | breathing |
|---|---|---|---|
| 100 | 0.0025 | 2.51e-05 | 7.1 |
| 200 | 0.0046 | 2.29e-05 | 6.1 |
| 400 | 0.0079 | 1.98e-05 | 24.9 |
| **600** | **0.0111** | 1.86e-05 | **53.5** |
| 900 | 0.0185 | 2.05e-05 | 23.5 |
| 1200 | 0.0263 | 2.20e-05 | 65.4 |

The per-pair rate is flat at ~2e-5 at every length: nothing about the camera
changes. The cumulative sum walks straight through the gate somewhere past 500
frames, and 8 seconds at 50p is 400 — just underneath it. The calibration window
was on the safe side of a length-dependent bound, so the measurement that was
supposed to be evidence had been quietly excluded from the failure.

Two lessons, and the second is the general one:

1. **A gate on a cumulative quantity is a time bomb.** Any fixed bound on a sum
   over frames is cleared eventually by a long enough clip of a perfectly still
   camera. The replacement, `scale_amp`, is the peak-to-peak excursion of the
   scale curve: it does not grow with length, and it is also the thing a viewer
   can actually see.
2. **A control that does not run the shipped configuration validates a
   configuration nobody uses.** `--duration` now defaults to the whole clip and
   `--max-frames` to the tool's own 600. The old 8-second window is still
   available as a flag, which is how this table was produced.

## Sign conventions

Verified by `tests/test_motion.py` against transforms applied by PIL rather than by
`shotdrift`'s own warp, so the test and the code cannot share a bug.

| | measured as |
|---|---|
| content moves right | `tx` positive |
| content moves down | `ty` positive |
| subject grows | `scale` positive |
| content rotates clockwise | `roll` positive |

Declared moves in `--expect` are **camera-relative**, which inverts pan, tilt and
roll: a camera panning right makes the picture move left, so `pan-right` expects a
negative `tx`.

## What this calibration does not cover

- **No generated video is in the set.** Every clip here is either real camera
  footage or a synthetic control. The bounds are therefore validated for *not
  flagging reality* and for *naming known faults*, and are unvalidated against the
  specific failure modes of any particular generator.
- 24 real shots across two events is still a small sample, and both events are
  live corporate/conference work: tripods, long lenses and vision mixes. No drone,
  no gimbal, no handheld documentary, no anamorphic, no heavy grain or film scan.
  Three of the five bounds are now *gates* rather than thresholds precisely
  because this material is dominated by near-static cameras — which is exactly the
  footage that breaks a ratio, and exactly the footage a conference package
  produces. A handheld set would stress the opposite end and is not here.
- `jerk broken` and `closure broken` have no positive control. Three candidate
  jerk controls were built and all three scored below real footage; see the
  distributions section.
- **Nothing here is measured through the in-memory path.** `measure_frames()`
  shares `analysis_size` with the file decoder and is unit-tested against it, but
  every number in this document came in through ffmpeg.

## Resolution stability

Measured at the shipped default of 512 px long edge. Re-run at 320 px, the maxima barely
move, which is the frame-width normalisation doing its job:

| metric | at 320 px | at 512 px |
|---|---|---|
| `incoherence` max | 0.00059 | 0.00068 |
| `jerk` max | 2.316 | 2.345 |
| `closure` max | 0.01177 | 0.00919 |
| shots with a measurable `closure` | **23 of 24** | 24 of 24 |

**No real shot is `broken` at either resolution.** Two differences are worth knowing.

`closure` is the resolution-sensitive one: it runs 28% higher at 320 px, which leaves
1.7x of headroom under the `soft` bound rather than 2.2x — and at 320 px **one shot's
anchor stopped being trustworthy and was correctly skipped**, so that clip reports *not
measurable* instead of a number. That is the intended behaviour and it is the honest
cost of a coarser analysis: fewer tiles survive, and an anchor that cannot be trusted
must not be allowed to contradict the chain.

One more difference: a
panel shot that reads `clean` at 320 px gains a `soft breathing` at 512 px, because the
finer analysis resolves a small real scale oscillation that the coarser one averages
away. `soft` does not fail a gate, but it means a verdict at the margin can depend on
`--max-side`, so compare clips at the same setting rather than across settings.
