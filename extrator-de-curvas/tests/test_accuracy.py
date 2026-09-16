import numpy as np
import pytest

from curveextractor.core.transform import Transform
from tests.fixtures.synthetic import fixture


@pytest.mark.parametrize(
    "parameters", [{}, {"angle": 3}, {"xlog": True}, {"xlog": True, "ylog": True}, {"offset": True}]
)
def test_raster_click_accuracy(parameters, tmp_path):
    system, clicks, truth, png = fixture(**parameters)
    (tmp_path / "fixture.png").write_bytes(png)
    measured = Transform(system).to_real(clicks)
    span = [999 if parameters.get("xlog") else 100, 99 if parameters.get("ylog") else 50]
    error = np.max(np.abs(measured - truth) / span, axis=0) * 100
    print(f"{parameters}: maximum full-scale errors = {error.tolist()} percent")
    assert (error < 0.5).all()
