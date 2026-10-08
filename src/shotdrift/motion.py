"""Per-frame-pair camera estimation from pixels alone.

One idea carries this whole module: **a tile grid plus a similarity fit gives the
camera parameters AND the evidence against them in the same pass.**

Measure the displacement of each tile independently, then ask whether one rigid
camera move explains all of them:

    dx = tx + s*x - r*y
    dy = ty + s*y + r*x        (x, y measured from frame centre)

The fit yields pan (tx, ty), scale change s and roll r. What the fit CANNOT
explain - the residual - is the useful half. A person walking through shot, or a
generator inventing geometry between frames, shows up as tiles that refuse to
agree with any single camera. So `incoherence` is not a separate detector bolted
on; it falls out of the same least-squares solve.

All units are fractions of the frame WIDTH, never pixels, so a bound means the
same thing on a proxy and on a master.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np

# A tile needs some texture to localise. Flat sky, a black letterbox bar or a
# blown highlight correlate with everything, and an unrejected flat tile votes
# confidently for nonsense.
MIN_TILE_STD = 0.012
MIN_PEAK = 0.06
TRIM = 0.25          # drop this fraction of worst-fitting tiles before refitting


@dataclass
class Pair:
    tx: float            # pan right, fraction of frame width per frame
    ty: float            # pan down, fraction of frame width per frame
    scale: float         # fractional size change per frame (+ = subject grows)
    roll: float          # radians per frame, + = content rotates clockwise
    incoherence: float   # median tile residual the camera model cannot explain
    morph: float         # geometry invented between frames, after alignment
    inliers: int
    tiles: int
    confidence: float

    def as_dict(self) -> dict:
        return {k: (round(v, 8) if isinstance(v, float) else v) for k, v in asdict(self).items()}


def phase_shift(a: np.ndarray, b: np.ndarray) -> tuple[float, float, float]:
    """(dx, dy, peak) such that b(x) == a(x - dx): positive dx = content moved right.

    The sign is the whole ballgame. A*conj(B) peaks at -d, so the raw peak is
    negated on the way out; getting it backwards doubles every error and makes an
    obedient take look like a drifting one. `tests/test_motion.py` is the
    authority on this, not the comment.
    """
    if a.shape != b.shape:
        raise ValueError(f"shape mismatch {a.shape} vs {b.shape}")
    win = np.outer(np.hanning(a.shape[0]), np.hanning(a.shape[1]))
    A = np.fft.fft2((a - a.mean()) * win)
    B = np.fft.fft2((b - b.mean()) * win)
    R = A * np.conj(B)
    R /= np.maximum(np.abs(R), 1e-9)
    c = np.real(np.fft.ifft2(R))
    py, px = np.unravel_index(int(np.argmax(c)), c.shape)

    def refine(i: int, n: int, line: np.ndarray) -> float:
        l, r = line[(i - 1) % n], line[(i + 1) % n]
        d = 2 * (2 * line[i] - l - r)
        off = (r - l) / d if abs(d) > 1e-9 else 0.0
        v = i + off
        return v - n if v > n / 2 else v

    dy = refine(py, c.shape[0], c[:, px])
    dx = refine(px, c.shape[1], c[py, :])
    return -float(dx), -float(dy), float(c.max())


def _tiles(h: int, w: int, grid: int) -> list[tuple[int, int, int, int]]:
    """Overlapping tiles. Overlap matters: a tile boundary that happens to land on
    the only vertical edge in frame leaves both neighbours unlocalisable."""
    th, tw = int(h / grid * 1.5), int(w / grid * 1.5)
    th = min(h, max(32, th - th % 2))
    tw = min(w, max(32, tw - tw % 2))
    ys = np.linspace(0, h - th, grid).round().astype(int)
    xs = np.linspace(0, w - tw, grid).round().astype(int)
    return [(int(y), int(x), th, tw) for y in ys for x in xs]


def _fit_similarity(pts: np.ndarray, dsp: np.ndarray, wts: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Weighted least squares for [tx, ty, s, r]; returns params and per-point residual."""
    n = len(pts)
    A = np.zeros((2 * n, 4), dtype=np.float64)
    bvec = np.zeros(2 * n, dtype=np.float64)
    x, y = pts[:, 0], pts[:, 1]
    A[0::2, 0] = 1.0
    A[0::2, 2] = x
    A[0::2, 3] = -y
    A[1::2, 1] = 1.0
    A[1::2, 2] = y
    A[1::2, 3] = x
    bvec[0::2] = dsp[:, 0]
    bvec[1::2] = dsp[:, 1]
    sw = np.repeat(np.sqrt(np.maximum(wts, 1e-6)), 2)
    p, *_ = np.linalg.lstsq(A * sw[:, None], bvec * sw, rcond=None)
    pred = (A @ p).reshape(n, 2)
    res = np.linalg.norm(pred - dsp, axis=1)
    return p, res


def _residual(pts: np.ndarray, dsp: np.ndarray, p: np.ndarray) -> np.ndarray:
    """Per-tile distance between what the camera model predicts and what was measured."""
    pred = np.stack([
        p[0] + p[2] * pts[:, 0] - p[3] * pts[:, 1],
        p[1] + p[2] * pts[:, 1] + p[3] * pts[:, 0],
    ], axis=1)
    return np.linalg.norm(pred - dsp, axis=1)


