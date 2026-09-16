"""Reads the ``Cases`` worksheet of the input workbook."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .models import SystemCurve
from .selection import SelectionMode, SelectionRequest


@dataclass(frozen=True)
class SelectionCase:
    name: str
    flow_lps: float
    static_head_min_m: float
    static_head_max_m: float
    head_min_m: float
    head_max_m: float
    altitude_m: float
    temperature_c: float = 20.0
    suction_loss_m: float = 0.0
    vapor_pressure_head_m: float = 0.26
    mode: SelectionMode = SelectionMode.OPTIMIZE
    manual_ids: tuple[str, ...] = ()

    def request(self, top_n: int = 3) -> SelectionRequest:
        return SelectionRequest(
            name=self.name,
            maximum_system=SystemCurve(
                "Maximum", self.flow_lps, self.head_max_m, self.static_head_max_m
            ),
            minimum_system=SystemCurve(
                "Minimum", self.flow_lps, self.head_min_m, self.static_head_min_m
            ),
            altitude_m=self.altitude_m,
            temperature_c=self.temperature_c,
            suction_loss_m=self.suction_loss_m,
            vapor_pressure_head_m=self.vapor_pressure_head_m,
            top_n=top_n,
        )


def load_cases(path: str | Path) -> list[SelectionCase]:
    """Load the public row-oriented ``Cases`` worksheet."""

    frame = pd.read_excel(path, sheet_name="Cases")
    required = {
        "Name",
        "Q_Lps",
        "StaticHeadMin_m",
        "StaticHeadMax_m",
        "HeadMin_m",
        "HeadMax_m",
        "Altitude_m",
        "Mode",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Cases is missing columns: {sorted(missing)}")

    def optional_number(row: dict[str, object], key: str, default: float) -> float:
        value = row.get(key, default)
        return float(default if pd.isna(value) else value)

    cases = []
    for row in frame.to_dict(orient="records"):
        manual_value = row.get("ManualIDs", "")
        manual = "" if pd.isna(manual_value) else str(manual_value)
        ids = tuple(value.strip() for value in manual.split(";") if value.strip())
        cases.append(
            SelectionCase(
                name=str(row["Name"]),
                flow_lps=float(row["Q_Lps"]),
                static_head_min_m=float(row["StaticHeadMin_m"]),
                static_head_max_m=float(row["StaticHeadMax_m"]),
                head_min_m=float(row["HeadMin_m"]),
                head_max_m=float(row["HeadMax_m"]),
                altitude_m=float(row["Altitude_m"]),
                temperature_c=optional_number(row, "Temperature_C", 20.0),
                suction_loss_m=optional_number(row, "SuctionLoss_m", 0.0),
                vapor_pressure_head_m=optional_number(row, "VaporHead_m", 0.26),
                mode=SelectionMode(str(row["Mode"]).strip().lower()),
                manual_ids=ids,
            )
        )
    return cases

