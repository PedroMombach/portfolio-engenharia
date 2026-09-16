"""Generate raster fixtures from independent forward geometry."""

from io import BytesIO

import numpy as np
from PIL import Image, ImageDraw

from curveextractor.core.model import AxisPoint, CoordinateSystem


def fixture(angle=0, xlog=False, ylog=False, offset=False):
    radians = np.deg2rad(angle)
    rotation = np.array([[np.cos(radians), -np.sin(radians)], [np.sin(radians), np.cos(radians)]])
    scale = np.diag([700, -700])

    def pixels(uv):
        return np.asarray(uv) @ scale @ rotation.T + [120, 850]

    uv = (
        np.array([[0.15, 0.2], [0.85, 0.15], [0.2, 0.8]])
        if offset
        else np.array([[0, 0], [1, 0], [0, 1]])
    )

    def real(values):
        result = np.array(values, dtype=float)
        result[:, 0] = 10 ** (3 * result[:, 0]) if xlog else 100 * result[:, 0]
        result[:, 1] = 10 ** (2 * result[:, 1]) if ylog else 50 * result[:, 1]
        return result

    system = CoordinateSystem(
        tuple(AxisPoint(*p, *v) for p, v in zip(pixels(uv), real(uv))),
        "log" if xlog else "lin",
        "log" if ylog else "lin",
    )
    x = np.linspace(0.05, 0.95, 20)
    truth = np.column_stack([x, 0.8 - 0.5 * x**2])
    raster = Image.new("RGB", (1100, 1000), "white")
    draw = ImageDraw.Draw(raster)
    draw.line([tuple(p) for p in pixels(truth)], fill="#0072B2", width=2)
    stream = BytesIO()
    raster.save(stream, format="PNG")
    return system, np.rint(pixels(truth)), real(truth), stream.getvalue()