def _warp_similarity(img: np.ndarray, tx: float, ty: float, s: float, r: float) -> np.ndarray:
    """Resample `img` so it lands where the fitted camera says it should.

    Inverse map with bilinear sampling, numpy only. Out-of-frame reads clamp to
    the edge; the morph metric crops that band away rather than measuring it,
    because a clamped border is an artefact of the warp, not of the take.
    """
    h, w = img.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    cx, cy = (w - 1) / 2.0, (h - 1) / 2.0
    X = xx - cx - tx * w
    Y = yy - cy - ty * w
    k = 1.0 / (1.0 + s)
    ca, sa = np.cos(-r), np.sin(-r)
    sx = k * (ca * X - sa * Y) + cx
    sy = k * (sa * X + ca * Y) + cy
    x0 = np.clip(np.floor(sx), 0, w - 1).astype(np.int64)
    y0 = np.clip(np.floor(sy), 0, h - 1).astype(np.int64)
    x1 = np.clip(x0 + 1, 0, w - 1)
    y1 = np.clip(y0 + 1, 0, h - 1)
    fx = np.clip(sx - x0, 0.0, 1.0)
    fy = np.clip(sy - y0, 0.0, 1.0)
    return (img[y0, x0] * (1 - fx) * (1 - fy) + img[y0, x1] * fx * (1 - fy)
            + img[y1, x0] * (1 - fx) * fy + img[y1, x1] * fx * fy).astype(np.float32)


def _grad(x: np.ndarray) -> np.ndarray:
    gy, gx = np.gradient(x)
    return np.sqrt(gx * gx + gy * gy)


def _morph(a: np.ndarray, b: np.ndarray, p: np.ndarray) -> float:
    """Structure that changed after the camera move is accounted for.

    Compared in the GRADIENT domain so a lighting or exposure change does not
    read as invented geometry, and on a central crop so the warp's clamped
    border cannot inflate it.
    """
    aw = _warp_similarity(a, *p)
    h, w = b.shape
    my, mx = max(2, int(h * 0.12)), max(2, int(w * 0.12))
    ga = _grad(aw[my:h - my, mx:w - mx])
    gb = _grad(b[my:h - my, mx:w - mx])
    den = float(gb.mean()) + 1e-6
    return float(np.abs(ga - gb).mean() / den)


def estimate_pair(a: np.ndarray, b: np.ndarray, grid: int = 4) -> Pair:
    """Camera parameters taking frame `a` to frame `b`, plus what they fail to explain."""
    from .validation import integer
    integer("grid", grid, 2)
    h, w = a.shape
    pts, dsp, wts = [], [], []
    for (y, x, th, tw) in _tiles(h, w, grid):
        ta, tb = a[y:y + th, x:x + tw], b[y:y + th, x:x + tw]
        if float(ta.std()) < MIN_TILE_STD or float(tb.std()) < MIN_TILE_STD:
            continue
        dx, dy, peak = phase_shift(ta, tb)
        if peak < MIN_PEAK:
            continue
        # A tile cannot honestly report a shift larger than a third of itself:
        # beyond that the correlation peak is as likely to be an alias.
        if abs(dx) > tw / 3 or abs(dy) > th / 3:
            continue
        cxp = (x + tw / 2 - w / 2) / w
        cyp = (y + th / 2 - h / 2) / w
        pts.append((cxp, cyp))
        dsp.append((dx / w, dy / w))
        wts.append(peak * min(float(ta.std()), float(tb.std())))

    tiles = len(pts)
    if tiles < 3:
        # Not enough texture anywhere to speak about the camera. Say so instead
        # of returning a confident zero, which would read as a locked-off shot.
        dx, dy, peak = phase_shift(a, b)
        return Pair(dx / w, dy / w, 0.0, 0.0, float("nan"), float("nan"),
                    tiles, tiles, max(0.0, min(1.0, peak)))

    P = np.asarray(pts, dtype=np.float64)
    D = np.asarray(dsp, dtype=np.float64)
    W = np.asarray(wts, dtype=np.float64)

    p, res = _fit_similarity(P, D, W)
    if tiles >= 6:
        keep = np.argsort(res)[: max(3, int(round(tiles * (1 - TRIM))))]
        p, _ = _fit_similarity(P[keep], D[keep], W[keep])
        inliers = int(len(keep))
        # Incoherence is scored on ALL tiles against the TRIMMED fit. Scoring it
        # on the survivors only would hide exactly the disagreement it exists to
        # report - the trim would launder away its own evidence.
        res = _residual(P, D, p)
    else:
        inliers = tiles

    conf = float(np.clip(W.mean() / (W.mean() + 0.004), 0.0, 1.0))
    return Pair(
        tx=float(p[0]), ty=float(p[1]), scale=float(p[2]), roll=float(p[3]),
        incoherence=float(np.median(res)), morph=_morph(a, b, p),
        inliers=inliers, tiles=tiles, confidence=conf,
    )
