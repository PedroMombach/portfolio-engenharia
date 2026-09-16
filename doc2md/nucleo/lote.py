"""Executor comum das etapas 2-6: filtro, idempotencia, checagem da origem, falha isolada.

Uma etapa so fornece `processar(linha) -> Feito(estado, resumo, aviso)`:
    ok       concluido
    pulado   nao se aplica a este documento (ex.: OCR na rota A)
    pendente bloqueado por etapa anterior; volta a ser avaliado na proxima execucao
    falhou   saida vazia ou abaixo do limiar (regra 3)
`resumo` vai so para o log; `aviso` vai para a coluna observacao. Excecao em `processar` vira
'falhou' com o motivo na observacao, e o lote segue (regra 2).
"""
import time
from collections import Counter
from typing import NamedTuple

from . import config, util

LOG = util.LOG


class Feito(NamedTuple):
    estado: str
    resumo: str = ""
    aviso: str = ""
    # Etapas a invalidar; None = as dependentes de sempre. Serve para a etapa dizer que refez
    # menos do que o normal (reexportar o Markdown nao mexe no JSON, logo nao afeta as tabelas).
    invalida: tuple | None = None


def origem(cfg, linha):
    return cfg.entrada / linha["arquivo_origem"]


def conferir_origens(cfg, linhas, jobs):
    """O PDF mudou desde o inventario? Entao tudo que foi feito sobre ele esta velho: parar."""
    def checar(linha):
        p = origem(cfg, linha)
        return "ausente" if not p.exists() else ("" if util.sha256(p) == linha["sha256_origem"]
                                                  else "mudou")
    problemas = [(l["id"], r) for l, r, e in util.em_paralelo(checar, linhas, jobs) if r or e]
    if problemas:
        lista = ", ".join(f"{i} ({r or 'ilegivel'})" for i, r in problemas)
        raise config.ErroConfig(f"origem diferente do manifesto: {lista}. "
                                "Rode `python main.py inventariar` antes.")


def rodar(man, cfg, args, etapa, versao, processar, jobs=1):
    """Devolve (feitos, falhas). `jobs` e o paralelismo entre documentos; etapas que ja
    paralelizam por dentro (Docling) usam jobs=1."""
    if not man.linhas:
        raise config.ErroConfig(f"manifesto vazio em {man.caminho}: rode `python main.py inventariar`")
    linhas = man.filtrar(args.so_rota, args.so_doc)
    if (args.so_doc or args.so_rota) and not linhas:
        raise config.ErroConfig("nenhum documento no manifesto casa com --so-doc/--so-rota")
    conferir_origens(cfg, linhas, cfg.nucleos())
    todo = [l for l in linhas if man.precisa_rodar(l, etapa, versao, args.forcar)]
    LOG.info("%s: %d documento(s) a processar, %d ja concluidos", etapa, len(todo),
             len(linhas) - len(todo))
    if args.simular:
        for l in todo:
            print(f"  faria {etapa}: {l['id']} (rota {l['rota_efetiva']}, estado {l[f'estado_{etapa}']})")
        return 0, 0

    cont = Counter()
    t0 = time.monotonic()
    for k, (linha, res, erro) in enumerate(util.em_paralelo(processar, todo, jobs), 1):
        if erro:
            res = Feito("falhou", aviso=f"{type(erro).__name__}: {erro}"[:300])
            LOG.debug("detalhe da falha em %s", linha["id"], exc_info=erro)
        man.marcar(linha, etapa, res.estado, versao, res.aviso)
        if res.estado == "ok":
            man.invalidar_apos(linha, etapa, res.invalida)
        cont[res.estado] += 1
        nivel = LOG.error if res.estado == "falhou" else LOG.info
        nivel("[%2d/%d] %-64s %-8s %s", k, len(todo), linha["id"], res.estado,
              " | ".join(t for t in (res.resumo, res.aviso) if t))
        man.salvar_parcial()
    man.salvar()
    LOG.info("%s: %s em %.0fs", etapa,
             ", ".join(f"{n} {e}" for e, n in sorted(cont.items())) or "nada a fazer",
             time.monotonic() - t0)
    return cont["ok"], cont["falhou"]
