"""Etapa 5 — limpeza configuravel, hifenizacao, numeracao de item em heading.

estrutura/<id>.md -> limpo/<id>.md, conforme perfis/<perfil>.toml (as regras ficam la, nao aqui)
mais o `limpeza_extra` do override do documento.

Regras de remocao devem ser criadas apenas para fontes cujo uso e transformacao sejam
autorizados. Remover um aviso de direitos ou restricao de exemplar nao concede direito de
redistribuir a obra. O perfil publico padrao nao remove esses avisos.

Contrapeso: regra agressiva apaga norma em silencio. Por isso a etapa conta o que removeu, grava
em `linhas_removidas` e avisa quando passa de LIMIAR_REVISAO do documento.
"""
import re

from nucleo import config, util
from nucleo.lote import Feito

VERSAO = 4  # 2: redige o JSON da etapa 3; 3: guardas do item -> heading; 4: remove trecho no meio da linha

LIMIAR_REVISAO = 0.25   # removeu mais que isto das linhas? vai para revisao
ANCORA = re.compile(r"<!-- p\.\d+ -->")

# Numeracao de item -> heading. As guardas importam mais que o padrao: sem elas, legenda de
# formula da ASME B16.5 ("0.79 mm = minus tolerance on outside diameter...") virava titulo e o QA
# passava a cobrar uma familia de itens "0.x" inexistente.
#   - comeca em digito nao nulo (item de norma nao comeca em 0);
#   - o texto depois do numero comeca em MAIUSCULA (legenda comeca em minuscula: "mm =", "t =");
#   - linha curta e sem " = " (legenda de simbolo tem sinal de igual).
# A faixa de maiusculas exclui U+00D7 (×): "8.75 × 1.00" e linha de dimensao, nao item.
ITEM = re.compile(r"^(?:[-*]\s+)?([1-9]\d?(?:\.\d{1,3})*)\s+([A-ZÀ-ÖØ-Ý][^=]{0,199})$")


def carregar_regras(cfg, raiz_ferramenta, ov):
    perfil = ov.get("perfil") or cfg.perfil
    regras = config.carregar_perfil(raiz_ferramenta, perfil)
    regras["remover_linhas"] = list(regras["remover_linhas"]) + list(ov.get("limpeza_extra", []))
    regras["_remover"] = [re.compile(p) for p in regras["remover_linhas"]]
    regras["_trechos"] = [re.compile(p) for p in regras.get("remover_trechos", [])]
    regras["_item"] = re.compile(regras["item_para_heading"]) if regras.get("item_para_heading") else None
    return regras


def _protegida(linha):
    """Linha que nenhuma regra de formatacao deve tocar: tabela, formula/codigo, ancora, imagem."""
    t = linha.lstrip()
    return t.startswith(("|", "`", "```", "<!--", "![")) or ANCORA.search(linha) is not None


def limpar_texto(md, regras):
    """Devolve (texto_limpo, estatisticas)."""
    est = {"linhas": 0, "removidas": 0, "trechos": 0, "hifens": 0, "headings": 0}
    linhas = md.splitlines()
    est["linhas"] = len(linhas)

    mantidas = []
    for linha in linhas:
        # A ancora de pagina e rastreabilidade: nenhuma regra de remocao a alcanca.
        if not ANCORA.search(linha) and any(r.search(linha.strip()) for r in regras["_remover"]):
            est["removidas"] += 1
            continue
        # Um perfil criado pelo operador pode remover um trecho dentro da linha, mantendo
        # o resto. O perfil publico nao remove avisos de restricao de exemplar.
        for padrao in regras.get("_trechos", []):
            linha, n = padrao.subn("", linha)
            est["trechos"] += n
        mantidas.append(linha.rstrip() if linha.strip() else linha)
    texto = "\n".join(l for l in mantidas)

    if regras.get("recompor_hifenizacao"):
        # "supor-\ntar" -> "suportar"; so quando a continuacao comeca em minuscula, para nao
        # colar item de lista nem heading.
        texto, n = re.subn(r"(\w)-[ \t]*\n[ \t]*([a-zà-ÿ])", r"\1\2", texto)
        est["hifens"] = n

    saida = []
    for linha in texto.splitlines():
        if _protegida(linha) or linha.lstrip().startswith("#"):
            saida.append(linha)
            continue
        if regras.get("colapsar_espaco_duplo"):
            # texto justificado gera "O  fator  parcial"; o "  \n" do fim de linha fica.
            linha = re.sub(r"(?<=\S)[ \t]{2,}(?=\S)", " ", linha)
        if (item := regras["_item"]) and (m := ITEM.match(linha)) and item.match(linha.lstrip("-* ")):
            nivel = min(6, 1 + len(m.group(1).split(".")))
            linha = f"{'#' * nivel} {m.group(1)} {m.group(2)}"
            est["headings"] += 1
        saida.append(linha)

    texto = re.sub(r"\n{3,}", "\n\n", "\n".join(saida)).strip() + "\n"
    return texto, est


