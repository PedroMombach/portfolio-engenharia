"""Etapa 6 — metadados: front-matter YAML + conferencia das ancoras de pagina.

limpo/<id>.md -> corpus/<id>.md (o Markdown final do acervo).

As ancoras <!-- p.N --> vem da etapa 3, que e quem sabe a pagina de cada bloco; aqui elas sao
conferidas. Sem elas o agente nao consegue devolver "NBR 8883:2002, item 4.9.2.8.2, p. 17", e
citacao sem pagina nao passa em revisao de ET.
"""
import re

from nucleo import util
from nucleo.lote import Feito

VERSAO = 1

ANCORA = re.compile(r"<!-- p\.(\d+) -->")
IDIOMAS = {"por": "pt-BR", "eng": "en", "deu": "de"}
QUALIFICADORES = ("PROJETO", "CANCELADA", "PT", "EN", "2ED")


def partes_do_id(id_):
    """{EMISSOR}-{CODIGO}-{ANO}-{slug}[-{QUALIF}] -> (emissor, codigo, ano)."""
    t = id_.split("-")
    emissor = t[0]
    ano, i_ano = "", None
    for i, p in enumerate(t[1:], 1):
        if re.fullmatch(r"(19|20)\d{2}", p):
            ano, i_ano = p, i
            break
    codigo = "-".join(t[1:i_ano]) if i_ano else ""
    # "NBR8883" -> "NBR 8883"; "B16.5" fica como esta (prefixo de uma letra so).
    codigo = re.sub(r"(?<=[A-Za-z]{2})(?=\d)", " ", codigo, count=1)
    return emissor, codigo, ano


def idioma_do_doc(id_, linha, ov):
    if "idioma" in ov:
        return ov["idioma"]
    t = id_.split("-")
    if "PT" in t[-2:]:
        return "pt-BR"
    if "EN" in t[-2:]:
        return "en"
    if t[0] == "ABNT":
        return "pt-BR"
    return IDIOMAS.get((linha["idioma_ocr"] or "eng").split("+")[0], "en")


def titulo_do_doc(id_, ov):
    """Titulo curado no override; senao o slug legivel — e a etapa avisa quem falta curar."""
    if ov.get("titulo"):
        return ov["titulo"], True
    _, _, ano = partes_do_id(id_)
    t = id_.split("-")
    inicio = t.index(ano) + 1 if ano in t else 1
    palavras = [p for p in t[inicio:] if p not in QUALIFICADORES]
    return " ".join(palavras).replace("_", " ") or id_, False


def front_matter(linha, ov):
    id_ = linha["id"]
    emissor, codigo, ano = partes_do_id(id_)
    titulo, curado = titulo_do_doc(id_, ov)
    dados = {
        "id": id_,
        "emissor": ov.get("emissor") or emissor,
        "codigo": ov.get("codigo") or codigo,
        "ano": int(ov["ano"]) if ov.get("ano") else (int(ano) if ano else None),
        # vigente | cancelada | projeto | traducao; nao_declarado = ninguem curou ainda
        "status": linha["status_doc"] or "nao_declarado",
        "idioma": idioma_do_doc(id_, linha, ov),
        "titulo": titulo,
        "rota": linha["rota_efetiva"],
        "origem": linha["arquivo_origem"],
        "origem_sha256": linha["sha256_origem"],
        "paginas": int(linha["paginas"] or 0),
        "confianca_ocr": linha["conf_ocr_media"] or "n/a",
    }
    return dados, curado


def criar_processador(cfg, threads, overrides=None):
    overrides = overrides or {}
    sem_titulo = []

    def processar(linha):
        import yaml
        id_ = linha["id"]
        origem = cfg.pasta("limpo") / f"{id_}.md"
        if linha["estado_limpeza"] != "ok" or not origem.exists():
            return Feito("pendente", aviso="aguarda limpar (etapa 5)")
        md = origem.read_text(encoding="utf-8")

        paginas_marcadas = sorted({int(n) for n in ANCORA.findall(md)})
        if not paginas_marcadas:
            return Feito("falhou", "", "documento sem ancora <!-- p.N -->: sem rastreabilidade "
                                       "norma -> item -> pagina")
        dados, curado = front_matter(linha, overrides.get(id_, {}))
        if not curado:
            sem_titulo.append(id_)
        cabecalho = yaml.safe_dump(dados, allow_unicode=True, sort_keys=False, default_flow_style=False)
        destino = cfg.pasta("corpus") / f"{id_}.md"
        destino.parent.mkdir(parents=True, exist_ok=True)
        util.gravar_atomico(destino, f"---\n{cabecalho}---\n\n{md.lstrip()}")

        total = int(linha["paginas"] or 0)
        cobertura = len(paginas_marcadas) / max(total, 1)
        resumo = (f"{len(paginas_marcadas)}/{total} paginas com ancora ({cobertura:.0%}), "
                  f"status {dados['status']}")
        avisos = []
        if cobertura < 0.9:
            # Pagina sem nenhum bloco de texto (prancha, figura) nao gera ancora; abaixo de 90%
            # vale conferir se nao foi perda de conteudo.
            avisos.append(f"{total - len(paginas_marcadas)} paginas sem ancora")
        if dados["status"] == "nao_declarado":
            avisos.append("status nao declarado: ponha `status` no override")
        if not curado:
            avisos.append("titulo derivado do nome do arquivo: ponha `titulo` no override")
        return Feito("ok", resumo, "; ".join(avisos))

    processar.sem_titulo = sem_titulo
    return processar
