"""Utilitarios compartilhados: sha256, slug, log, subprocesso com timeout, paralelismo."""
import hashlib
import logging
import os
import re
import subprocess
import sys
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import NamedTuple

LOG = logging.getLogger("doc2md")


def configurar_log(verboso=False):
    """Log no stderr; o stdout fica livre para o resultado dos comandos (tabelas, relatorios)."""
    for s in (sys.stdout, sys.stderr):
        # Console do Windows em cp1252/cp850 nao pode derrubar o lote por causa de um acento.
        if hasattr(s, "reconfigure"):
            s.reconfigure(errors="replace")
    h = logging.StreamHandler(sys.stderr)
    h.setFormatter(logging.Formatter("%(levelname)-7s %(message)s"))
    LOG.handlers[:] = [h]
    LOG.setLevel(logging.DEBUG if verboso else logging.INFO)


def log_em_arquivo(caminho):
    """Acrescenta um log com data/hora no diretorio de saida (rastreabilidade entre execucoes)."""
    h = logging.FileHandler(caminho, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s"))
    h.setLevel(logging.DEBUG)
    LOG.addHandler(h)


def sha256(caminho, bloco=1 << 20):
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        while b := f.read(bloco):
            h.update(b)
    return h.hexdigest()


def slug(texto):
    """Id estavel a partir do nome do arquivo: sem acento, sem espaco, preserva caixa e pontos
    internos (ASME-B16.5). Pontos e hifens nas pontas caem ('...grande-porte.' -> '...grande-porte')."""
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    t = re.sub(r"[^A-Za-z0-9.]+", "-", t)
    t = re.sub(r"-{2,}", "-", t)
    t = re.sub(r"\.{2,}", ".", t)
    return t.strip("-.")


class Resultado(NamedTuple):
    rc: int
    saida: str
    erro: str


class ErroExecucao(Exception):
    pass


def _decodificar(b):
    # poppler escreve UTF-8 (-enc UTF-8); decodificar pela pagina de codigo do Windows gera
    # UnicodeDecodeError e diagnosticos incorretos na triagem.
    return b.decode("utf-8", errors="replace") if b else ""


def executar(args, timeout=300, cwd=None):
    """Roda um executavel externo. Falha de execucao vira ErroExecucao com motivo legivel;
    codigo de retorno != 0 NAO levanta: quem chama decide o que e erro."""
    args = [str(a) for a in args]
    try:
        p = subprocess.run(args, capture_output=True, timeout=timeout, cwd=cwd)
    except FileNotFoundError:
        raise ErroExecucao(f"executavel nao encontrado: {args[0]} (rode `python main.py doutor`)")
    except subprocess.TimeoutExpired:
        raise ErroExecucao(f"{Path(args[0]).stem} excedeu {timeout}s")
    return Resultado(p.returncode, _decodificar(p.stdout), _decodificar(p.stderr))


def nucleos_padrao():
    return max(1, (os.cpu_count() or 2) - 1)


def em_paralelo(funcao, itens, jobs):
    """Aplica `funcao` a cada item e devolve (item, resultado, excecao) a medida que terminam.
    Excecao de um item nao interrompe os demais (regra 2: falha de um documento nao derruba o lote).
    Threads bastam: o trabalho pesado esta em subprocessos e em hashlib, que liberam o GIL."""
    itens = list(itens)
    if jobs <= 1 or len(itens) <= 1:
        for it in itens:
            try:
                yield it, funcao(it), None
            except Exception as e:
                yield it, None, e
        return
    ex = ThreadPoolExecutor(max_workers=jobs)
    try:
        futuros = {ex.submit(funcao, it): it for it in itens}
        for f in as_completed(futuros):
            try:
                yield futuros[f], f.result(), None
            except Exception as e:
                yield futuros[f], None, e
    finally:
        ex.shutdown(wait=True, cancel_futures=True)


def gravar_atomico(caminho, texto, encoding="utf-8", tentativas=10):
    """Grava via arquivo temporario + os.replace: um Ctrl+C no meio nao corrompe o manifesto.
    No Windows, OneDrive (sincronizando) e Excel (arquivo aberto) seguram o destino por instantes:
    tenta de novo com espera crescente (~10 s no total) antes de desistir."""
    caminho = Path(caminho)
    tmp = caminho.with_name(caminho.name + ".tmp")
    with open(tmp, "w", encoding=encoding, newline="") as f:
        f.write(texto)
    for k in range(tentativas):
        try:
            os.replace(tmp, caminho)
            return
        except PermissionError:
            if k == tentativas - 1:
                raise PermissionError(f"{caminho} bloqueado por outro programa (aberto no Excel?); "
                                      f"o conteudo novo ficou em {tmp.name}")
            time.sleep(min(0.1 * 2 ** k, 2.0))


def dentro_de(filho, pai):
    try:
        return Path(filho).resolve().is_relative_to(Path(pai).resolve())
    except OSError:
        return False
