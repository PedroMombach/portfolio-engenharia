"""Etapa 1 — triagem: diagnostico de cada PDF e rota sugerida.

Calibrado no estudo de caso descrito em docs/metodologia.md. Metricas,
limiares e decisao conservam essa calibracao:
  - devolve um dicionario para o manifesto em vez de imprimir CSV;
  - poppler e lido em UTF-8 explicito (no Windows o original decodificava pela pagina de codigo
    e, no primeiro byte invalido, devolvia "" em silencio);
  - falha de pdfinfo/pdftotext levanta erro em vez de virar "0 caracteres" -> rota C falsa.

Rotas:
    A  texto nativo integro                      -> extracao direta
    B  texto nativo denso em tabelas             -> Docling + TableFormer
    C  raster sem camada de texto                -> OCRmyPDF --force-ocr
    D  camada de texto corrompida                -> OCRmyPDF --force-ocr (descarta camada)
    E  misto pagina a pagina                     -> OCRmyPDF --redo-ocr

LIMITACAO CONHECIDA: separa com seguranca texto integro de texto ILEGIVEL (mojibake). Nao separa
texto integro de OCR legado apenas RUIM -- "C6pia" e "vSlvulas" tem a mesma assinatura estatistica
de "DN50" e "Class150". Por isso existem suspeita_ocr_legado e revisar, e por isso a rota curada
do overrides.toml vence a sugerida quando a inspecao visual discorda da heuristica.
"""
import os
import re
import unicodedata

from nucleo import ambiente, util

VERSAO = 1  # mude ao alterar metricas ou limiares: invalida a triagem ja gravada

STOPWORDS = {
    "de","da","do","das","dos","que","para","com","ser","uma","nao","por","como","deve","devem",
    "the","and","for","shall","with","this","that","are","from","not","any","which","have","been",
    "der","die","und","des","den","fur","mit","ist","nach","bei",
}


class ErroTriagem(Exception):
    pass


def _run(args, timeout, obrigatorio=False, avisos=None):
    """obrigatorio: falha vira ErroTriagem. Senao, devolve "" e registra aviso."""
    nome = args[0]
    try:
        r = util.executar([ambiente.exe(nome), *args[1:]], timeout=timeout)
    except util.ErroExecucao as e:
        if obrigatorio:
            raise ErroTriagem(str(e))
        if avisos is not None:
            avisos.append(str(e))
        return ""
    if r.rc != 0:
        msg = f"{nome} rc={r.rc}: {r.erro.strip().splitlines()[0][:100] if r.erro.strip() else ''}"
        if obrigatorio:
            raise ErroTriagem(msg)
        if avisos is not None and not r.saida:
            avisos.append(msg)
    return r.saida


