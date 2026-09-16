"""Etapa 7 — QA: os criterios de aceitacao da conversao, documento a documento.

Le o corpus final e devolve `aprovado` | `revisar` | `reprovado` no manifesto, mais
relatorio-qa.md. Codigo de saida != 0 quando ha reprovado: e o que impede um corpus furado de
seguir para a indexacao.

Criterios (secao 8 do relatorio de conversao):
    cobertura de texto     MD >= 95 % dos caracteres do pdftotext        reprova
    confianca de OCR       media do Tesseract >= 85 %                    revisa
    numeracao de item      item da fonte ausente reprova (A/B); lacuna revisa
    tabelas                documento de rota F com CSV extraido          reprova
    limpeza                nenhum padrao bloqueado (CPF no perfil padrao) reprova
    rastreabilidade        ancora <!-- p.N --> e front-matter completo   reprova
    revisao visual         3 paginas por documento conferidas a mao      fica pendente, humano

A referencia de cobertura desconta linhas que um perfil configurado manda remover: senao
a propria limpeza derrubaria a cobertura e reprovaria o documento.
"""
import re

from nucleo import ambiente, util

VERSAO = 1

LIMIAR_COBERTURA = 0.95
LIMIAR_CONF_OCR = 85.0
CAMPOS_FRONT_MATTER = ("emissor", "ano", "status", "idioma", "titulo", "rota",
                       "origem_sha256", "paginas", "confianca_ocr")
# `codigo` fica de fora da reprova: ha documento que nao tem codigo no nome (ASCE Guidelines,
# livros). A falta vira revisao, para o override poder preencher.
CAMPOS_CURADORIA = ("codigo",)

ANCORA = re.compile(r"<!-- p\.(\d+) -->")
# Item numerado, como heading (apos a etapa 5) ou como item de lista. As mesmas guardas da
# etapa 5: numero comeca em digito nao nulo e o texto comeca em maiuscula. Linha de tabela,
# formula e legenda de simbolo ficam de fora (ver `itens_numerados`).
# A faixa de maiusculas exclui U+00D7 (×): "8.75 × 1.00", de tabela de dimensoes, nao e item.
MAIUSCULA = "A-ZÀ-ÖØ-Ý"
ITEM = re.compile(rf"^(?:#{{1,6}}\s+|[-*]\s+)?([1-9]\d?(?:\.\d{{1,3}})+)\s+([{MAIUSCULA}]\S*)")
# "4.0 TP309H", "3.6 B8T": codigo de material em tabela, nao titulo de secao.
CODIGO = re.compile(r"^[A-Z0-9./-]{2,}$")
# Linha de sumario: pontilhado de conducao, com ou sem numero de pagina no fim.
SUMARIO = re.compile(r"\.{3,}\s*\d*\s*$|\.{5,}")
# "20.6 MPa": valor com unidade no inicio da linha, nao item numerado.
UNIDADES = {"Pa", "kPa", "MPa", "GPa", "N", "kN", "MN", "Nm", "kgf", "kg", "g", "t", "mm", "cm",
            "m", "km", "in", "ft", "psi", "ksi", "bar", "Hz", "rpm", "W", "kW", "V", "A", "C",
            "K", "L", "s", "min", "h", "%"}


def itens_numerados(md):
    """Itens numerados que comecam linha, ignorando tabela, formula, codigo de material e valor
    com unidade. Serve tanto para o Markdown quanto para o texto cru do pdftotext."""
    achados = []
    for linha in md.splitlines():
        t = linha.strip()
        if t.startswith(("|", "`", "<!--", "![")) or " = " in t:
            continue
        if SUMARIO.search(t):        # "8.2.14 Ultimate limit state ....... 30": linha de sumario
            continue
        m = ITEM.match(linha)
        if not m:
            continue
        titulo = m.group(2).strip(".,;:()")
        if CODIGO.match(titulo) or titulo in UNIDADES or "/" in titulo:
            continue
        # Titulo de secao tem palavra: "2.7 M)", "13.8 Ag", "1.14 T" sao celula de tabela ou
        # fragmento de formula que o OCR deixou no comeco da linha.
        if len(re.findall(r"[^\W\d_]", t[m.end(1):])) < 4:
            continue
        achados.append(m.group(1))
    return achados


