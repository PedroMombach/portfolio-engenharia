from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from curveextractor.core.errors import DomainError
from curveextractor.core.model import AxisPoint, CoordinateSystem
from curveextractor.core.transform import Transform
from tests.fixtures.synthetic import fixture


def test_round_trip():
    system, _, truth, _ = fixture(angle=3, xlog=True, ylog=True)
    solver = Transform(system)
    np.testing.assert_allclose(solver.to_real(solver.to_pixel(truth)), truth)


@pytest.mark.parametrize(
    "points,code",
    [
        ((AxisPoint(0, 0, 0, 0), AxisPoint(1, 1, 1, 1), AxisPoint(2, 2, 2, 2)), "degenerate"),
        ((), "calibration_count"),
    ],
)
def test_invalid_calibration(points, code):
    with pytest.raises(DomainError) as caught:
        Transform(CoordinateSystem(points))
    assert caught.value.code == code


def test_lock_and_independent_calibration(curve_factory):
    first, second = curve_factory(), curve_factory()
    assert first.coordinate_system is not second.coordinate_system
    first.lock()
    with pytest.raises(DomainError):
        first.points_px = ()
    with pytest.raises(DomainError):
        first.locked = False
    with pytest.raises(FrozenInstanceError):
        first.coordinate_system.points[0].px = 4
    first.name = "Renamed"


def test_log_requires_positive(curve_factory):
    with pytest.raises(DomainError, match="log_positive"):
        Transform(CoordinateSystem(curve_factory().coordinate_system.points, "log"))
