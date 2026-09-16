"""Etapa 0 — higiene: varredura da entrada, integridade (qpdf --check) e nome de arquivo.

O sha256 e calculado aqui mas gravado pelo `inventariar`, que o compara com o manifesto.
"""
import importlib.util
import os
import re
from collections import defaultdict
from pathlib import Path

from nucleo import ambiente, util

VERSAO = 1

PARCIAIS = (".crdownload", ".part", ".partial", ".download", ".tmp")

# {EMISSOR}-{CODIGO}-{ANO}-{slug}[-{QUALIFICADOR}] — padrao mnemonico do acervo.
PADRAO_NOME = re.compile(r"^[A-Z]+-([A-Za-z0-9.-]+-)?(19|20)\d{2}-[A-Za-z0-9][A-Za-z0-9.-]*$")


def varrer(entrada, extensoes):
    """Devolve (documentos, ignorados). Pastas iniciadas por '_' (ex.: _descartar) ficam de fora."""
    docs, ignorados = [], defaultdict(list)
    for dp, dirs, fns in os.walk(entrada):
        dirs[:] = sorted(d for d in dirs if not d.startswith(("_", ".")))
        for fn in sorted(fns):
            ext = Path(fn).suffix.lower()
            if ext in extensoes:
                docs.append(Path(dp) / fn)
            else:
                ignorados[ext or "(sem extensao)"].append(fn)
    return docs, dict(ignorados)


def verificador():
    """Ha como conferir integridade neste ambiente? (qpdf ou pikepdf)"""
    return bool(ambiente.localizar("qpdf") or importlib.util.find_spec("pikepdf"))


def integridade(caminho, timeout):
    """'ok' | 'avisos: ...' | 'erro: ...' | 'nao_verificado'. Nunca levanta."""
    qpdf = ambiente.localizar("qpdf")
    if qpdf:
        try:
            r = util.executar([qpdf, "--check", caminho], timeout=timeout)
        except util.ErroExecucao as e:
            return f"erro: {e}"
        msg = next((l.strip() for l in (r.erro + "\n" + r.saida).splitlines()
                    if l.strip() and ("error" in l.lower() or "warning" in l.lower())), "")
        # "WARNING: C:\...\arquivo.pdf (object 12 0): msg" -> "WARNING: (object 12 0): msg"
        msg = re.sub(re.escape(str(caminho)) + r":?\s*", "", msg)
        n = sum(1 for l in (r.erro + r.saida).splitlines() if "warning" in l.lower())
        if n > 1:
            msg = f"{msg} (+{n - 1} avisos)"
        if r.rc == 0:
            return "ok"
        if r.rc == 3:  # qpdf: 3 = so avisos
            return f"avisos: {msg[:120]}"
        return f"erro: {msg[:120] or f'qpdf rc={r.rc}'}"
    if importlib.util.find_spec("pikepdf"):
        import pikepdf
        try:
            with pikepdf.open(caminho) as pdf:
                len(pdf.pages)
            return "ok"
        except Exception as e:
            return f"erro: {str(e)[:120]}"
    return "nao_verificado"


def avisos_nome(caminho):
    """Problemas de nome que o `renomear` deveria corrigir."""
    stem = caminho.stem
    avisos = []
    if util.slug(stem) != stem:
        avisos.append(f"nome '{caminho.name}' normalizado para o id '{util.slug(stem)}'")
    elif not PADRAO_NOME.match(stem):
        avisos.append("nome fora do padrao EMISSOR-CODIGO-ANO-slug")
    return avisos
