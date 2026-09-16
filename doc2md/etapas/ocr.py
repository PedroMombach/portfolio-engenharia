"""Etapa 2 — OCR: normaliza o PDF das rotas C, D e E com OCRmyPDF + Tesseract.

Saida: trabalho/<id>.pdf (PDF com camada de texto confiavel) e trabalho/<id>.sidecar.txt.
As etapas seguintes (estrutura, tabelas) leem esse PDF, nunca o original, quando a rota exige OCR.

Rota -> acao (veja docs/metodologia.md):
    A, B   pulado; vale o PDF original
    C      --force-ocr   (raster sem camada de texto)
    D      --force-ocr   (camada de texto corrompida: o force e o que descarta a camada podre)
    E      --redo-ocr    (misto: OCRiza so onde falta)

Sem Ghostscript de proposito: `--rasterizer pypdfium` e `--output-type pdf` tiram a unica
dependencia AGPL da pilha. PDF/A nao interessa aqui — o produto final e Markdown.
"""
import re
import sys
import tempfile
from pathlib import Path

from nucleo import ambiente, util
from nucleo.lote import Feito

VERSAO = 1

ROTAS_COM_OCR = ("C", "D", "E")
PAGINAS_AMOSTRA = 3          # paginas usadas para medir a confianca media do OCR
CARACTERES_MINIMOS = 50      # por pagina; abaixo disso o OCR nao produziu texto (regra 3)


def comando(linha, entrada, saida, sidecar, jobs, com_deskew=True, modo=None, assinatura=False):
    rota = linha["rota_efetiva"]
    idioma = linha["idioma_ocr"] or "eng"
    modo = modo or ("redo" if rota == "E" else "force")
    exe = ambiente.localizar("ocrmypdf")
    base = [exe] if exe else [sys.executable, "-m", "ocrmypdf"]
    base += ["-l", idioma, "--rasterizer", "pypdfium", "--output-type", "pdf",
             "--sidecar", str(sidecar), "--jobs", str(jobs), "--quiet"]
    if modo == "force":
        base += ["--force-ocr", "--rotate-pages", "--optimize", "1"]
    else:
        base += ["--redo-ocr"]
    if com_deskew:
        base += ["--deskew"]
    if assinatura:
        base += ["--invalidate-digital-signatures"]
    return base + [str(entrada), str(saida)]


def confianca_media(pdf, paginas, idioma, timeout):
    """Media da confianca do Tesseract numa amostra de paginas do PDF ja normalizado.

    O OCRmyPDF nao reporta confianca; aqui a amostra e rasterizada com o poppler e passada pelo
    Tesseract em modo TSV, que traz a coluna `conf` por palavra."""
    ambiente.preparar_ocr()
    tess = ambiente.localizar("tesseract")
    if not tess or paginas <= 0:
        return None
    alvos = sorted({max(1, round(1 + k * (paginas - 1) / max(PAGINAS_AMOSTRA - 1, 1)))
                    for k in range(PAGINAS_AMOSTRA)})
    confiancas = []
    with tempfile.TemporaryDirectory() as tmp:
        for pagina in alvos:
            prefixo = Path(tmp) / f"p{pagina}"
            r = util.executar([ambiente.exe("pdftoppm"), "-r", "300", "-f", str(pagina),
                               "-l", str(pagina), "-png", "-singlefile", str(pdf), str(prefixo)],
                              timeout=timeout)
            imagem = prefixo.with_suffix(".png")
            if r.rc != 0 or not imagem.exists():
                continue
            r = util.executar([tess, str(imagem), "stdout", "-l", idioma, "tsv"], timeout=timeout)
            for linha_tsv in r.saida.splitlines()[1:]:
                campos = linha_tsv.split("\t")
                if len(campos) >= 12 and campos[-1].strip():
                    try:
                        conf = float(campos[10])
                    except ValueError:
                        continue
                    if conf >= 0:
                        confiancas.append(conf)
    return round(sum(confiancas) / len(confiancas), 1) if confiancas else None


