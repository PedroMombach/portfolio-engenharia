"""Declarative output contracts."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ExportProfile:
    name: str
    delimiter: str | None = None
    decimal: str | None = None
    bom: bool | None = None
    headers: tuple[str, ...] | None = None
    newline: str = "\n"


def profiles() -> tuple[ExportProfile, ...]:
    return (
        ExportProfile("Padrão"),
        ExportProfile("SeletorBombasMK3", ",", ".", False, ("Q", "H", "Eta1", "NPSH"), "\r\n"),
    )
