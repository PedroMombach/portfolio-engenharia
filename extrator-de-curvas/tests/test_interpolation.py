import numpy as np
import pytest

from curveextractor.core.aggregation import aggregate
from curveextractor.core.errors import DomainError
from curveextractor.core.interpolation import interpolate


@pytest.mark.parametrize("method", ["linear", "pchip"])
def test_reverse_domain_and_preserve(curve_factory, method):
    forward = curve_factory(((1, 2), (2, 4), (3, 6)))
    reverse = curve_factory(tuple(reversed(forward.points_px)))
    before = reverse.points_px
    query = [-1, 1, 1.5, 3, 4]
    np.testing.assert_allclose(
        interpolate(forward, query, method), [np.nan, 2, 3, 6, np.nan], equal_nan=True
    )
    np.testing.assert_allclose(
        interpolate(reverse, query, method), interpolate(forward, query, method), equal_nan=True
    )
    assert reverse.points_px == before


def test_fold_and_duplicate_rejected(curve_factory):
    for points in [((0, 0), (2, 2), (1, 3)), ((0, 0), (0, 1), (2, 2))]:
        with pytest.raises(DomainError, match="nonmonotonic"):
            interpolate(curve_factory(points), [1])


def test_aggregation_missing_both_ends(curve_factory):
    main = curve_factory(((0, 0), (1, 1), (2, 2), (3, 3)), "Main")
    secondary = curve_factory(((1, 2), (2, 4)), "Secondary")
    table = aggregate([main, secondary], main.id)
    assert table.incomplete_rows == 2
    assert table.incomplete_columns == ["Secondary"]
