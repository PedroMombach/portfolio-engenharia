"""Capture transitions separate from widgets and file dialogs."""

from dataclasses import replace

from curveextractor.core.errors import DomainError
from curveextractor.core.model import AxisPoint
from curveextractor.core.transform import Transform


class CaptureFlow:
    def __init__(self):
        self.curve = None
        self.stage = 0
        self.pending = None
        self.redo_points = []
        self.free_mode = False

    def start(self, curve, duplicate=False, free_mode=False):
        self.curve = curve
        self.stage = 4 if duplicate else 1
        self.pending = None
        self.redo_points.clear()
        self.free_mode = free_mode

    def set_axis(self, x, y, values):
        if self.free_mode or self.stage == 1:
            vx, vy = values
        elif self.stage == 2:
            vx, vy = values[0], self.curve.coordinate_system.points[0].vy
        else:
            vx, vy = self.curve.coordinate_system.points[0].vx, values[0]
        self.pending = AxisPoint(x, y, vx, vy)

    def advance(self):
        if not self.curve:
            return None
        if self.stage < 4:
            if self.pending is None:
                raise DomainError("calibration_count")
            system = replace(
                self.curve.coordinate_system,
                points=(*self.curve.coordinate_system.points, self.pending),
            )
            if self.stage == 3:
                Transform(system)
            self.curve.coordinate_system = system
            self.pending = None
            self.stage += 1
            return None
        self.curve.lock()
        result = self.curve
        self.curve, self.stage = None, 0
        return result

    def point(self, x, y):
        if self.stage == 4:
            self.curve.add_point(x, y)
            self.redo_points.clear()

    def undo(self):
        if self.stage == 4 and self.curve.points_px:
            self.redo_points.append(self.curve.points_px[-1])
            self.curve.points_px = self.curve.points_px[:-1]

    def redo(self):
        if self.stage == 4 and self.redo_points:
            self.curve.add_point(*self.redo_points.pop())

    def discard(self):
        self.curve, self.stage, self.pending = None, 0, None
        self.redo_points.clear()
