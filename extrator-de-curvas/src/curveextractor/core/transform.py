"""One affine solver for assisted and arbitrary linear/log calibration."""

import numpy as np
from numpy.typing import ArrayLike, NDArray

from .errors import DomainError
from .model import AxisPoint, CoordinateSystem


class Transform:
    def __init__(self, system: CoordinateSystem) -> None:
        self.system = system
        if len(system.points) != 3:
            raise DomainError("calibration_count")
        if system.x_scale not in {"lin", "log"} or system.y_scale not in {"lin", "log"}:
            raise DomainError("scale")
        try:
            pixels = np.array([[p.px, p.py, 1] for p in system.points], dtype=float)
            values = np.array([[p.vx, p.vy] for p in system.points], dtype=float)
        except (ValueError, TypeError) as exc:
            raise DomainError("finite") from exc
        if not np.isfinite(pixels).all() or not np.isfinite(values).all():
            raise DomainError("finite")
        values = self._linearize(values)
        try:
            self.affine = np.linalg.solve(pixels, values).T
            self.inverse = np.linalg.inv(self.affine[:, :2])
        except np.linalg.LinAlgError as exc:
            raise DomainError("degenerate") from exc

    def _linearize(self, values: NDArray) -> NDArray:
        result = values.copy()
        for axis, scale in enumerate((self.system.x_scale, self.system.y_scale)):
            if scale == "log":
                if np.any(result[..., axis] <= 0):
                    raise DomainError("log_positive")
                result[..., axis] = np.log10(result[..., axis])
        return result

    def to_real(self, points: ArrayLike) -> NDArray:
        pixels = np.asarray(points, dtype=float).reshape(-1, 2)
        if not np.isfinite(pixels).all():
            raise DomainError("finite")
        result = pixels @ self.affine[:, :2].T + self.affine[:, 2]
        for axis, scale in enumerate((self.system.x_scale, self.system.y_scale)):
            if scale == "log":
                with np.errstate(over="ignore"):
                    result[:, axis] = 10 ** result[:, axis]
        if not np.isfinite(result).all():
            raise DomainError("finite")
        return result

    def to_pixel(self, points: ArrayLike) -> NDArray:
        values = np.asarray(points, dtype=float).reshape(-1, 2)
        if not np.isfinite(values).all():
            raise DomainError("finite")
        return (self._linearize(values) - self.affine[:, 2]) @ self.inverse.T


def assisted(
    points: list[tuple[float, float]],
    xmin: float,
    xmax: float,
    ymin: float,
    ymax: float,
    x_scale: str = "lin",
    y_scale: str = "lin",
) -> CoordinateSystem:
    values = ((xmin, ymin), (xmax, ymin), (xmin, ymax))
    if len(points) != 3:
        raise DomainError("calibration_count")
    system = CoordinateSystem(
        tuple(AxisPoint(*p, *v) for p, v in zip(points, values)), x_scale, y_scale
    )
    Transform(system)
    return system
