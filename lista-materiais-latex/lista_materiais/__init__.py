"""Lista de materiais em LaTeX: catálogo + quantidades da emissão -> PDF."""

from __future__ import annotations

from pathlib import Path
import shutil  # noqa: F401  (exposto para os testes)
import subprocess  # noqa: F401

from .compilar import compile_pdf
from .entrada import (
    CATALOG_COLUMNS,
    ITEM_COLUMNS,
    InputError,
    load_emission,
    read_sheet,
    select_materials,
    validate_catalog,
    validate_items,
)
from .latex import (
    format_quantity,
    generate_tex,
    image_index,
    latex_escape,
    stage_template,
    tex_path,
)

PROJECT_DIR = Path(__file__).resolve().parents[1]


def generate(config_path, only_tex: bool = False, output_root=None) -> dict:
    """Pipeline completo de uma emissão.

    1. lê o JSON e as planilhas;  2. seleciona os itens com quantidade;
    3. copia o template e grava o LaTeX;  4. compila (opcional).
    """
    config = load_emission(config_path)
    catalog = validate_catalog(read_sheet(config["catalogo"], "Catalogo", CATALOG_COLUMNS))
    items = validate_items(read_sheet(config["itens"], "Itens", ITEM_COLUMNS))
    materials = select_materials(catalog, items)
    image_index(config["figuras"])  # falha cedo se a pasta de figuras não existir

    destination = Path(output_root or PROJECT_DIR / "output") / config["identificador"]
    work = destination.resolve() / "work"
    stage_template(work)
    warnings = generate_tex(config, materials, work)
    passes = None if only_tex else compile_pdf(work)

    included = sum(
        len(rows)
        for types in materials.values()
        for families in types.values()
        for rows in families.values()
    )
    return {
        "output": work.parent,
        "work": work,
        "warnings": warnings,
        "passes": passes,
        "items": included,
    }


__all__ = [
    "CATALOG_COLUMNS", "InputError", "compile_pdf", "format_quantity", "generate",
    "generate_tex", "image_index", "latex_escape", "load_emission", "read_sheet",
    "select_materials", "stage_template", "tex_path", "validate_catalog", "validate_items",
]
