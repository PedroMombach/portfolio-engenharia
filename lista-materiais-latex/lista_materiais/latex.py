"""Geração das fontes LaTeX da emissão a partir do template."""

from __future__ import annotations

import hashlib
from pathlib import Path
import shutil

from .entrada import METADATA, REVISION_COLUMNS, InputError, text

TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "Template"
IMAGE_PRIORITY = {".pdf": 0, ".png": 1, ".jpg": 2, ".jpeg": 3}
LATEX_SPECIAL = {
    "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
    "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
    "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
    "μ": r"\ensuremath{\mu}", "µ": r"\ensuremath{\mu}",
    "\n": " ", "\r": " ",
}
PLACEHOLDER_PICTURE = (
    r"\parbox[c][38mm][c]{0.8\linewidth}{\centering"
    r"\includegraphics[width=0.7\linewidth,height=24mm,keepaspectratio]{imgs/handler.jpg}"
    r"\\ Sem figura cadastrada}"
)


def latex_escape(value) -> str:
    """Escapa caracteres especiais uma única vez."""
    return "".join(LATEX_SPECIAL.get(char, char) for char in text(value))


def tex_path(path) -> str:
    value = Path(path).resolve().as_posix()
    if any(char in value for char in "%{}\n\r"):
        raise InputError(
            f"Caminho incompatível com LaTeX (%, chaves ou quebra de linha): {path}"
        )
    return r"\detokenize{" + value + "}"


def format_quantity(quantity) -> str:
    """Decimal -> texto com vírgula e sem zeros à direita (12.500 -> 12,5)."""
    number = format(quantity, "f")
    if "." in number:
        number = number.rstrip("0").rstrip(".")
    return number.replace(".", ",")


def image_index(directory: Path) -> dict[str, Path]:
    """{código da família (minúsculo): arquivo}; PDF tem prioridade sobre PNG/JPG."""
    if not directory.is_dir():
        raise InputError(f"Pasta de figuras não encontrada: {directory}")

    def priority(path):
        return IMAGE_PRIORITY.get(path.suffix.lower(), 99), path.name.lower(), path.name

    index = {}
    for path in sorted(directory.iterdir(), key=priority):
        if path.is_file() and path.suffix.lower() in IMAGE_PRIORITY:
            index.setdefault(path.stem.casefold(), path)
    return index


def _anchor(prefix: str, value: str) -> str:
    return f"{prefix}-" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _data_lines(config) -> list[str]:
    """Comandos com os metadados da capa e o histórico de revisões."""
    lines = [
        f"\\newcommand{{\\{command}}}{{{latex_escape(config[field])}}}"
        for field, command in METADATA.items()
    ]
    lines.append(f"\\newcommand{{\\PaginaInicial}}{{{config['pagina_inicial']}}}")
    revisions = [
        " & ".join(latex_escape(revision[key]) for key in REVISION_COLUMNS) + r" \\ \hline"
        for revision in config["historico_revisoes"]
    ]
    lines.append("\\newcommand{\\HistoricoRevisoes}{\n" + "\n".join(revisions) + "\n}")
    return lines


def _family_table(family: str, rows: list[dict], images: dict, warnings: list) -> list[str]:
    """Uma ficha (ambiente myTables) por família."""
    first = rows[0]
    image = images.get(family.casefold())
    if image:
        picture = (
            r"\includegraphics[width=0.8\linewidth,height=38mm,keepaspectratio]{"
            + tex_path(image) + "}"
        )
    else:
        picture = PLACEHOLDER_PICTURE
        warnings.append(f"{family}: figura ausente; usando Template/imgs/handler.jpg.")

    lines = [
        r"\begin{myTables}",
        "{" + latex_escape(first["TITULO_FAMILIA"]) + "}",
        "{" + latex_escape(family) + "}",
        "{" + latex_escape(first["DESCR_FAMILIA"]) + "}",
        "{" + (latex_escape(first["REF_COMERCIAL"]) or "---") + "}",
        "{" + picture + "}",
        "{" + _anchor("fam", family) + "}",
    ]
    for row in rows:
        cells = (
            row["COD_ELEMENTO"],
            row["COD_CLIENTE_ELEMENTO"],
            row["DIMENSÃO CARACTERÍSTICA"],
            format_quantity(row["QUANTIDADE"]),
            row["UNIDADE"],
        )
        lines.append(" & ".join(latex_escape(cell) for cell in cells) + r" \\ \hline")
    lines.append(r"\end{myTables}")
    return lines


def generate_tex(config, materials, work: Path) -> list[str]:
    """Grava generated/data.tex e generated/mats.tex; devolve os avisos."""
    images = image_index(config["figuras"])
    warnings: list[str] = []

    tables = []
    for material, types in materials.items():
        tables.append(r"\AddSec{" + latex_escape(material) + "}{" + _anchor("mat", material) + "}")
        for families in types.values():
            for family, rows in families.items():
                tables.extend(_family_table(family, rows, images, warnings))

    generated = work / "generated"
    generated.mkdir(parents=True, exist_ok=True)
    for name, lines in (("data.tex", _data_lines(config)), ("mats.tex", tables)):
        (generated / name).write_text("\n".join(lines) + "\n", encoding="utf-8")

    log = "\n".join(warnings) + ("\n" if warnings else "")
    (work.parent / "avisos.log").write_text(log, encoding="utf-8")
    return warnings


def stage_template(work: Path) -> None:
    """Copia para a pasta de trabalho apenas as fontes TeX e as imagens do template."""
    for source in TEMPLATE_DIR.rglob("*"):
        if source.is_file() and source.suffix.lower() in {".tex", ".png", ".jpg", ".jpeg"}:
            destination = work / source.relative_to(TEMPLATE_DIR)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
