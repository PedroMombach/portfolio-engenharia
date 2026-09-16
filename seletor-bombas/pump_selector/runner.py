"""Executa os casos de uma planilha de entrada e grava um relatório por caso."""

from __future__ import annotations

from pathlib import Path
import re
import unicodedata

from .database import PumpDatabase
from .inputs import SelectionCase, load_cases
from .reporting import write_selection_report
from .selection import SelectionCriteria, SelectionMode, select_pumps


def _safe_filename(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9._-]+", "-", ascii_text).strip("-_") or "selecao"


def _pick_cases(cases: list[SelectionCase], selector: int | str | None) -> list[SelectionCase]:
    """``None`` = todos; inteiro = posição (1, 2, ...); texto = nome exato."""
    if selector is None:
        return cases
    if isinstance(selector, int):
        if not 1 <= selector <= len(cases):
            raise ValueError(f"o caso deve estar entre 1 e {len(cases)}")
        return [cases[selector - 1]]
    chosen = [case for case in cases if case.name == selector]
    if not chosen:
        raise ValueError(f"caso não encontrado: {selector}")
    return chosen


def run_cases(
    database_path: Path,
    input_path: Path,
    template_path: Path,
    output_dir: Path,
    case: int | str | None = None,
    mode: str | None = None,
    criteria: SelectionCriteria | None = None,
) -> list[Path]:
    database = PumpDatabase.from_xlsx(database_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    reports = []

    for item in _pick_cases(load_cases(input_path), case):
        selection_mode = SelectionMode(mode) if mode else item.mode
        result = select_pumps(
            database, item.request(), selection_mode,
            criteria=criteria, manual_ids=item.manual_ids,
        )
        report = write_selection_report(
            result, output_dir / f"{_safe_filename(item.name)}.xlsx", template_path
        )
        reports.append(report)

        chosen = ", ".join(evaluation.pump_id for evaluation in result.selected)
        print(f"{item.name}: {selection_mode.value} -> {chosen} -> {report.name}")
        for evaluation in result.selected:
            for warning in evaluation.warnings:
                print(f"  aviso {evaluation.pump_id}: {warning}")
    return reports
