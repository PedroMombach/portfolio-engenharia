"""Etapa 4 — tabelas: Camelot/pdfplumber -> CSV, com score de acuracia.

Vale para os documentos com rota extra F (tabela dimensional -> CSV) ou com `tabelas` no
override. Para ASME B16.5, ISO 5752, ISO 2531 e as DIN de parafuso, o CSV indexado por DN/classe
e o que alimenta folha de dados; o Markdown narrativo dessas normas quase nao serve.

Quais paginas: `tabelas.paginas` do override, se houver; senao as paginas onde o Docling achou
tabela (estrutura/<id>.json). Sem override e sem JSON, o documento aguarda a etapa 3.

Qual flavor: `tabelas.flavor` do override; o padrao e 'lattice' (tabela com fio), caindo para
'stream' nas paginas em que o lattice nao acha nada. A escolha muda o resultado — na Tabela 23
da ISO 2531 (p. 43), stream da 21x6 com acuracia 100,0 e lattice da 19x5 com 99,57 — por isso a
decisao fica no override, documento a documento.

Saida: tabelas/<id>-<n>.csv e tabelas/<id>-indice.csv (pagina, flavor, dimensoes, acuracia).
"""
import re

from nucleo import util
from nucleo.lote import Feito

VERSAO = 2  # 2: falha de rasterizacao numa pagina cai para o stream em vez de derrubar o documento

FLAVORS = ("lattice", "stream", "network", "hybrid")
PADRAO = "lattice"
RESERVA = "stream"      # usado nas paginas em que o flavor padrao nao acha tabela

COLUNAS_INDICE = ["arquivo", "pagina", "flavor", "linhas", "colunas", "acuracia", "espaco_branco"]


def _paginas_do_json(json_path):
    """Paginas com tabela, segundo o Docling."""
    import json
    if not json_path.exists():
        return None
    doc = json.loads(json_path.read_text(encoding="utf-8"))
    paginas = {p["page_no"] for t in doc.get("tables", []) for p in t.get("prov", [])}
    return sorted(paginas)


def _intervalo(texto, total):
    """'40-50' ou '43,45' -> lista de paginas."""
    paginas = []
    for parte in str(texto).split(","):
        parte = parte.strip()
        if m := re.fullmatch(r"(\d+)\s*-\s*(\d+)", parte):
            paginas.extend(range(int(m.group(1)), int(m.group(2)) + 1))
        elif parte.isdigit():
            paginas.append(int(parte))
        elif parte == "all":
            paginas.extend(range(1, total + 1))
        else:
            raise ValueError(f"paginas invalidas no override: {texto!r}")
    return sorted({p for p in paginas if 1 <= p <= max(total, 1)})


def extrair(pdf, paginas, flavor, reserva=RESERVA):
    """Devolve (achados, falhas). achados: [(pagina, flavor, df, relatorio)], um por tabela.

    Falha de uma pagina nao derruba o documento (regra 2). O `lattice` rasteriza a pagina, e o
    rasterizador do Camelot (pypdfium2) tropeca em algumas paginas — quando isso acontece, o
    Camelot tenta cair para o Ghostscript, que a pilha nao tem de proposito (licenca AGPL).
    Nessas paginas vale o `stream`, que trabalha sobre o texto e dispensa rasterizacao."""
    import camelot
    achados, falhas = [], []
    for pagina in paginas:
        erro = ""
        for tentativa in ([flavor] if flavor == reserva else [flavor, reserva]):
            try:
                tabelas = camelot.read_pdf(str(pdf), pages=str(pagina), flavor=tentativa,
                                           suppress_stdout=True)
            except Exception as e:
                erro = f"p.{pagina} {tentativa}: {type(e).__name__}: {str(e)[:80]}"
                util.LOG.debug("%s", erro)
                continue
            erro = ""
            if len(tabelas):
                achados.extend((pagina, tentativa, t.df, t.parsing_report) for t in tabelas)
                break
        if erro:
            falhas.append(erro)
    return achados, falhas


def criar_processador(cfg, threads, overrides=None):
    overrides = overrides or {}

    def processar(linha):
        id_ = linha["id"]
        ov = overrides.get(id_, {})
        opcoes = ov.get("tabelas", {})
        if "F" not in linha["rotas_extras"].split("+") and not opcoes:
            return Feito("pulado", aviso="sem rota F e sem `tabelas` no override")

        from etapas.estrutura import pdf_de_entrada
        pdf, bloqueio = pdf_de_entrada(cfg, linha)
        if bloqueio:
            return Feito("pendente", aviso=bloqueio)

        total = int(linha["paginas"] or 0)
        if opcoes.get("paginas"):
            paginas = _intervalo(opcoes["paginas"], total)
        else:
            paginas = _paginas_do_json(cfg.pasta("estrutura") / f"{id_}.json")
            if paginas is None:
                return Feito("pendente", aviso="aguarda converter (etapa 3) para saber as paginas "
                                               "com tabela, ou defina tabelas.paginas no override")
        if not paginas:
            return Feito("ok", "nenhuma pagina com tabela", "")

        flavor = opcoes.get("flavor", PADRAO)
        if flavor not in FLAVORS:
            raise ValueError(f"flavor '{flavor}' invalido (use {'/'.join(FLAVORS)})")

        destino = cfg.pasta("tabelas")
        destino.mkdir(parents=True, exist_ok=True)
        for velho in destino.glob(f"{id_}-*.csv"):
            velho.unlink()

        achados, falhas = extrair(pdf, paginas, flavor)
        indice = ["﻿" + ",".join(COLUNAS_INDICE)]
        ruins = []
        for n, (pagina, usado, df, rel) in enumerate(achados, 1):
            arquivo = f"{id_}-{n}.csv"
            df.to_csv(destino / arquivo, index=False, header=False, encoding="utf-8-sig")
            acuracia = round(float(rel.get("accuracy", 0)), 1)
            indice.append(f"{arquivo},{pagina},{usado},{df.shape[0]},{df.shape[1]},{acuracia},"
                          f"{round(float(rel.get('whitespace', 0)), 1)}")
            if acuracia < cfg.acuracia_min:
                ruins.append(f"{arquivo} (p.{pagina}, {acuracia})")
        util.gravar_atomico(destino / f"{id_}-indice.csv", "\n".join(indice) + "\n")

        linha["tabelas_extraidas"] = str(len(achados))
        resumo = (f"{len(achados)} tabelas em {len(paginas)} paginas, flavor {flavor}"
                  + (f" (+{RESERVA} onde faltou)" if flavor != RESERVA else ""))
        if not achados:
            return Feito("falhou", resumo, f"nenhuma tabela extraida em {len(paginas)} paginas "
                                           f"com tabela segundo o Docling (flavor {flavor}?)")
        avisos = []
        if ruins:
            avisos.append(f"acuracia < {cfg.acuracia_min:g}: " + ", ".join(ruins[:5])
                          + (f" (+{len(ruins) - 5})" if len(ruins) > 5 else ""))
        if falhas:
            avisos.append(f"{len(falhas)} pagina(s) sem extracao: " + "; ".join(falhas[:3]))
        return Feito("ok", resumo, " | ".join(avisos))

    return processar