REDIGIDO = "[redigido por regra do perfil]"


def sanitizar_json(json_path, regras):
    """O Docling pode mandar cabecalhos para a camada `furniture`, fora do Markdown; o
    JSON ainda pode guardar esse texto. Se um perfil autorizado define
    redacoes, elas tambem sao aplicadas aqui. Isto nao remove dados de imagens ou PDFs e nao
    constitui anonimizacao completa. Bboxes e paginas ficam intactos; so o texto sai."""
    import json
    if not json_path.exists():
        return 0
    doc = json.loads(json_path.read_text(encoding="utf-8"))
    padroes = [re.compile(p) for p in (list(regras["remover_linhas"])
                                       + list(regras.get("remover_trechos", []))
                                       + list(regras.get("qa", {}).get("bloquear", [])))]
    n = 0
    for item in doc.get("texts", []):
        alvo = item.get("text") or item.get("orig") or ""
        if alvo and any(p.search(alvo) for p in padroes):
            for campo in ("text", "orig"):
                if item.get(campo):
                    item[campo] = REDIGIDO
            n += 1
    if n:
        util.gravar_atomico(json_path, json.dumps(doc, ensure_ascii=False, indent=2))
    return n


def criar_processador(cfg, threads, overrides=None, raiz_ferramenta=None):
    overrides = overrides or {}

    def processar(linha):
        id_ = linha["id"]
        origem = cfg.pasta("estrutura") / f"{id_}.md"
        if linha["estado_estrutura"] != "ok" or not origem.exists():
            return Feito("pendente", aviso="aguarda converter (etapa 3)")
        regras = carregar_regras(cfg, raiz_ferramenta, overrides.get(id_, {}))
        md = origem.read_text(encoding="utf-8")
        texto, est = limpar_texto(md, regras)

        destino = cfg.pasta("limpo") / f"{id_}.md"
        destino.parent.mkdir(parents=True, exist_ok=True)
        util.gravar_atomico(destino, texto)

        redigidos = sanitizar_json(origem.with_suffix(".json"), regras)

        linha["linhas_removidas"] = str(est["removidas"])
        fracao = est["removidas"] / max(est["linhas"], 1)
        resumo = (f"perfil {regras['nome']}, {est['removidas']} linhas removidas "
                  f"({fracao:.1%}), {est['trechos']} trechos removidos no meio da linha, "
                  f"{est['hifens']} hifens recompostos, "
                  f"{est['headings']} itens viraram heading, "
                  f"{redigidos} trechos redigidos no JSON")
        if not texto.strip():
            return Feito("falhou", resumo, "limpeza esvaziou o documento")
        if not ANCORA.search(texto):
            return Feito("falhou", resumo, "ancoras <!-- p.N --> sumiram na limpeza")
        aviso = (f"removeu {fracao:.1%} das linhas: confira o perfil {regras['nome']}"
                 if fracao > LIMIAR_REVISAO else "")
        return Feito("ok", resumo, aviso)

    return processar
