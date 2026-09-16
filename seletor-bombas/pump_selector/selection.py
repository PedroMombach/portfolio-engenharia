"""Manual, abacus and optimization-based pump selection."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable
import math

import pandas as pd

from .database import PumpDatabase
from .models import OperatingPoint, Pump, SystemCurve


class SelectionMode(str, Enum):
    MANUAL = "manual"
    ABACUS = "abacus"
    OPTIMIZE = "optimize"


@dataclass(frozen=True)
class SelectionCriteria:
    min_frequency_hz: float = 30.0
    max_frequency_hz: float = 60.0
    min_motor_margin: float = 0.05
    min_npsh_absolute_margin_m: float = 0.6
    min_npsh_ratio: float = 1.25
    missing_npsh_policy: str = "allow_with_warning"
    min_bep_flow_ratio: float | None = None
    max_bep_flow_ratio: float | None = None

    def __post_init__(self) -> None:
        if self.min_frequency_hz <= 0 or self.max_frequency_hz < self.min_frequency_hz:
            raise ValueError("invalid frequency range")
        if self.missing_npsh_policy not in {"allow_with_warning", "reject"}:
            raise ValueError("missing_npsh_policy must be 'allow_with_warning' or 'reject'")


@dataclass(frozen=True)
class SelectionRequest:
    name: str
    maximum_system: SystemCurve
    minimum_system: SystemCurve
    altitude_m: float
    temperature_c: float = 20.0
    suction_loss_m: float = 0.0
    vapor_pressure_head_m: float = 0.26
    top_n: int = 3

    def __post_init__(self) -> None:
        if self.top_n <= 0:
            raise ValueError("top_n must be positive")


@dataclass
class CandidateEvaluation:
    pump: Pump
    maximum_operation: OperatingPoint | None
    feasible: bool
    score: float
    rejection_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    bep_flow_ratio: float | None = None

    @property
    def pump_id(self) -> str:
        return self.pump.ID


@dataclass
class SelectionResult:
    mode: SelectionMode
    request: SelectionRequest
    candidates: list[CandidateEvaluation]
    selected: list[CandidateEvaluation]


def evaluate_pump(
    pump: Pump, request: SelectionRequest, criteria: SelectionCriteria
) -> CandidateEvaluation:
    rejections: list[str] = []
    notices: list[str] = []
    try:
        operation = pump.set_op(
            name="Maximum",
            altitude_m=request.altitude_m,
            q_lps=request.maximum_system.reference_flow_lps,
            head_m=request.maximum_system.reference_head_m,
            suction_loss_m=request.suction_loss_m,
            vapor_pressure_head_m=request.vapor_pressure_head_m,
        )
    except (ValueError, ZeroDivisionError) as exc:
        return CandidateEvaluation(
            pump=pump,
            maximum_operation=None,
            feasible=False,
            score=math.inf,
            rejection_reasons=[str(exc)],
        )

    if operation.frequency_hz < criteria.min_frequency_hz:
        rejections.append(
            f"frequency {operation.frequency_hz:.2f} Hz is below {criteria.min_frequency_hz:.2f} Hz"
        )
    if operation.frequency_hz > criteria.max_frequency_hz:
        rejections.append(
            f"frequency {operation.frequency_hz:.2f} Hz exceeds {criteria.max_frequency_hz:.2f} Hz"
        )
    if operation.motor_margin < criteria.min_motor_margin:
        rejections.append(
            f"motor margin {operation.motor_margin:.1%} is below {criteria.min_motor_margin:.1%}"
        )

    npsh_status = operation.npsh.status(
        criteria.min_npsh_absolute_margin_m, criteria.min_npsh_ratio
    )
    if npsh_status == "rejected":
        rejections.append(
            "NPSH margins do not meet the configured absolute and relative limits"
        )
    elif npsh_status == "not_available":
        if criteria.missing_npsh_policy == "reject":
            rejections.append("manufacturer did not provide NPSHr")
        else:
            notices.append("manufacturer did not provide NPSHr; cavitation was not verified")

    speed_ratio = operation.speed_rpm / pump.metadata.base_speed_rpm
    operating_bep_flow = pump.metadata.q_bep_lps * speed_ratio
    bep_ratio = operation.q_lps / operating_bep_flow
    if criteria.min_bep_flow_ratio is not None and bep_ratio < criteria.min_bep_flow_ratio:
        rejections.append(
            f"flow/BEP ratio {bep_ratio:.3f} is below {criteria.min_bep_flow_ratio:.3f}"
        )
    if criteria.max_bep_flow_ratio is not None and bep_ratio > criteria.max_bep_flow_ratio:
        rejections.append(
            f"flow/BEP ratio {bep_ratio:.3f} exceeds {criteria.max_bep_flow_ratio:.3f}"
        )

    # Electrical power is the primary objective.  The small BEP-distance term
    # provides a deterministic preference without changing the physical unit.
    score = operation.electrical_power_kw * (1 + 0.02 * abs(bep_ratio - 1))
    return CandidateEvaluation(
        pump=pump,
        maximum_operation=operation,
        feasible=not rejections,
        score=score,
        rejection_reasons=rejections,
        warnings=notices,
        bep_flow_ratio=bep_ratio,
    )


def _nearest_abacus_value(grid: pd.DataFrame, q_lps: float, head_m: float) -> str:
    if grid.shape[1] < 2:
        raise ValueError("abacus must contain a head column and at least one flow column")
    head_column = grid.columns[0]
    heads = pd.to_numeric(grid[head_column], errors="coerce")
    flow_columns = []
    for column in grid.columns[1:]:
        try:
            flow_columns.append((column, float(column)))
        except (TypeError, ValueError):
            continue
    if not flow_columns or heads.isna().all():
        raise ValueError("abacus axes must be numeric")

    row_order = sorted(
        (index for index in grid.index if not math.isnan(float(heads.loc[index]))),
        key=lambda index: abs(float(heads.loc[index]) - head_m),
    )
    column_order = sorted(flow_columns, key=lambda item: abs(item[1] - q_lps))
    for row_index in row_order:
        for column, _ in column_order:
            value = grid.loc[row_index, column]
            if pd.notna(value) and str(value).strip():
                return str(value).strip()
    raise ValueError("abacus has no pump ID")


def _abacus_ids(database: PumpDatabase, request: SelectionRequest) -> list[str]:
    if not database.abacus:
        raise ValueError("database does not contain synthetic abacus sheets")
    ids = []
    for manufacturer in sorted(database.abacus):
        ids.append(
            _nearest_abacus_value(
                database.abacus[manufacturer],
                request.maximum_system.reference_flow_lps,
                request.maximum_system.reference_head_m,
            )
        )
    return ids


def select_pumps(
    database: PumpDatabase,
    request: SelectionRequest,
    mode: SelectionMode | str,
    criteria: SelectionCriteria | None = None,
    manual_ids: Iterable[str] | None = None,
) -> SelectionResult:
    """Select unique pump IDs without grouping them into model families."""

    mode = SelectionMode(mode)
    criteria = criteria or SelectionCriteria()
    if mode is SelectionMode.MANUAL:
        ids = list(manual_ids or [])
        if not ids:
            raise ValueError("manual mode requires at least one exact pump ID")
    elif mode is SelectionMode.ABACUS:
        ids = _abacus_ids(database, request)
    else:
        ids = database.pump_ids

    if len(ids) != len(set(ids)):
        raise ValueError("selection input contains duplicate pump IDs")
    evaluations = [evaluate_pump(database.get_pump(pump_id), request, criteria) for pump_id in ids]
    ranked = sorted(evaluations, key=lambda item: (not item.feasible, item.score, item.pump_id))
    if mode is SelectionMode.MANUAL:
        selected = evaluations[: request.top_n]
    else:
        selected = [item for item in ranked if item.feasible][: request.top_n]
    return SelectionResult(mode=mode, request=request, candidates=ranked, selected=selected)
