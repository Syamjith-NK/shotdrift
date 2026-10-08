"""Turn frames that are already in memory into the stack the measurement wants.

This exists so shotdrift can measure video that never became a file: a batch of
frames inside a generation graph, a sequence read by something else, an array in
a notebook. The file path in `frames.py` and this path MUST agree on the analysis
geometry or the same clip measures differently depending on how it arrived, and
every threshold in the project is expressed in fractions of the frame width - so
`analysis_size` is defined once, here, and imported by both.

No torch import. ComfyUI hands over a torch tensor and torch is a 2 GB
dependency; a tensor already knows how to become an array, so it is asked to,
through the two methods every version of it has had.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

# BT.709 luma. The file path takes ffmpeg's Y plane; these weights are the same
# question answered by the same standard. The exact coefficients do not move a
# phase correlation, but having two different greyscale definitions in one tool
# would be a silent reason for two measurements of one clip to disagree.
_LUMA = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


def analysis_size(src_w: int, src_h: int, max_side: int = 512) -> tuple[int, int]:
    """The resolution a clip is measured at: long edge capped, aspect kept, even.

    Even dimensions because the file path decodes through ffmpeg, which wants
    them; keeping the rule identical on both paths is the point of this function.
    """
    from .validation import integer
    integer("max_side", max_side, 16)
    if src_w <= 0 or src_h <= 0:
        raise ValueError(f"frame size {src_w}x{src_h} is not a picture")
    scale = min(1.0, max_side / max(src_w, src_h))
    w = max(16, int(round(src_w * scale)))
    h = max(16, int(round(src_h * scale)))
    return w - w % 2, h - h % 2


def _as_array(frames) -> np.ndarray:
    """A torch tensor, a numpy array, or anything that can become one."""
    x = frames
    for m in ("detach", "cpu"):                 # torch, in that order
        if hasattr(x, m):
            x = getattr(x, m)()
    if hasattr(x, "numpy") and not isinstance(x, np.ndarray):
        try:
            x = x.numpy()
        except Exception:                                        # noqa: BLE001
            pass
    a = np.asarray(x)
    if a.dtype == object:
        raise TypeError(
            "frames did not convert to a numeric array. Pass a numpy array, a "
            "torch tensor, or a list of same-shaped frames."
        )
    return a


def to_gray_stack(frames, max_side: int = 512) -> tuple[np.ndarray, int, int]:
    """(n, h, w) float32 in 0..1, plus the SOURCE width and height.

    Accepts (n, h, w) or (n, h, w, c) with c in 1/3/4 - which is ComfyUI's IMAGE
    layout - in uint8 0..255 or float 0..1.
    """
    a = _as_array(frames)

    if a.ndim == 4 and a.shape[-1] not in (1, 3, 4) and a.shape[1] in (1, 3, 4):
        raise ValueError(
            f"frames look channels-first {tuple(a.shape)}. shotdrift wants "
            "(n, height, width, channels); transpose with "
            "`x.permute(0, 2, 3, 1)` or `np.moveaxis(x, 1, -1)`."
        )
    if a.ndim == 4:
        if a.shape[-1] not in (1, 3, 4):
            raise ValueError(
                f"frames have {a.shape[-1]} channels; expected 1, 3 or 4."
            )
        a = a[..., 0] if a.shape[-1] == 1 else a[..., :3] @ _LUMA
    elif a.ndim != 3:
        raise ValueError(
            f"frames have shape {tuple(a.shape)}; expected (n, h, w) or "
            "(n, h, w, c)."
        )

    n, sh, sw = a.shape
    if n < 2:
        raise ValueError(
            f"got {n} frame(s). Camera motion is measured BETWEEN frames, so at "
            "least two are needed."
        )

    a = a.astype(np.float32, copy=False)
    # A float batch that is really 0..255 is a common way in, and silently
    # measuring it as if it were 0..1 would clip every frame to white.
    if a.dtype.kind in "ui" or float(np.nanmax(a)) > 1.5:
        a = a / 255.0
    a = np.clip(np.nan_to_num(a, nan=0.0), 0.0, 1.0)

    w, h = analysis_size(sw, sh, max_side)
    if (w, h) != (sw, sh):
        out = np.empty((n, h, w), dtype=np.float32)
        for i in range(n):
            im = Image.fromarray((a[i] * 255.0 + 0.5).astype(np.uint8))
            out[i] = np.asarray(im.resize((w, h), Image.BILINEAR),
                                dtype=np.float32) / 255.0
        a = out
    return np.ascontiguousarray(a), int(sw), int(sh)
