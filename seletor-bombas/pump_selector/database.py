"""Database loading and validation for pump-selector workbooks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd

from .models import Pump, PumpCurve, PumpMetadata


METADATA_COLUMNS = (
    "ID",
    "manufacturer",
    "model",
    "poles",
    "baseSpeedRPM",
    "baseFreq",
    "motorEfficiency",
    "motorPowerKW",
    "minSubmergenceMM",
    "impellerAxisMM",
    "voltageV",
    "massKG",
    "Qbep",
    "Hbep",
    "Eta1bep",
    "NPSHbep",
)
CURVE_COLUMNS = ("ID", "Q", "H", "Eta1", "NPSH")


@dataclass
class PumpDatabase:
    """Validated in-memory representation of the public XLSX database."""

    metadata: pd.DataFrame
    curves: pd.DataFrame
    abacus: Mapping[str, pd.DataFrame]
    source_path: Path | None = None

    def __post_init__(self) -> None:
        self.metadata = self.metadata.copy()
        self.curves = self.curves.copy()
        self.abacus = {name: data.copy() for name, data in self.abacus.items()}
        self._validate()
        self._metadata_by_id = self.metadata.set_index("ID", drop=False)

    @classmethod
    def from_xlsx(cls, path: str | Path) -> "PumpDatabase":
        source = Path(path)
        if not source.is_file():
            raise FileNotFoundError(source)
        sheets = pd.read_excel(source, sheet_name=None)
        missing = {"Metadata", "Curves"} - set(sheets)
        if missing:
            raise ValueError(f"database workbook is missing sheets: {sorted(missing)}")
        abacus = {
            name.removeprefix("Abacus_"): frame
            for name, frame in sheets.items()
            if name.startswith("Abacus_")
        }
        return cls(sheets["Metadata"], sheets["Curves"], abacus, source)


    def _validate(self) -> None:
        missing_metadata = set(METADATA_COLUMNS) - set(self.metadata.columns)
        missing_curves = set(CURVE_COLUMNS) - set(self.curves.columns)
        if missing_metadata:
            raise ValueError(f"Metadata is missing columns: {sorted(missing_metadata)}")
        if missing_curves:
            raise ValueError(f"Curves is missing columns: {sorted(missing_curves)}")

        self.metadata = self.metadata.loc[:, METADATA_COLUMNS].copy()
        self.curves = self.curves.loc[:, CURVE_COLUMNS].copy()
        self.metadata["ID"] = self.metadata["ID"].astype(str).str.strip()
        self.curves["ID"] = self.curves["ID"].astype(str).str.strip()
        if self.metadata["ID"].duplicated().any():
            duplicate = self.metadata.loc[self.metadata["ID"].duplicated(), "ID"].iloc[0]
            raise ValueError(f"duplicate pump ID in Metadata: {duplicate}")

        metadata_ids = set(self.metadata["ID"])
        curve_ids = set(self.curves["ID"])
        if metadata_ids != curve_ids:
            raise ValueError(
                "Metadata and Curves IDs differ: "
                f"metadata_only={sorted(metadata_ids - curve_ids)}, "
                f"curves_only={sorted(curve_ids - metadata_ids)}"
            )

        numeric_metadata = [
            "poles",
            "baseSpeedRPM",
            "baseFreq",
            "motorEfficiency",
            "motorPowerKW",
            "minSubmergenceMM",
            "impellerAxisMM",
            "massKG",
            "Qbep",
            "Hbep",
            "Eta1bep",
            "NPSHbep",
        ]
        for column in numeric_metadata:
            self.metadata[column] = pd.to_numeric(self.metadata[column], errors="coerce")
        for column in ("Q", "H", "Eta1", "NPSH"):
            self.curves[column] = pd.to_numeric(self.curves[column], errors="coerce")

        required_meta = [column for column in numeric_metadata if column not in {"massKG", "NPSHbep"}]
        if self.metadata[required_meta].isna().any().any():
            column = self.metadata[required_meta].isna().any().idxmax()
            pump_id = self.metadata.loc[self.metadata[column].isna(), "ID"].iloc[0]
            raise ValueError(f"missing required metadata {column} for {pump_id}")
        if self.curves[["Q", "H", "Eta1"]].isna().any().any():
            row = self.curves[self.curves[["Q", "H", "Eta1"]].isna().any(axis=1)].iloc[0]
            raise ValueError(f"missing required curve value for {row['ID']}")

        for pump_id, frame in self.curves.groupby("ID", sort=False):
            if len(frame) < 2:
                raise ValueError(f"curve {pump_id} has fewer than two points")
            q = frame["Q"].to_numpy(float)
            if np.any(np.diff(q) <= 0):
                raise ValueError(f"curve {pump_id} must be strictly increasing in Q")
            eta = frame["Eta1"].to_numpy(float)
            if np.any((eta < 0) | (eta > 1)):
                raise ValueError(f"curve {pump_id} has efficiency outside [0, 1]")

        for manufacturer, grid in self.abacus.items():
            if grid.empty:
                raise ValueError(f"abacus for {manufacturer} is empty")
            referenced_ids = {
                str(value).strip()
                for value in grid.iloc[:, 1:].to_numpy().ravel()
                if pd.notna(value) and str(value).strip()
            }
            unknown_ids = referenced_ids - metadata_ids
            if unknown_ids:
                raise ValueError(
                    f"abacus for {manufacturer} references unknown IDs: {sorted(unknown_ids)}"
                )

    @property
    def pump_ids(self) -> list[str]:
        return self.metadata["ID"].tolist()

    @property
    def manufacturers(self) -> list[str]:
        return sorted(self.metadata["manufacturer"].astype(str).unique().tolist())

    def get_pump(self, pump_id: str) -> Pump:
        if pump_id not in self._metadata_by_id.index:
            raise KeyError(f"unknown pump ID: {pump_id}")
        row = self._metadata_by_id.loc[pump_id].to_dict()
        metadata = PumpMetadata.from_mapping(row)
        curve_frame = self.curves[self.curves["ID"] == pump_id].loc[:, ["Q", "H", "Eta1", "NPSH"]]
        curve = PumpCurve.from_dataframe(metadata.base_frequency_hz, curve_frame)
        return Pump(metadata, curve)

    def pumps(self, pump_ids: list[str] | None = None) -> list[Pump]:
        return [self.get_pump(pump_id) for pump_id in (pump_ids or self.pump_ids)]
