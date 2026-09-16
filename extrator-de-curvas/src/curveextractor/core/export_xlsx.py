"""Spreadsheet writer with sanitized, unique raw sheet names."""

import math
import re
from pathlib import Path

import xlsxwriter

from .aggregation import Table
from .storage import atomic_write


def write_xlsx(
    path: Path,
    table: Table,
    raw: list[tuple[str, Table]] | None = None,
    primary_name: str = "Tabela",
) -> None:
    def write(temporary: Path) -> None:
        with xlsxwriter.Workbook(
            temporary, {"strings_to_formulas": False, "strings_to_urls": False}
        ) as workbook:
            used: set[str] = set()
            for name, data in [(primary_name, table), *(raw or [])]:
                base = re.sub(r"[\[\]:*?/\\]", "_", name).strip("'")[:31] or "Curva"
                title, number = base, 1
                while title.casefold() in used or title.casefold() == "history":
                    suffix = f"_{number}"
                    title, number = base[: 31 - len(suffix)] + suffix, number + 1
                used.add(title.casefold())
                sheet = workbook.add_worksheet(title)
                sheet.freeze_panes(1, 0)
                sheet.write_row(0, 0, data.headers)
                for r, row in enumerate(data.values, 1):
                    for c, value in enumerate(row):
                        if not math.isnan(float(value)):
                            sheet.write_number(r, c, float(value))
                sheet.set_column(0, len(data.headers) - 1, 20)

    atomic_write(path, write)