def medir_saida(pdf, timeout):
    """(caracteres por pagina, fracao de caracteres de controle) do PDF normalizado — as duas
    medidas que dizem se o OCR funcionou. Mesma conta da triagem."""
    from etapas import triagem
    diag = triagem.diagnosticar(pdf, timeout)
    return diag["car_por_pag"], diag["frac_ctrl"], diag["paginas"]


def criar_processador(cfg, threads):
    def processar(linha):
        rota = linha["rota_efetiva"]
        if rota not in ROTAS_COM_OCR:
            return Feito("pulado", aviso=f"rota {rota}: usa o PDF original")
        ambiente.preparar_ocr()
        origem = cfg.entrada / linha["arquivo_origem"]
        destino = cfg.pasta("trabalho") / f"{linha['id']}.pdf"
        sidecar = destino.with_suffix(".sidecar.txt")
        destino.parent.mkdir(parents=True, exist_ok=True)

        paginas = int(linha["paginas"] or 1)
        # OCR de documento grande passa de meia hora: o timeout por chamada da triagem nao serve.
        limite = max(cfg.timeout, 30 * paginas + 120)
        r = util.executar(comando(linha, origem, destino, sidecar, threads), timeout=limite)
        aviso = ""
        saida_erro = (r.erro or "") + (r.saida or "")
        if r.rc != 0 and "deskew" in saida_erro.lower():
            # --redo-ocr nao aceita --deskew em algumas versoes; sem deskew ainda vale a pena.
            aviso = "refeito sem --deskew (incompativel com --redo-ocr nesta versao)"
            r = util.executar(comando(linha, origem, destino, sidecar, threads, com_deskew=False),
                              timeout=limite)
            saida_erro = (r.erro or "") + (r.saida or "")
        if r.rc != 0 and ("fillable form" in saida_erro or "not currently possible" in saida_erro):
            # PDF com formulario preenchivel recusa --redo-ocr (NBR 7259). O --force-ocr resolve,
            # ao custo de rasterizar tambem as paginas que ja tinham texto nativo.
            aviso = "rota E convertida para --force-ocr: o PDF tem formulario preenchivel"
            r = util.executar(comando(linha, origem, destino, sidecar, threads, modo="force"),
                              timeout=limite)
            saida_erro = (r.erro or "") + (r.saida or "")
        if r.rc != 0 and "signature" in saida_erro.lower():
            # PDF assinado digitalmente (DIN 18800-1). A assinatura e invalidada apenas na COPIA
            # de trabalho: o arquivo de entrada nunca e tocado (regra 1).
            aviso = "assinatura digital invalidada na copia de trabalho (o original nao e tocado)"
            r = util.executar(comando(linha, origem, destino, sidecar, threads, assinatura=True),
                              timeout=limite)
        if r.rc != 0:
            motivo = next((l for l in reversed((r.erro or "").splitlines()) if l.strip()), "")
            raise RuntimeError(f"ocrmypdf rc={r.rc}: {motivo[:200]}")
        if not destino.exists():
            raise RuntimeError("ocrmypdf terminou sem gravar o PDF de saida")

        car_por_pag, frac_ctrl, paginas_saida = medir_saida(destino, cfg.timeout)
        conf = confianca_media(destino, paginas_saida, linha["idioma_ocr"] or "eng", cfg.timeout)
        linha["conf_ocr_media"] = "" if conf is None else str(conf)

        resumo = (f"rota {rota}, {linha['idioma_ocr']}, {paginas_saida} pag, "
                  f"{car_por_pag} car/pag, frac_ctrl {frac_ctrl}, "
                  f"confianca {'n/d' if conf is None else conf}")
        if car_por_pag < CARACTERES_MINIMOS:
            return Feito("falhou", resumo,
                         f"OCR nao produziu texto: {car_por_pag} caracteres por pagina")
        avisos = [aviso] if aviso else []
        if frac_ctrl > 0.01:
            avisos.append(f"ainda ha {frac_ctrl:.1%} de caracteres de controle apos o OCR")
        if conf is not None and conf < 85:
            avisos.append(f"confianca media {conf} < 85: revisar")
        return Feito("ok", resumo, "; ".join(avisos))

    return processar