def diagnosticar(path, timeout=300):
    """Devolve as colunas de diagnostico do manifesto + 'avisos' (lista de texto)."""
    path = str(path)
    avisos = []
    d = {"mb": round(os.path.getsize(path) / 1e6, 2)}

    info = _run(["pdfinfo", path], timeout, obrigatorio=True)
    m = re.search(r"Pages:\s+(\d+)", info)
    d["paginas"] = int(m.group(1)) if m else 0
    if d["paginas"] == 0:
        raise ErroTriagem("pdfinfo nao retornou numero de paginas")
    d["produtor"] = (re.search(r"Producer:\s+(.*)", info).group(1).strip()[:40]
                     if re.search(r"Producer:\s+(.*)", info) else "")
    d["produtor"] = re.sub(r"[\x00-\x1f]", "", d["produtor"])
    d["cripto"] = "sim" if re.search(r"Encrypted:\s+yes", info) else "nao"
    ps = re.search(r"Page size:\s+([\d.]+) x ([\d.]+)", info)
    pw, ph = (float(ps.group(1)), float(ps.group(2))) if ps else (612.0, 792.0)

    # --- cobertura de texto, pagina a pagina ---
    # -eol unix: no Windows o poppler emite \r\n, o que altera car_por_pag e pode cruzar
    # o limiar de 2200. Os limiares foram calibrados com \n.
    txt = _run(["pdftotext", "-q", "-enc", "UTF-8", "-eol", "unix", path, "-"],
               timeout, obrigatorio=True)
    paginas = txt.split("\f")
    if paginas and not paginas[-1].strip():
        paginas = paginas[:-1]
    chars = [len(p.strip()) for p in paginas] or [0]
    n = len(chars)
    d["pag_sem_texto"] = sum(1 for c in chars if c < 80)
    d["pag_pobres"] = sum(1 for c in chars if 80 <= c < 400)
    d["frac_com_texto"] = round(1 - d["pag_sem_texto"] / n, 2)
    d["car_por_pag"] = round(sum(chars) / n)

    # --- qualidade da camada de texto (detecta mojibake e OCR legado) ---
    amostra = txt[:400000]
    ctrl = sum(1 for c in amostra
               if (ord(c) < 32 and c not in "\n\r\t\f")
               or (0xE000 <= ord(c) <= 0xF8FF)
               or unicodedata.category(c) in ("Co", "Cn"))
    d["frac_ctrl"] = round(ctrl / max(1, len(amostra)), 3)
    tokens = [w for w in re.findall(r"[A-Za-zÀ-ÿ0-9]{3,}", amostra)
              if re.search(r"[A-Za-zÀ-ÿ]", w)]
    # "sujo" = maiuscula no meio da palavra ou digito colado a letra -> assinatura de OCR ruim
    sujos = sum(1 for w in tokens
                if re.search(r"[a-zà-ÿ][A-ZÀ-Ý]|[A-Za-zÀ-ÿ]\d|\d[a-zà-ÿ]", w))
    d["frac_sujos"] = round(sujos / max(1, len(tokens)), 3)
    stop = sum(1 for w in (t.lower() for t in tokens) if w in STOPWORDS)
    d["frac_stopwords"] = round(stop / max(1, len(tokens)), 3)
    d["tokens"] = len(tokens)

    # --- pagina inteira como imagem? ---
    cobertura = 0.0
    for i in sorted({max(1, round(1 + k * (d["paginas"] - 1) / 4)) for k in range(5)}):
        for l in _run(["pdfimages", "-list", "-f", str(i), "-l", str(i), path],
                      timeout, avisos=avisos).splitlines():
            f = l.split()
            if len(f) > 13 and f[0].isdigit():
                try:
                    cov = (int(f[3]) / float(f[12]) * 72 / pw) * (int(f[4]) / float(f[13]) * 72 / ph)
                    cobertura = max(cobertura, cov)
                except (ValueError, ZeroDivisionError):
                    pass
    d["cobertura_img"] = round(cobertura, 2)

    # --- camada de OCR embutida? ---
    fontes = {l.split()[0].split("+")[-1]
              for l in _run(["pdffonts", "-f", "1", "-l", "8", path],
                            timeout, avisos=avisos).splitlines()[2:] if l.strip()}
    d["ocr_embutido"] = "sim" if any("OCR" in f.upper() or "GLYPHLESS" in f.upper()
                                     for f in fontes) else "nao"

    # --- decisao ---
    # Corrupcao inequivoca (camada de texto ilegivel): vira rota D automaticamente.
    corrompido = (d["frac_ctrl"] > 0.02
                  or d["frac_sujos"] > 0.25
                  or (d["tokens"] > 300 and d["frac_stopwords"] < 0.03))
    # OCR legado degradado (texto legivel mas cheio de erro): o script NAO decide sozinho,
    # so levanta suspeita. Este caso exige conferencia visual de 2-3 paginas.
    produtor_legado = bool(re.search(
        r"Acrobat (4|5)\.0|Acrobat Distiller (3|4|5)\.|PDFWriter|Import Plug-in|Paper Capture",
        d["produtor"], re.I))
    suspeita_ocr_legado = (d["frac_sujos"] > 0.03
                           and (d["cobertura_img"] > 0.9
                                or d["ocr_embutido"] == "sim"
                                or produtor_legado))

    if d["frac_com_texto"] < 0.10:
        d["rota_sugerida"] = "C"
    elif corrompido:
        d["rota_sugerida"] = "D"
    elif d["frac_com_texto"] < 0.90:
        d["rota_sugerida"] = "E"
    elif d["car_por_pag"] > 2200 or d["cobertura_img"] > 0.9:
        d["rota_sugerida"] = "B"
    else:
        d["rota_sugerida"] = "A"
    d["suspeita_ocr_legado"] = "sim" if suspeita_ocr_legado else "nao"

    d["revisar"] = "sim" if (d["ocr_embutido"] == "sim" or d["cobertura_img"] > 0.9
                             or suspeita_ocr_legado
                             or d["rota_sugerida"] in ("C", "D", "E")) else "nao"
    d["avisos"] = avisos
    return d


# --- decisao efetiva: override curado > heuristica ------------------------------------------

QUALIFICADORES = {"PROJETO": "projeto", "CANCELADA": "cancelada", "PT": "traducao", "EN": "traducao"}


def _tokens(id_):
    # Sensivel a caixa de proposito: o qualificador e MAIUSCULO no nome; o slug e minusculo
    # ("...-2003-projeto-estrutural-..." nao e projeto de norma).
    return id_.split("-")


def idioma_padrao(id_):
    t = _tokens(id_)
    if "PT" in t[-2:]:
        return "por"
    if "EN" in t[-2:]:
        return "eng"
    return {"ABNT": "por", "DIN": "deu+eng"}.get(t[0], "eng")


def status_padrao(id_):
    return next((QUALIFICADORES[t] for t in _tokens(id_) if t in QUALIFICADORES), "")


def decidir(id_, rota_sugerida, ov=None):
    """Colunas de decisao do manifesto. O que o humano curou no overrides.toml manda."""
    ov = ov or {}
    return {
        "rota_efetiva": ov.get("rota") or rota_sugerida,
        "rotas_extras": "+".join(ov.get("extras", [])),
        "idioma_ocr": ov.get("idioma_ocr") or idioma_padrao(id_),
        "status_doc": ov.get("status") or status_padrao(id_),
    }
