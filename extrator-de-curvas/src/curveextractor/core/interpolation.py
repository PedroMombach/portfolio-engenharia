"""Monotonicity checks and local ordered copies, never model mutations."""

import numpy as np
from numpy.typing import ArrayLike, NDArray
from scipy.interpolate import PchipInterpolator

from .errors import DomainError
from .model import Curve
from .transform import Transform


def ordered_points(curve: Curve) -> NDArray:
    points = Transform(curve.coordinate_system).to_real(curve.points_px)
    if len(points) < 2:
        raise DomainError("few_points", curve=curve.name)
    delta = np.diff(points[:, 0])
    if not (np.all(delta > 0) or np.all(delta < 0)):
        direction = np.sign(delta[0])
        bad = np.flatnonzero((np.sign(delta) != direction) | (delta == 0))
        raise DomainError(
            "nonmonotonic", curve=curve.name, point=int(bad[0] + 2) if len(bad) else 2
        )
    return points.copy() if delta[0] > 0 else points[::-1].copy()


def interpolate(curve: Curve, x: ArrayLike, method: str = "linear") -> NDArray:
    points = ordered_points(curve)
    query = np.asarray(x, dtype=float)
    outside = (query < points[0, 0]) | (query > points[-1, 0])
    if method == "linear":
        result = np.interp(query, points[:, 0], points[:, 1])
        result[outside] = np.nan
    elif method == "pchip":
        result = PchipInterpolator(points[:, 0], points[:, 1], extrapolate=False)(query)
        result[outside] = np.nan
    else:
        raise DomainError("method")
    return result
