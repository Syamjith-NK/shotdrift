"""Validate measurement options before decoding or allocating arrays."""

import math
from numbers import Integral, Real


def integer(name, value, minimum):
    if isinstance(value, bool) or not isinstance(value, Integral) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


def finite(name, value, minimum=0.0, *, positive=False):
    if (isinstance(value, bool) or not isinstance(value, Real)
            or not math.isfinite(value) or value < minimum
            or (positive and value == minimum)):
        op = ">" if positive else ">="
        raise ValueError(f"{name} must be finite and {op} {minimum:g}")


def analysis_options(grid, anchors):
    integer("grid", grid, 2)
    integer("anchors", anchors, 0)
