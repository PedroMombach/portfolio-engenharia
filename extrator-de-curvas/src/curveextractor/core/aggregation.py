"""Build a common-X table with explicit missing-domain diagnostics."""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from .errors import DomainError
from .interpolation import interpolate, ordered_points
from .model import Curve


@dataclass
class Table:
    headers: list[str]
    values: NDArray

    @property
    def incomplete_rows(self) -> int:
        return int(np.isnan(self.values).any(axis=1).sum())

    @property
    def incomplete_columns(self) -> list[str]:
        return [h for h, missing in zip(self.headers, np.isnan(self.values).any(axis=0)) if missing]


def aggregate(
    curves: list[Curve],
    main_id: str,
    method: str = "linear",
    count: int | None = None,
    x_label: str = "X",
) -> Table:
    main = next((c for c in curves if c.id == main_id), None)
    if main is None:
        raise DomainError("main_curve")
    points = ordered_points(main)
    if count is not None and count < 2:
        raise DomainError("grid_count")
    x = points[:, 0] if count is None else np.linspace(points[0, 0], points[-1, 0], count)
    return Table(
        [x_label, *(c.name for c in curves)],
        np.column_stack([x, *(interpolate(c, x, method) for c in curves)]),
    )
