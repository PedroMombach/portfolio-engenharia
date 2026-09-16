"""Seletor de bombas — pacote de cálculo, seleção e relatório."""

from .database import PumpDatabase
from .inputs import SelectionCase, load_cases
from .models import (
    IntersectionResult,
    NPSHResult,
    OperatingPoint,
    Pump,
    PumpCurve,
    PumpMetadata,
    SystemCurve,
    atmospheric_pressure_head,
)
from .reporting import write_selection_report
from .runner import run_cases
from .selection import (
    CandidateEvaluation,
    SelectionCriteria,
    SelectionMode,
    SelectionRequest,
    SelectionResult,
    select_pumps,
)

__all__ = [
    "CandidateEvaluation",
    "IntersectionResult",
    "NPSHResult",
    "OperatingPoint",
    "Pump",
    "PumpCurve",
    "PumpDatabase",
    "PumpMetadata",
    "SelectionCase",
    "SelectionCriteria",
    "SelectionMode",
    "SelectionRequest",
    "SelectionResult",
    "SystemCurve",
    "atmospheric_pressure_head",
    "load_cases",
    "run_cases",
    "select_pumps",
    "write_selection_report",
]