def _alfanumericos(texto):
    return len(re.findall(r"\w", texto))


def texto_do_pdf(pdf, timeout):
    r = util.executar([ambiente.exe("pdftotext"), "-q", "-enc", "UTF-8", "-eol", "unix", pdf, "-"],
                      timeout=timeout)
    return r.saida


def cobertura(texto_pdf, md, regras):
    """Fracao dos caracteres do PDF que chegou ao Markdown, descontando o que a limpeza remove:
    senao um perfil que remove linhas derrubaria a cobertura e a propria limpeza
    reprovaria o documento."""
    remover = [re.compile(p) for p in regras["remover_linhas"]]
    bloquear = [re.compile(p) for p in regras["qa"]["bloquear"]]
    referencia = [l for l in texto_pdf.splitlines()
                  if not any(p.search(l.strip()) for p in remover + bloquear)]
    total = _alfanumericos("\n".join(referencia))
    return (_alfanumericos(md) / total) if total else 0.0, total


def itens_perdidos(md, texto_pdf):
    """Itens numerados que o PDF tem e o corpus nao tem — perda de conteudo na conversao.

    E a checagem que vale como reprova: comparar o corpus com a origem, nao com a propria
    numeracao. O Docling costuma juntar itens consecutivos num mesmo paragrafo
    ('...fechamento; 4.3.8.3 Fator de seguranca...'), entao o item so conta como perdido se nao
    aparecer em lugar nenhum do texto — e nao apenas quando deixa de comecar uma linha."""
    corpo = "\n".join(l for l in md.splitlines() if not l.lstrip().startswith(("|", "`")))
    perdidos = []
    for item in dict.fromkeys(itens_numerados(texto_pdf)):
        # Basta o item aparecer como token. Exigir maiuscula logo apos o numero quebra em norma
        # que poe marcador entre os dois (a ASME B16.5 sai como "## 7.3 ð 25 Þ Facings"), e
        # exigir espaco quebra quando o numero termina a linha ("#### 4.2.1." na DIN 18800-1).
        if not re.search(rf"(?<![\d.]){re.escape(item)}(?![\d])(?:[\s.)\]:-]|$)", corpo, re.M):
            perdidos.append(item)
    return perdidos


def numeracao_faltante(md):
    """Lacunas em sequencias de item (4.1, 4.2, 4.4 -> falta 4.3).

    So considera sequencias com 3 ou mais itens sob o mesmo pai, e nunca reclama do que vem
    antes do primeiro item visto: documento pode comecar em 4.3 por recorte legitimo."""
    familias = {}
    for item in itens_numerados(md):
        partes = item.split(".")
        pai, ultimo = ".".join(partes[:-1]), partes[-1]
        if ultimo.isdigit():
            familias.setdefault(pai, set()).add(int(ultimo))
    faltantes = []
    for pai, numeros in sorted(familias.items()):
        if len(numeros) < 3:
            continue
        faltantes += [f"{pai}.{n}" for n in range(min(numeros), max(numeros)) if n not in numeros]
    return sorted(faltantes, key=lambda s: [int(p) for p in s.split(".")])


# Bloco de formula como a etapa 3 o escreve: comentario, recorte opcional e o texto do PDF.
FORMULA = re.compile(r"<!-- formula[^\n]*-->\n(!\[formula\]\([^)]+\)\n+)?`([^`\n]+)`")
LIMIAR_EMBARALHADAS = 0.20


def formulas(md):
    """(total, com recorte fiel, com ordem de leitura suspeita).

    Suspeita = o texto extraido termina em '=' ou nao tem '=': assinatura de formula cujo PDF
    entrega os simbolos fora de ordem ('2 s s 4 d F C q π =', NBR 6123)."""
    blocos = FORMULA.findall(md)
    embaralhadas = sum(1 for _, texto in blocos
                       if texto.strip().endswith("=") or "=" not in texto)
    return len(blocos), sum(1 for img, _ in blocos if img), embaralhadas


