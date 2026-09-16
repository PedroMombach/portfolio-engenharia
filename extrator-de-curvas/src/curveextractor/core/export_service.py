"""Prepare export tables and write requested formats without GUI state."""

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .aggregation import Table, aggregate
from .errors import DomainError
from .export_csv import write_csv
from .export_profiles import profiles
from .export_xlsx import write_xlsx
from .interpolation import interpolate
from .model import Curve
from .storage import slug
from .transform import Transform


@dataclass
class ExportOptions:
    path: Path
    main_id: str | None
    method: str = "linear"
    count: int | None = None
    profile: str = "Padrão"
    format: str = "CSV"
    delimiter: str = ","
    decimal: str = "."
    bom: bool = True
    include_raw: bool = False
    raw_only: bool = False
    x_label: str = "X"
    mapping: dict[str, str | None] = field(default_factory=dict)


def prepare(
    curves: list[Curve], options: ExportOptions
) -> tuple[Table | None, list[tuple[str, Table]]]:
    if not curves:
        raise DomainError("main_curve")
    raw = [
        (
            c.name,
            Table(
                ["px", "py", "X", "Y"],
                np.column_stack(
                    [
                        np.asarray(c.points_px).reshape(-1, 2),
                        Transform(c.coordinate_system).to_real(c.points_px),
                    ]
                ),
            ),
        )
        for c in curves
    ]
    if options.raw_only:
        return None, raw
    profile = next((p for p in profiles() if p.name == options.profile), None)
    if profile is None:
        raise DomainError("profile_columns")
    if profile.headers:
        main = next((c for c in curves if c.id == options.main_id), None)
        if main is None:
            raise DomainError("main_curve")
        base = aggregate([main], main.id, options.method, options.count)
        x = base.values[:, 0]
        columns = [x]
        for header in profile.headers[1:]:
            curve_id = options.mapping.get(header)
            curve = next((c for c in curves if c.id == curve_id), None)
            if curve_id and curve is None:
                raise DomainError("profile_columns")
            columns.append(
                interpolate(curve, x, options.method) if curve else np.full(len(x), np.nan)
            )
        table = Table(list(profile.headers), np.column_stack(columns))
    else:
        table = aggregate(curves, options.main_id, options.method, options.count, options.x_label)
    return table, raw


def export(curves: list[Curve], options: ExportOptions) -> tuple[list[Path], Table | None]:
    table, raw = prepare(curves, options)
    profile = next((p for p in profiles() if p.name == options.profile), None)
    if profile is None:
        raise DomainError("profile_columns")
    files: list[Path] = []
    if options.format in {"CSV", "both"}:
        if table is not None:
            path = options.path.with_suffix(".csv")
            write_csv(path, table, options.delimiter, options.decimal, options.bom, profile)
            files.append(path)
        if options.include_raw or options.raw_only:
            for curve, (_, data) in zip(curves, raw):
                path = (
                    options.path.parent
                    / f"{options.path.stem}_{slug(curve.name)}_{curve.id[:8]}_raw.csv"
                )
                write_csv(
                    path,
                    data,
                    profile.delimiter or options.delimiter,
                    profile.decimal or options.decimal,
                    options.bom if profile.bom is None else profile.bom,
                )
                files.append(path)
    if options.format in {"XLSX", "both"}:
        path = options.path.with_suffix(".xlsx")
        if table is None:
            write_xlsx(path, raw[0][1], raw[1:], raw[0][0])
        else:
            write_xlsx(path, table, raw if options.include_raw else [])
        files.append(path)
    return files, table


def planned_paths(curves: list[Curve], options: ExportOptions) -> list[Path]:
    if not options.path.name or options.path.name in {".", ".."}:
        raise DomainError("destination")
    if options.format not in {"CSV", "XLSX", "both"}:
        raise DomainError("format")
    paths = []
    if options.format in {"CSV", "both"}:
        if not options.raw_only:
            paths.append(options.path.with_suffix(".csv"))
        if options.include_raw or options.raw_only:
            paths.extend(
                options.path.parent / f"{options.path.stem}_{slug(c.name)}_{c.id[:8]}_raw.csv"
                for c in curves
            )
    if options.format in {"XLSX", "both"}:
        paths.append(options.path.with_suffix(".xlsx"))
    return paths
