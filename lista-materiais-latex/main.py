"""Lista de materiais em LaTeX — ponto de entrada.

Ajuste os parâmetros abaixo e execute:  python main.py
"""

from pathlib import Path
import sys

from lista_materiais import InputError, generate

ROOT = Path(__file__).resolve().parent

# --- Parâmetros ---------------------------------------------------------------
EMISSAO = ROOT / "Emissoes" / "exemplo" / "emissao.json"   # configuração da emissão
SAIDA = ROOT / "output"          # o PDF vai para SAIDA/<identificador>/main.pdf
SOMENTE_TEX = False              # True = só gera o .tex, sem chamar o pdflatex


def main() -> int:
    try:
        result = generate(EMISSAO, only_tex=SOMENTE_TEX, output_root=SAIDA)
    except (InputError, OSError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1

    for warning in result["warnings"]:
        print(f"Aviso: {warning}", file=sys.stderr)
    if SOMENTE_TEX:
        print(f"LaTeX gerado: {result['work'] / 'main.tex'}")
    else:
        print(f"PDF gerado: {result['output'] / 'main.pdf'} ({result['passes']} passagens)")
    print(f"Elementos incluídos: {result['items']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