def ocorrencias_bloqueadas(texto, regras):
    achados = []
    for padrao in regras["qa"]["bloquear"]:
        if m := re.search(padrao, texto):
            achados.append(m.group(0)[:40])
    return achados


def front_matter_incompleto(md):
    import yaml
    if not md.startswith("---\n"):
        return ["sem front-matter"]
    try:
        dados = yaml.safe_load(md.split("---\n")[1]) or {}
    except Exception as e:
        return [f"front-matter ilegivel: {e}"]
    return ([c for c in CAMPOS_FRONT_MATTER if dados.get(c) in (None, "")],
            [c for c in CAMPOS_CURADORIA if dados.get(c) in (None, "")])


def avaliar(cfg, linha, regras, pdf, md, tabelas_docling=None):
    """Devolve (veredito, reprovas, revisoes, metricas)."""
    reprovas, revisoes, metricas = [], [], {}
    texto_pdf = texto_do_pdf(pdf, cfg.timeout)

    frac, total = cobertura(texto_pdf, md, regras)
    metricas["cobertura_texto"] = round(frac, 3)
    if total == 0:
        reprovas.append("pdftotext nao devolveu texto do PDF de entrada")
    elif frac < LIMIAR_COBERTURA:
        reprovas.append(f"cobertura de texto {frac:.1%} < {LIMIAR_COBERTURA:.0%}")

    # Item que o PDF tem e o corpus nao tem. Em texto nativo (rotas A e B) isso e perda de
    # conteudo e reprova. Em documento OCRizado (C, D, E) a propria numeracao vem do OCR e erra
    # ("3.3.3" virou "33.33." no ASCE 1995, com o titulo intacto ao lado): ali vale revisao, nao
    # reprova — reprovar por ruido de OCR e o QA gritando lobo.
    perdidos = itens_perdidos(md, texto_pdf)
    metricas["itens_faltantes"] = ";".join(perdidos[:20])
    if perdidos:
        aviso = (f"{len(perdidos)} item(ns) do PDF ausentes no corpus: "
                 + ", ".join(perdidos[:8]) + (" ..." if len(perdidos) > 8 else ""))
        (reprovas if linha["rota_efetiva"] in ("A", "B") else revisoes).append(aviso)
    # Lacuna na numeracao do proprio corpus: pode ser recorte legitimo da norma, entao so revisa.
    if lacunas := numeracao_faltante(md):
        if len(lacunas) > 50:
            revisoes.append(f"numeracao do corpus muito fragmentada ({len(lacunas)} lacunas): "
                            "provavel ruido de OCR na numeracao")
        else:
            revisoes.append(f"{len(lacunas)} lacuna(s) na numeracao do corpus: "
                            + ", ".join(lacunas[:8]) + (" ..." if len(lacunas) > 8 else ""))

    total_f, recortadas, embaralhadas = formulas(md)
    if total_f:
        if recortadas < total_f:
            # Sem recorte, a unica representacao da formula e um texto que pode estar fora de
            # ordem — e nao ha como o revisor saber sem abrir o PDF.
            revisoes.append(f"{total_f - recortadas} de {total_f} formulas sem recorte fiel")
        if embaralhadas / total_f > LIMIAR_EMBARALHADAS:
            revisoes.append(f"{embaralhadas} de {total_f} formulas com ordem de leitura suspeita "
                            f"({embaralhadas / total_f:.0%}): confira pelos recortes")

    if achados := ocorrencias_bloqueadas(md, regras):
        reprovas.append("texto bloqueado no corpus: " + ", ".join(repr(a) for a in achados))

    if not ANCORA.search(md):
        reprovas.append("sem ancora <!-- p.N -->")
    else:
        paginas = {int(n) for n in ANCORA.findall(md)}
        total_pag = int(linha["paginas"] or 0)
        if total_pag and len(paginas) / total_pag < 0.9:
            revisoes.append(f"{total_pag - len(paginas)} pagina(s) sem ancora")
    faltando, curadoria = front_matter_incompleto(md)
    if faltando:
        reprovas.append(f"front-matter incompleto: {', '.join(faltando)}")
    if curadoria:
        revisoes.append(f"front-matter sem {', '.join(curadoria)}: preencha no override")

    conf = linha["conf_ocr_media"]
    if linha["rota_efetiva"] in ("C", "D", "E") and conf:
        try:
            if float(conf) < LIMIAR_CONF_OCR:
                revisoes.append(f"confianca media de OCR {float(conf):.0f} < {LIMIAR_CONF_OCR:.0f}")
        except ValueError:
            pass

    if "F" in linha["rotas_extras"].split("+"):
        if linha["estado_tabelas"] != "ok" or not (linha["tabelas_extraidas"] or "0").isdigit() \
                or int(linha["tabelas_extraidas"] or 0) == 0:
            reprovas.append("rota F sem tabela extraida (etapa 4)")
        else:
            ruins = tabelas_abaixo_do_limiar(cfg, linha)
            if ruins:
                revisoes.append(f"{len(ruins)} tabela(s) com acuracia < {cfg.acuracia_min:g}: "
                                + ", ".join(ruins[:5]))
    if tabelas_docling and linha["estado_tabelas"] == "ok":
        extraidas = int(linha["tabelas_extraidas"] or 0)
        if extraidas < tabelas_docling:
            revisoes.append(f"Docling viu {tabelas_docling} tabelas, o Camelot extraiu {extraidas}")

    if linha["status_doc"] in ("", "nao_declarado"):
        revisoes.append("status do documento nao declarado no override")

    veredito = "reprovado" if reprovas else ("revisar" if revisoes else "aprovado")
    return veredito, reprovas, revisoes, metricas


