# Calibration

Every threshold in `verdict.py` came from this measurement. Re-derive it with:

```console
PYTHONPATH=src python validate_real.py --write-calibration
```

The governing requirement is **silence on real footage**. A measurement tool that
flags genuine material trains the person reading it to ignore it, so a bound is
only acceptable if real single-camera footage sits clear of it. Everything below
is the evidence for that claim, including the parts that did not work out.

## Real footage — the silence requirement

Eleven shots of real single-camera material (live event cameras, 720p and 1080p,
30p and 50p, locked-off and operated, wide and long lens), measured at 320 px long
edge over the first 8 seconds. Clips containing cuts were segmented first and each
shot judged on its own.

| shot | frames | verdict | incoherence | jerk | closure | wander | breathing | conf |
|---|---|---|---|---|---|---|---|---|
| locked-off stage, 50p s0 | 400 | `clean` | 0.00003 | 0.00 | 0.00093 | 14.0 | 23.0 | 0.98 |
| multi-camera panel cut s0 | 400 | `clean` | 0.00002 | 0.00 | 0.00021 | 31.1 | 30.2 | 0.98 |
| panel Q&A, vision mix s0 | 373 | `clean` | 0.00005 | 1.34 | 0.00000 | 3.5 | 1.9 | 0.97 |
| panel Q&A, vision mix s1 | 27 | `clean` | 0.00003 | 0.00 | 0.00012 | 1.5 | 1.4 | 0.98 |
| conference stage 720p s0 | 240 | `clean` | 0.00006 | 0.00 | 0.00169 | 8.0 | 4.9 | 0.98 |
| main stage wide s0 | 20 | `clean` | 0.00000 | 0.00 | 0.00000 | 0.1 | 0.2 | 0.95 |
| main stage wide s1 | 173 | `soft` | 0.00039 | 1.78 | 0.00000 | 25.5 | 2.4 | 0.98 |
| main stage wide s2 | 20 | `clean` | 0.00040 | 1.67 | 0.00000 | 3.1 | 1.2 | 0.98 |
| main stage wide s3 | 25 | `clean` | 0.00117 | 1.37 | 0.00000 | 1.4 | 1.1 | 0.97 |
| event highlight cut s0 | 240 | `clean` | 0.00002 | 0.00 | 0.00064 | 6.1 | 9.0 | 0.98 |
| event highlight cut 2 s0 | 240 | `clean` | 0.00002 | 0.00 | 0.00044 | 9.3 | 29.8 | 0.98 |

One `soft` finding across the set: a stage camera that genuinely reframed and came
back, which is what `wander` describes. `soft` never fails a gate.

## Distributions

| metric | min | median | max | n |
|---|---|---|---|---|
| `incoherence` | 0.00000 | 0.00003 | **0.00117** | 11 |
| `jerk` | 0.00000 | 0.00000 | **1.78119** | 11 |
| `closure` | 0.00000 | 0.00012 | **0.00169** | 11 |
| `confidence` | 0.95133 | 0.98014 | **0.98357** | 11 |
| `morph` | 0.00000 | 0.05308 | **0.36264** | 11 |

The shipped bounds, and the headroom over the real maximum:

| metric | real max | soft | broken | headroom to soft |
|---|---|---|---|---|
| `incoherence` | 0.00117 | 0.004 | 0.012 | 3.4x |
| `jerk` | 1.78 | 1.9 | 2.5 | 1.07x |
| `closure` | 0.0017 | 0.02 | 0.06 | 11.8x |

`jerk` has the thinnest margin at 1.07x, and that is stated rather than smoothed
over: a heavily operated long-lens shot could report `soft jerk`. It is deliberately
set above the real maximum so it does not, and `broken` sits at 2.5 where nothing in
this set reaches — so **the jerk `broken` bound has no positive control**. It is a
conservative bound, not a validated one.

## Controls — the fault must be named

Synthetic clips built by cropping a textured plate, each with one deliberate fault.
"Something is wrong" is not a finding, so the harness asserts the specific code.

| control | verdict | named | incoherence | jerk | wander | breathing | --expect |
|---|---|---|---|---|---|---|---|
| clean push-in | `clean` | - | 0.00027 | 0.14 | 28.6 | 1.0 | HELD |
| clean pan-right | `clean` | - | 0.00001 | 0.11 | 1.0 | 2.7 | HELD |
| push-in that reverses | `clean` | - | 0.00026 | 0.11 | 25.8 | 2.3 | not held |
| pan sold as push-in | `clean` | - | 0.00001 | 0.15 | 1.0 | 2.3 | not held |
| breathing, net zero | `broken` | breathing | 0.00031 | 0.13 | 12.4 | 46.1 | not held |
| wander, net zero | `soft` | jerk,wander | 0.00003 | 2.28 | 15.7 | 5.6 | not held |
| two layers, opposite | `broken` | incoherent | 0.01706 | 0.00 | 1.3 | 3.0 | - |

Two of these exist only to pin `--expect`: *push-in that reverses* and *pan sold as
push-in* are both physically clean shots that are not the shot that was ordered. The
unprompted verdict stays conservative and the hard verdict comes from declared
intent — which is the right division, because without knowing what was asked for a
reversal is suspicious and not impossible.

`two layers, opposite` is the positive control for `incoherent`: the top half of the
frame pans one way and the bottom half the other, which no single camera can do. It
was added because `incoherent` otherwise had a bound with no control behind it, and
a bound with no control is a guess with a comment.

## Three checks did not survive, and were removed

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
- 11 real shots is a small sample, all from live-event cameras. No drone, no
  gimbal, no handheld documentary, no anamorphic, no heavy grain or film scan.
- `jerk broken` and `closure broken` have no positive control.

## Resolution stability

Measured at the shipped default of 512 px long edge. Re-run at 320 px, the maxima barely
move, which is the frame-width normalisation doing its job:

| metric | at 320 px | at 512 px |
|---|---|---|
| `incoherence` max | 0.00117 | 0.00099 |
| `jerk` max | 1.78 | 1.78 |
| `closure` max | 0.00169 | 0.00206 |

**No real shot is `broken` at either resolution.** One difference is worth knowing: a
panel shot that reads `clean` at 320 px gains a `soft breathing` at 512 px, because the
finer analysis resolves a small real scale oscillation that the coarser one averages
away. `soft` does not fail a gate, but it means a verdict at the margin can depend on
`--max-side`, so compare clips at the same setting rather than across settings.
