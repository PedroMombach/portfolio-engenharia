"""CSV exports preserve numeric precision and explicit empty cells."""

import csv
import math
from pathlib import Path

from .aggregation import Table
from .errors import DomainError
from .export_profiles import ExportProfile
from .storage import atomic_write


def write_csv(
    path: Path,
    table: Table,
    delimiter: str = ",",
    decimal: str = ".",
    bom: bool = True,
    profile: ExportProfile | None = None,
) -> None:
    if profile:
        delimiter = profile.delimiter if profile.delimiter is not None else delimiter
        decimal = profile.decimal if profile.decimal is not None else decimal
        bom = profile.bom if profile.bom is not None else bom
    if len(delimiter) != 1 or decimal not in {".", ","} or delimiter == decimal:
        raise DomainError("separators")
    headers = profile.headers if profile and profile.headers else table.headers
    if len(headers) != table.values.shape[1]:
        raise DomainError("profile_columns")

    def write(temporary: Path) -> None:
        with temporary.open("w", encoding="utf-8-sig" if bom else "utf-8", newline="") as stream:
            writer = csv.writer(
                stream, delimiter=delimiter, lineterminator=profile.newline if profile else "\n"
            )
            writer.writerow(headers)
            for row in table.values:
                writer.writerow(
                    "" if math.isnan(float(v)) else str(float(v)).replace(".", decimal) for v in row
                )

    atomic_write(path, write)