def tabelas_abaixo_do_limiar(cfg, linha):
    import csv
    indice = cfg.pasta("tabelas") / f"{linha['id']}-indice.csv"
    if not indice.exists():
        return []
    ruins = []
    for r in csv.DictReader(indice.read_text(encoding="utf-8-sig").splitlines()):
        try:
            if float(r["acuracia"]) < cfg.acuracia_min:
                ruins.append(f"{r['arquivo']} (p.{r['pagina']}, {r['acuracia']})")
        except (KeyError, ValueError):
            pass
    return ruins


def relatorio(cfg, resultados, pendentes):
    """relatorio-qa.md: o que passou, o que reprovou e o que ainda depende de olho humano."""
    import datetime
    cont = {}
    for r in resultados:
        cont[r["veredito"]] = cont.get(r["veredito"], 0) + 1
    linhas = [
        "# Relatorio de QA — Doc2MD",
        "",
        f"Gerado em {datetime.datetime.now():%d/%m/%Y %H:%M}. Saida: `{cfg.saida}`.",
        "",
        f"**{len(resultados)} documento(s) avaliados** — "
        + ", ".join(f"{n} {v}" for v, n in sorted(cont.items()))
        + (f"; {len(pendentes)} ainda nao chegaram ao QA" if pendentes else ""),
        "",
        "| Documento | QA | Cobertura | Itens faltando | Tabelas |",
        "|---|---|---|---|---|",
    ]
    for r in sorted(resultados, key=lambda x: (x["veredito"] != "reprovado",
                                               x["veredito"] != "revisar", x["id"])):
        faltando = r["metricas"].get("itens_faltantes", "")
        linhas.append(f"| `{r['id']}` | {r['veredito']} | "
                      f"{r['metricas'].get('cobertura_texto', 0):.1%} | "
                      f"{len(faltando.split(';')) if faltando else 0} | {r['tabelas'] or '—'} |")
    for titulo, chave in (("Reprovados", "reprovas"), ("Para revisar", "revisoes")):
        itens = [(r["id"], m) for r in resultados for m in r[chave]]
        if itens:
            linhas += ["", f"## {titulo}", ""]
            linhas += [f"- `{i}`: {m}" for i, m in itens]
    if pendentes:
        linhas += ["", "## Ainda fora do QA", "",
                   "Documento que nao chegou ao fim do pipeline (etapa pendente ou falha):", ""]
        linhas += [f"- `{i}`: {m}" for i, m in pendentes]
    linhas += ["", "## Conferencia visual (humana)", "",
               "O criterio de revisao visual — 3 paginas por documento conferidas contra o PDF —",
               "nao e automatizavel e continua em aberto para todos os documentos acima.", ""]
    return "\n".join(linhas)
