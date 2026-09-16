"""Core hydraulic models for pump selection.

The module intentionally keeps spreadsheet and database concerns out of the
calculation layer.  Pump curves are immutable arrays, while generated curves
are cached by their operating frequency inside :class:`Pump`.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Iterable, Mapping
import math
import warnings

import numpy as np


CURVE_COLUMNS = ("Q", "H", "Eta1", "NPSH")
FREQUENCY_KEY_DIGITS = 6
SARBU_BORZA_EXPONENT = 0.1


def atmospheric_pressure_head(altitude_m: float) -> float:
    """Return atmospheric pressure head in metres of water.

    Standard-atmosphere expression with a 20 degC reference temperature.
    """

    altitude_m = float(altitude_m)
    g = 9.80665
    rho_w = 997.8
    p0 = 101325 / (g * rho_w)
    cp = 1004.68506
    t0 = 20 + 273.15
    molar_mass = 0.02896968
    gas_constant = 8.314462618
    base = 1 - g * altitude_m / (cp * t0)
    if base <= 0:
        raise ValueError("altitude is outside the valid range of the model")
    return float(p0 * base ** (cp * molar_mass / gas_constant))


def _required_float(value: object, field: str) -> float:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        raise ValueError(f"missing required metadata field: {field}")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid numeric metadata field {field}: {value!r}") from exc


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else number


@dataclass(frozen=True)
class PumpMetadata:
    """General pump and motor data for one unique pump identifier."""

    pump_id: str
    manufacturer: str
    model: str
    poles: int
    base_speed_rpm: float
    base_frequency_hz: float
    motor_efficiency: float
    motor_power_kw: float
    minimum_submergence_mm: float
    impeller_axis_mm: float
    voltage_v: float | str
    mass_kg: float | None
    q_bep_lps: float
    head_bep_m: float
    efficiency_bep: float
    npshr_bep_m: float | None

    def __post_init__(self) -> None:
        if not self.pump_id.strip():
            raise ValueError("pump_id cannot be blank")
        if self.poles <= 0:
            raise ValueError("poles must be positive")
        if self.base_speed_rpm <= 0 or self.base_frequency_hz <= 0:
            raise ValueError("base speed and base frequency must be positive")
        if not 0 < self.motor_efficiency <= 1:
            raise ValueError("motor_efficiency must be in (0, 1]")
        if self.motor_power_kw <= 0:
            raise ValueError("motor_power_kw must be positive")
        if self.q_bep_lps <= 0 or self.head_bep_m < 0:
            raise ValueError("BEP flow must be positive and BEP head cannot be negative")
        if not 0 <= self.efficiency_bep <= 1:
            raise ValueError("efficiency_bep must be in [0, 1]")

    @property
    def base_synchronous_speed_rpm(self) -> float:
        return 120 * self.base_frequency_hz / self.poles

    @property
    def base_slip(self) -> float:
        synchronous = self.base_synchronous_speed_rpm
        return (synchronous - self.base_speed_rpm) / synchronous

    @property
    def suction_head_m(self) -> float:
        """Water level above the impeller axis at minimum submergence."""

        return (self.minimum_submergence_mm - self.impeller_axis_mm) * 1e-3

    @classmethod
    def from_mapping(cls, row: Mapping[str, object]) -> "PumpMetadata":
        """Build metadata from one row of the ``Metadata`` worksheet."""

        return cls(
            pump_id=str(row["ID"]).strip(),
            manufacturer=str(row["manufacturer"]).strip(),
            model=str(row["model"]).strip(),
            poles=int(_required_float(row.get("poles"), "poles")),
            base_speed_rpm=_required_float(row.get("baseSpeedRPM"), "baseSpeedRPM"),
            base_frequency_hz=_required_float(row.get("baseFreq", 60.0), "baseFreq"),
            motor_efficiency=_required_float(row.get("motorEfficiency"), "motorEfficiency"),
            motor_power_kw=_required_float(row.get("motorPowerKW"), "motorPowerKW"),
            minimum_submergence_mm=_required_float(row.get("minSubmergenceMM"), "minSubmergenceMM"),
            impeller_axis_mm=_required_float(row.get("impellerAxisMM"), "impellerAxisMM"),
            voltage_v=row.get("voltageV"),
            mass_kg=_optional_float(row.get("massKG")),
            q_bep_lps=_required_float(row.get("Qbep"), "Qbep"),
            head_bep_m=_required_float(row.get("Hbep"), "Hbep"),
            efficiency_bep=_required_float(row.get("Eta1bep"), "Eta1bep"),
            npshr_bep_m=_optional_float(row.get("NPSHbep")),
        )


@dataclass(frozen=True)
class PumpCurve:
    """Immutable H-Q, efficiency and NPSHr data at one frequency."""

    frequency_hz: float
    q_lps: np.ndarray
    head_m: np.ndarray
    efficiency: np.ndarray
    npshr_m: np.ndarray

    def __post_init__(self) -> None:
        frequency = float(self.frequency_hz)
        if frequency <= 0:
            raise ValueError("frequency_hz must be positive")
        object.__setattr__(self, "frequency_hz", frequency)

        arrays = []
        for name in ("q_lps", "head_m", "efficiency", "npshr_m"):
            value = np.array(getattr(self, name), dtype=float, copy=True)
            if value.ndim != 1:
                raise ValueError(f"{name} must be one-dimensional")
            value.setflags(write=False)
            object.__setattr__(self, name, value)
            arrays.append(value)

        lengths = {len(value) for value in arrays}
        if len(lengths) != 1 or not lengths or next(iter(lengths)) < 2:
            raise ValueError("curve arrays must have the same length and at least two points")
        if not np.isfinite(self.q_lps).all() or not np.isfinite(self.head_m).all():
            raise ValueError("Q and H must be finite")
        if not np.isfinite(self.efficiency).all():
            raise ValueError("efficiency must be finite")
        if np.any(np.diff(self.q_lps) <= 0):
            raise ValueError("Q values must be strictly increasing")
        if self.q_lps[0] < 0 or np.any(self.head_m < 0):
            raise ValueError("Q and H cannot be negative")
        if np.any((self.efficiency < 0) | (self.efficiency > 1)):
            raise ValueError("efficiency must be in [0, 1]")

    @classmethod
    def from_dataframe(cls, frequency_hz: float, dataframe: object) -> "PumpCurve":
        missing = set(CURVE_COLUMNS) - set(dataframe.columns)
        if missing:
            raise ValueError(f"curve is missing columns: {sorted(missing)}")
        data = dataframe.loc[:, CURVE_COLUMNS].copy()
        for column in CURVE_COLUMNS:
            data[column] = data[column].astype(float)
        data = data.sort_values("Q").reset_index(drop=True)
        return cls(
            frequency_hz=frequency_hz,
            q_lps=data["Q"].to_numpy(),
            head_m=data["H"].to_numpy(),
            efficiency=data["Eta1"].to_numpy(),
            npshr_m=data["NPSH"].to_numpy(),
        )

    def to_dataframe(self):
        import pandas as pd

        return pd.DataFrame(
            {
                "Q": self.q_lps.copy(),
                "H": self.head_m.copy(),
                "Eta1": self.efficiency.copy(),
                "NPSH": self.npshr_m.copy(),
            }
        )

    def interpolate(self, q_lps: float, field: str) -> float | None:
        q_lps = float(q_lps)
        if q_lps < self.q_lps[0] - 1e-12 or q_lps > self.q_lps[-1] + 1e-12:
            raise ValueError(
                f"Q={q_lps:g} L/s is outside the curve range "
                f"[{self.q_lps[0]:g}, {self.q_lps[-1]:g}]"
            )
        values = {
            "H": self.head_m,
            "Eta1": self.efficiency,
            "NPSH": self.npshr_m,
        }.get(field)
        if values is None:
            raise KeyError(f"unknown curve field: {field}")
        result = float(np.interp(q_lps, self.q_lps, values))
        return None if math.isnan(result) else result

    def scale(self, speed_ratio: float, frequency_hz: float) -> "PumpCurve":
        """Apply the affinity laws and the Sârbu-Borza efficiency equation.

        r = n2/n1:  Q2 = Q1·r,  H2 = H1·r²,  NPSH2 = NPSH1·r²
        η2 = 1 - (1 - η1)·(n1/n2)^0.1   (Sârbu & Borza, 1998)
        """

        ratio = float(speed_ratio)
        if ratio <= 0:
            raise ValueError("speed_ratio must be positive")
        eta = self.efficiency
        transformed_eta = 1 - (1 - eta) * ratio ** -SARBU_BORZA_EXPONENT
        # Points with zero efficiency (shut-off) stay at zero; the correlation
        # is only meaningful where the pump actually delivers flow.
        transformed_eta = np.clip(np.where(eta == 0, 0.0, transformed_eta), 0.0, 1.0)
        return PumpCurve(
            frequency_hz=float(frequency_hz),
            q_lps=self.q_lps * ratio,
            head_m=self.head_m * ratio**2,
            efficiency=transformed_eta,
            npshr_m=self.npshr_m * ratio**2,
        )


@dataclass(frozen=True)
class SystemCurve:
    """Quadratic system curve including the static head.

    H(Q) = static_head + (reference_head - static_head) * (Q / reference_flow)^2
    """

    name: str
    reference_flow_lps: float
    reference_head_m: float
    static_head_m: float

    def __post_init__(self) -> None:
        if self.reference_flow_lps <= 0:
            raise ValueError("reference_flow_lps must be positive")
        if self.static_head_m < 0:
            raise ValueError("static_head_m cannot be negative")
        if self.reference_head_m < self.static_head_m:
            raise ValueError("reference_head_m cannot be below static_head_m")

    @property
    def resistance(self) -> float:
        return (self.reference_head_m - self.static_head_m) / self.reference_flow_lps**2

    def head(self, q_lps: float | Iterable[float]) -> float | np.ndarray:
        q = np.asarray(q_lps, dtype=float)
        result = self.static_head_m + self.resistance * q**2
        return float(result) if result.ndim == 0 else result

    def sample(self, q_max_lps: float | None = None, points: int = 100):
        import pandas as pd

        if points < 2:
            raise ValueError("points must be at least 2")
        maximum = q_max_lps if q_max_lps is not None else self.reference_flow_lps * 2
        q = np.linspace(0, maximum, points)
        return pd.DataFrame({"Q": q, "H": self.head(q)})


@dataclass(frozen=True)
class IntersectionResult:
    pump_id: str
    system_name: str
    frequency_hz: float
    q_lps: float | None
    head_m: float | None
    efficiency: float | None
    npshr_m: float | None
    found: bool
    intersection_count: int = 0
    note: str = ""


@dataclass(frozen=True)
class NPSHResult:
    required_m: float | None
    atmospheric_m: float
    suction_head_m: float
    suction_loss_m: float
    vapor_pressure_head_m: float

    @property
    def available_m(self) -> float:
        return (
            self.atmospheric_m
            + self.suction_head_m
            - self.suction_loss_m
            - self.vapor_pressure_head_m
        )

    @property
    def absolute_margin_m(self) -> float | None:
        return None if self.required_m is None else self.available_m - self.required_m

    @property
    def available_to_required_ratio(self) -> float | None:
        if self.required_m is None:
            return None
        return math.inf if self.required_m == 0 else self.available_m / self.required_m

    def status(self, min_absolute_m: float = 0.6, min_ratio: float = 1.25) -> str:
        if self.required_m is None:
            return "not_available"
        if self.absolute_margin_m >= min_absolute_m and self.available_to_required_ratio >= min_ratio:
            return "approved"
        return "rejected"


@dataclass(frozen=True)
class OperatingPoint:
    name: str
    frequency_hz: float
    speed_rpm: float
    synchronous_speed_rpm: float
    slip: float
    q_lps: float
    head_m: float
    hydraulic_efficiency: float
    shaft_power_kw: float
    motor_margin: float
    electrical_power_kw: float
    npsh: NPSHResult


class Pump:
    """One unique pump with cached curves keyed by frequency."""

    def __init__(self, metadata: PumpMetadata, base_curve: PumpCurve):
        if not math.isclose(
            metadata.base_frequency_hz, base_curve.frequency_hz, rel_tol=0, abs_tol=1e-9
        ):
            raise ValueError("base curve frequency must match metadata baseFreq")
        self.metadata = metadata
        self.ID = metadata.pump_id
        self._base_key = self._frequency_key(metadata.base_frequency_hz)
        self._curves: dict[float, PumpCurve] = {self._base_key: base_curve}
        self.operations: dict[str, OperatingPoint] = {}

    @staticmethod
    def _frequency_key(frequency_hz: float) -> float:
        frequency = float(frequency_hz)
        if frequency <= 0:
            raise ValueError("frequency must be positive")
        return round(frequency, FREQUENCY_KEY_DIGITS)

    @property
    def curves(self) -> Mapping[float, PumpCurve]:
        return MappingProxyType(self._curves)

    @property
    def base_curve(self) -> PumpCurve:
        return self._curves[self._base_key]


    def speed_ratio_for_frequency(self, frequency_hz: float) -> float:
        """Speed ratio n/n_base for a supply frequency, with variable motor slip."""

        y = float(frequency_hz) / self.metadata.base_frequency_hz
        slip = self.metadata.base_slip
        denominator = 1 - slip + y * slip
        if denominator <= 0:
            raise ValueError("frequency produces an invalid speed ratio")
        return y / denominator

    def frequency_for_speed_ratio(self, speed_ratio: float) -> float:
        ratio = float(speed_ratio)
        if ratio <= 0:
            raise ValueError("speed_ratio must be positive")
        slip = self.metadata.base_slip
        denominator = 1 - slip * ratio
        if denominator <= 0:
            raise ValueError("speed ratio produces invalid synchronous speed")
        synchronous = self.metadata.base_speed_rpm * ratio / denominator
        return synchronous * self.metadata.poles / 120

    def curve_at(self, frequency_hz: float, create: bool = True) -> PumpCurve:
        key = self._frequency_key(frequency_hz)
        if key in self._curves:
            return self._curves[key]
        if not create:
            raise KeyError(f"curve at {frequency_hz:g} Hz is not cached")
        ratio = self.speed_ratio_for_frequency(frequency_hz)
        curve = self.base_curve.scale(ratio, float(frequency_hz))
        self._curves[key] = curve
        return curve

    def remove_curve(self, frequency_hz: float) -> None:
        key = self._frequency_key(frequency_hz)
        if key == self._base_key:
            raise ValueError("the baseFreq curve cannot be deleted")
        if key not in self._curves:
            raise KeyError(f"curve at {frequency_hz:g} Hz is not cached")
        del self._curves[key]

    @staticmethod
    def _curve_intersections(curve: PumpCurve, system: SystemCurve) -> list[float]:
        roots: list[float] = []
        k = system.resistance
        for index in range(len(curve.q_lps) - 1):
            q1, q2 = curve.q_lps[index : index + 2]
            h1, h2 = curve.head_m[index : index + 2]
            slope = (h2 - h1) / (q2 - q1)
            intercept = h1 - slope * q1
            coefficients = [k, -slope, system.static_head_m - intercept]
            if abs(coefficients[0]) < 1e-14:
                coefficients = coefficients[1:]
            if len(coefficients) == 2 and abs(coefficients[0]) < 1e-14:
                continue
            for candidate in np.roots(coefficients):
                if abs(candidate.imag) > 1e-8:
                    continue
                q_value = float(candidate.real)
                if q1 - 1e-9 <= q_value <= q2 + 1e-9:
                    roots.append(q_value)
        return sorted({round(value, 10) for value in roots})

    def intersect(
        self, system: SystemCurve, frequency_hz: float | None = None
    ) -> IntersectionResult:
        frequency = self.metadata.base_frequency_hz if frequency_hz is None else float(frequency_hz)
        curve = self.curve_at(frequency)
        roots = self._curve_intersections(curve, system)
        if not roots:
            return IntersectionResult(
                pump_id=self.ID,
                system_name=system.name,
                frequency_hz=frequency,
                q_lps=None,
                head_m=None,
                efficiency=None,
                npshr_m=None,
                found=False,
                note="no intersection within the pump curve range",
            )
        q_value = roots[0]
        note = ""
        if len(roots) > 1:
            note = f"{len(roots)} intersections found; the lowest-flow point was returned"
        return IntersectionResult(
            pump_id=self.ID,
            system_name=system.name,
            frequency_hz=frequency,
            q_lps=q_value,
            head_m=float(system.head(q_value)),
            efficiency=curve.interpolate(q_value, "Eta1"),
            npshr_m=curve.interpolate(q_value, "NPSH"),
            found=True,
            intersection_count=len(roots),
            note=note,
        )

    def required_speed_ratio(self, q_lps: float, head_m: float) -> float:
        """Return the affinity ratio needed to pass through a requested duty.

        The local system segment is intentionally linearised on the base-curve
        Q grid.  This reproduces the established MK3 ``getRot`` results.  The
        public :meth:`intersect` method uses the exact quadratic solution.
        """

        virtual_system = SystemCurve(
            name="required-duty",
            reference_flow_lps=float(q_lps),
            reference_head_m=float(head_m),
            static_head_m=0.0,
        )
        curve = self.base_curve
        system_head = np.asarray(virtual_system.head(curve.q_lps), dtype=float)
        delta = system_head - curve.head_m
        flips = np.where(np.diff(np.sign(delta)) != 0)[0]
        if len(flips) == 0:
            raise ValueError("the requested duty cannot be reached from the base curve")
        index = int(flips[0])
        q1, q2 = curve.q_lps[index : index + 2]
        pump_h1, pump_h2 = curve.head_m[index : index + 2]
        sys_h1, sys_h2 = system_head[index : index + 2]
        pump_slope = (pump_h2 - pump_h1) / (q2 - q1)
        pump_intercept = pump_h1 - pump_slope * q1
        system_slope = (sys_h2 - sys_h1) / (q2 - q1)
        system_intercept = sys_h1 - system_slope * q1
        denominator = pump_slope - system_slope
        if abs(denominator) < 1e-14:
            raise ValueError("the requested duty is tangent to the base curve")
        base_q = (system_intercept - pump_intercept) / denominator
        if base_q <= 0:
            raise ValueError("the requested duty produces an invalid speed ratio")
        return float(q_lps) / base_q

    def set_op(
        self,
        name: str,
        altitude_m: float,
        q_lps: float | None = None,
        head_m: float | None = None,
        frequency_hz: float | None = None,
        speed_rpm: float | None = None,
        system: SystemCurve | None = None,
        suction_loss_m: float = 0.0,
        vapor_pressure_head_m: float = 0.26,
    ) -> OperatingPoint:
        if name in self.operations:
            warnings.warn(f"overwriting operating point {name!r}", UserWarning, stacklevel=2)
        if system is not None:
            if frequency_hz is None:
                raise ValueError("frequency_hz is required when setting an operation from a system curve")
            result = self.intersect(system, frequency_hz)
            if not result.found:
                raise ValueError(result.note)
            q_lps, head_m = result.q_lps, result.head_m

        if q_lps is None:
            raise ValueError("q_lps is required")
        q_lps = float(q_lps)

        if head_m is not None:
            if frequency_hz is not None or speed_rpm is not None:
                warnings.warn(
                    "head_m and q_lps define the required speed; supplied speed/frequency was ignored",
                    UserWarning,
                    stacklevel=2,
                )
            ratio = self.required_speed_ratio(q_lps, float(head_m))
            frequency_hz = self.frequency_for_speed_ratio(ratio)
            speed_rpm = self.metadata.base_speed_rpm * ratio
            curve = self.curve_at(frequency_hz)
        else:
            if speed_rpm is None and frequency_hz is None:
                raise ValueError("provide head_m, speed_rpm or frequency_hz together with q_lps")
            if speed_rpm is not None:
                ratio = float(speed_rpm) / self.metadata.base_speed_rpm
                derived_frequency = self.frequency_for_speed_ratio(ratio)
                if frequency_hz is not None and not math.isclose(
                    float(frequency_hz), derived_frequency, rel_tol=1e-6, abs_tol=1e-6
                ):
                    raise ValueError("speed_rpm and frequency_hz are inconsistent")
                frequency_hz = derived_frequency
            else:
                ratio = self.speed_ratio_for_frequency(float(frequency_hz))
                speed_rpm = self.metadata.base_speed_rpm * ratio
            curve = self.curve_at(float(frequency_hz))
            head_m = curve.interpolate(q_lps, "H")

        eta = curve.interpolate(q_lps, "Eta1")
        if eta is None or eta <= 0:
            raise ValueError("hydraulic efficiency must be positive at the operating point")
        npshr = curve.interpolate(q_lps, "NPSH")
        shaft_power = 1e-3 * q_lps * 0.9978 * 9.80665 * float(head_m) / eta
        npsh = NPSHResult(
            required_m=npshr,
            atmospheric_m=atmospheric_pressure_head(altitude_m),
            suction_head_m=self.metadata.suction_head_m,
            suction_loss_m=float(suction_loss_m),
            vapor_pressure_head_m=float(vapor_pressure_head_m),
        )
        synchronous = 120 * float(frequency_hz) / self.metadata.poles
        point = OperatingPoint(
            name=name,
            frequency_hz=float(frequency_hz),
            speed_rpm=float(speed_rpm),
            synchronous_speed_rpm=synchronous,
            slip=(synchronous - float(speed_rpm)) / synchronous,
            q_lps=q_lps,
            head_m=float(head_m),
            hydraulic_efficiency=eta,
            shaft_power_kw=shaft_power,
            motor_margin=1 - shaft_power / self.metadata.motor_power_kw,
            electrical_power_kw=shaft_power / self.metadata.motor_efficiency,
            npsh=npsh,
        )
        self.operations[name] = point
        return point
