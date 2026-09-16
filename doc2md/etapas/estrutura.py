"""Etapa 3 — estrutura: Docling -> Markdown + JSON + figuras.

Entrada por rota:
    A, B     PDF original (texto nativo)
    C, D, E  PDF normalizado pelo OCR em trabalho/<id>.pdf; exige estado_ocr = ok. Sem ele o
             documento fica 'pendente' (aguarda a etapa 2), nunca e convertido da camada podre.
O Docling roda sempre com do_ocr=False: OCR e trabalho do OCRmyPDF.

Saidas (ver Config.pasta):
    estrutura/<id>.md    Markdown com ancora <!-- p.N --> no inicio de cada pagina
    estrutura/<id>.json  DoclingDocument (proveniencia por item: pagina e bbox)
    assets/<id>/*.png    figuras, referenciadas por caminho relativo no .md

As ancoras nascem aqui porque so o Docling sabe em que pagina cada bloco esta; depois dele a
informacao existe apenas no JSON, e a limpeza (etapa 5) trabalha sobre o Markdown.
"""
import re
import shutil
import time
from pathlib import Path

from nucleo import ambiente, util
from nucleo.lote import Feito

VERSAO = 4  # 2: formula vira texto bruto; 3: resgata titulo do rodape; 4: recorte de cada formula

# Versao do que os MODELOS produzem (o JSON). Enquanto ela nao muda, corrigir a exportacao nao
# obriga a rodar o Docling de novo: o Markdown e regerado a partir do JSON, em segundos.
VERSAO_CONVERSAO = 2

# Regra 3: Markdown com menos que isto dos caracteres alfanumericos do pdftotext e falha.
# O criterio fino (>= 95 %) e do QA; aqui se barra a saida vazia ou truncada.
COBERTURA_MINIMA = 0.5

ROTAS_COM_OCR = ("C", "D", "E")


def pdf_de_entrada(cfg, linha):
    """(caminho, motivo_se_bloqueado)."""
    if linha["rota_efetiva"] in ROTAS_COM_OCR:
        pdf = cfg.pasta("trabalho") / f"{linha['id']}.pdf"
        if linha["estado_ocr"] != "ok" or not pdf.exists():
            return None, f"aguarda OCR (etapa 2, rota {linha['rota_efetiva']})"
        return pdf, ""
    return cfg.entrada / linha["arquivo_origem"], ""


def _alfanumericos(texto):
    return len(re.findall(r"\w", texto))


def _caracteres_pdftotext(pdf, timeout):
    r = util.executar([ambiente.exe("pdftotext"), "-q", "-enc", "UTF-8", "-eol", "unix", pdf, "-"],
                      timeout=timeout)
    return _alfanumericos(r.saida)


class Conversor:
    """Carrega os modelos do Docling uma vez (segundos) e converte documento a documento.
    O paralelismo e interno (threads do torch), por isso a etapa roda com jobs=1."""

    def __init__(self, threads, timeout_doc=None, latex=False, dispositivo="auto"):
        from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import (PdfPipelineOptions, TableFormerMode,
                                                        TableStructureOptions)
        from docling.document_converter import DocumentConverter, PdfFormatOption

        op = PdfPipelineOptions()
        op.do_ocr = False
        op.do_table_structure = True
        op.table_structure_options = TableStructureOptions(mode=TableFormerMode.ACCURATE,
                                                           do_cell_matching=True)
        op.generate_picture_images = True      # rota G: figuras e abacos viram PNG referenciado
        op.images_scale = 2.0                  # 144 dpi
        op.heading_hierarchy_options.enabled = True   # nivel do titulo pela numeracao 4.2.3
        op.do_formula_enrichment = latex       # modelo de formula -> LaTeX; lento em CPU
        op.accelerator_options = AcceleratorOptions(
            num_threads=threads,
            device={"auto": AcceleratorDevice.AUTO, "cpu": AcceleratorDevice.CPU,
                    "cuda": AcceleratorDevice.CUDA}[dispositivo])
        op.document_timeout = timeout_doc
        self._conv = DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=op)})

    def converter(self, pdf, md_path, json_path, assets_dir):
        from docling.datamodel.base_models import ConversionStatus
        res = self._conv.convert(pdf, raises_on_error=False)
        erros = "; ".join(e.error_message for e in (res.errors or []))[:200]
        if res.status not in (ConversionStatus.SUCCESS, ConversionStatus.PARTIAL_SUCCESS):
            raise RuntimeError(f"Docling: {res.status.value} {erros}")
        doc = res.document
        resgatados = resgatar_titulos(doc)
        md = exportar_markdown(doc, md_path, assets_dir, pdf=pdf)
        doc.save_as_json(json_path, artifacts_dir=_relativo(assets_dir, json_path.parent),
                         image_mode=_image_ref_mode().REFERENCED, ensure_ascii=False)
        return doc, md, (erros if res.status == ConversionStatus.PARTIAL_SUCCESS else ""), resgatados


def _image_ref_mode():
    from docling_core.types.doc import ImageRefMode
    return ImageRefMode


def _relativo(destino, base):
    """Caminho relativo lexico (../assets/<id>): o .md continua valido se a saida mudar de lugar."""
    import os
    return Path(os.path.relpath(destino, base))


MARCA_FORMULA = "<!-- formula: texto bruto do PDF, sem LaTeX; a ordem dos simbolos pode estar trocada -->"
MARCA_FORMULA_IMG = "<!-- formula: recorte fiel da pagina; o texto abaixo e o do PDF, e a ordem dos simbolos pode estar trocada -->"

DPI_FORMULA = 220      # legivel na tela sem inflar o acervo
MARGEM_FORMULA = 3.0   # pontos em volta do bbox, para nao cortar indice e expoente


def recortar_formulas(doc, pdf, assets_dir, md_dir):
    """Um PNG por formula, recortado da pagina pelo bbox do proprio Docling.

    O texto de formula do PDF vem com a ordem de leitura embaralhada em quase um terco dos casos
    ('2 s s 4 d F C q π =' na NBR 6123). O recorte e fiel por construcao: nao depende de modelo,
    nao alucina e funciona igual em documento OCRizado, onde o texto e irrecuperavel.

    Devolve {self_ref: caminho relativo ao .md}."""
    import pypdfium2
    from docling_core.types.doc import CoordOrigin, DocItemLabel

    formulas = [t for t in doc.texts
                if t.label == DocItemLabel.FORMULA and t.prov and not (t.text or "").strip()]
    if not formulas:
        return {}
    por_pagina = {}
    for item in formulas:
        por_pagina.setdefault(item.prov[0].page_no, []).append(item)

    rel = _relativo(assets_dir, md_dir).as_posix()
    assets_dir.mkdir(parents=True, exist_ok=True)
    mapa = {}
    documento = pypdfium2.PdfDocument(str(pdf))
    try:
        for page_no in sorted(por_pagina):
            if page_no not in doc.pages or page_no > len(documento):
                continue
            tamanho = doc.pages[page_no].size
            imagem = documento[page_no - 1].render(scale=DPI_FORMULA / 72).to_pil()
            sx, sy = imagem.width / tamanho.width, imagem.height / tamanho.height
            for k, item in enumerate(por_pagina[page_no], 1):
                b = item.prov[0].bbox
                if b.coord_origin == CoordOrigin.BOTTOMLEFT:
                    topo, base = tamanho.height - b.t, tamanho.height - b.b
                else:
                    topo, base = b.t, b.b
                caixa = (max(0, int((b.l - MARGEM_FORMULA) * sx)),
                         max(0, int((topo - MARGEM_FORMULA) * sy)),
                         min(imagem.width, int((b.r + MARGEM_FORMULA) * sx)),
                         min(imagem.height, int((base + MARGEM_FORMULA) * sy)))
                if caixa[2] - caixa[0] < 4 or caixa[3] - caixa[1] < 4:
                    continue
                nome = f"formula-p{page_no:03}-{k:02}.png"
                imagem.crop(caixa).save(assets_dir / nome)
                mapa[item.self_ref] = f"{rel}/{nome}"
    finally:
        documento.close()
    return mapa

# Titulo de item numerado: "5.7.4.4 Vibracoes". Comeca em digito nao nulo e tem texto depois.
TITULO_DE_ITEM = re.compile(r"^[1-9]\d?(?:\.\d{1,3})*\s+[^\W\d_].{0,118}$")


def resgatar_titulos(doc):
    """O modelo de layout manda para cabecalho/rodape o titulo de item que cai no pe da pagina, e
    o export do corpo o descarta em silencio — na NBR 8883, '5.7.4.4 Vibracoes' (p. 26) virou
    page_footer e sumiu do Markdown, deixando o subitem 5.7.4.4.1 orfao. Aqui esses titulos
    voltam para o corpo. Marca d'agua e numero de pagina nao casam com o padrao e ficam fora."""
    from docling_core.types.doc import ContentLayer, DocItemLabel
    resgatados = []
    for item in doc.texts:
        if (item.content_layer == ContentLayer.FURNITURE
                and item.label in (DocItemLabel.PAGE_HEADER, DocItemLabel.PAGE_FOOTER)
                and TITULO_DE_ITEM.match((item.text or "").strip())):
            item.content_layer = ContentLayer.BODY
            item.label = DocItemLabel.SECTION_HEADER
            resgatados.append(item.text.strip()[:40])
    return resgatados


def _serializador_texto(recortes=None):
    """Sem enriquecimento de formula, o docling-core troca a formula por
    '<!-- formula-not-decoded -->' e o texto some (NBR 8883: 24 formulas, entre elas
    'Fd = γ F. ψ . Fk'). Aqui a formula sai com o recorte fiel da pagina, quando ha, mais o
    texto que o PDF tem."""
    from docling_core.transforms.serializer.common import create_ser_result
    from docling_core.transforms.serializer.markdown import MarkdownTextSerializer
    from docling_core.types.doc import FormulaItem

    recortes = recortes or {}

    class _TextoComFormula(MarkdownTextSerializer):
        def serialize(self, *, item, doc_serializer, doc, is_inline_scope=False, **kwargs):
            if isinstance(item, FormulaItem) and not item.text and item.orig:
                bruto = " ".join(item.orig.split())
                if is_inline_scope:
                    texto = f"`{bruto}`"
                elif png := recortes.get(item.self_ref):
                    texto = f"{MARCA_FORMULA_IMG}\n![formula]({png})\n\n`{bruto}`"
                else:
                    texto = f"{MARCA_FORMULA}\n`{bruto}`"
                return create_ser_result(text=texto, span_source=item)
            return super().serialize(item=item, doc_serializer=doc_serializer, doc=doc,
                                     is_inline_scope=is_inline_scope, **kwargs)

    return _TextoComFormula()


def versao_registrada(linha, etapa="estrutura"):
    for parte in linha["versoes"].split(";"):
        if parte.startswith(f"{etapa}=") and parte.split("=")[1].isdigit():
            return int(parte.split("=")[1])
    return None


def reexportar(json_path, md_path, assets_dir, pdf=None):
    """Regera o Markdown a partir do JSON ja gravado, sem chamar os modelos."""
    from docling_core.types.doc import DoclingDocument
    doc = DoclingDocument.load_from_json(json_path)
    resgatados = resgatar_titulos(doc)
    # As figuras ja estao em disco e o JSON guarda o caminho relativo delas: nao mexer.
    md = exportar_markdown(doc, md_path, assets_dir, ja_referenciado=True, pdf=pdf)
    return doc, md, resgatados


def exportar_markdown(doc, md_path, assets_dir, ja_referenciado=False, pdf=None):
    """Markdown do Docling com a quebra de pagina trocada por <!-- p.N --> (N = pagina que comeca).

    O serializador do docling-core marca cada quebra com as paginas anterior e seguinte, mas o
    export publico troca tudo por um texto fixo; aqui a troca preserva o numero."""
    from docling_core.transforms.serializer.base import SerializationResult  # noqa: F401
    from docling_core.transforms.serializer.common import create_ser_result
    from docling_core.transforms.serializer.markdown import MarkdownDocSerializer, MarkdownParams
    from docling_core.types.doc.document import DEFAULT_CONTENT_LAYERS, DOCUMENT_TOKENS_EXPORT_LABELS

    class _ComPaginas(MarkdownDocSerializer):
        def serialize_doc(self, *, parts, **kwargs):
            texto = "\n\n".join(p.text for p in parts if p.text)
            for marca, _anterior, seguinte in self._get_page_breaks(text=texto):
                texto = texto.replace(marca, f"<!-- p.{seguinte} -->", 1)
            return create_ser_result(text=texto, span_source=parts)

        def requires_page_break(self):
            return True

    rel = _relativo(assets_dir, md_path.parent)
    ref_doc = doc if ja_referenciado else doc._make_copy_with_refmode(
        md_path.parent / rel, _image_ref_mode().REFERENCED, None, reference_path=md_path.parent)
    recortes = recortar_formulas(doc, pdf, assets_dir, md_path.parent) if pdf else {}
    ser = _ComPaginas(doc=ref_doc, text_serializer=_serializador_texto(recortes),
                      params=MarkdownParams(
        labels=DOCUMENT_TOKENS_EXPORT_LABELS, layers=DEFAULT_CONTENT_LAYERS,
        image_mode=_image_ref_mode().REFERENCED,
        # Corpus para IA: "&lt;" e "\_" sao ruido para o modelo e para a busca por regex.
        escape_html=False, escape_underscores=False,
    ))
    md = ser.serialize().text
    md = md.replace("<!-- formula-not-decoded -->", "")   # rede de seguranca: nunca apagar formula
    primeira = min((it.prov[0].page_no for it, _ in doc.iterate_items()
                    if getattr(it, "prov", None)), default=1)
    md = f"<!-- p.{primeira} -->\n\n{md}\n"
    md_path.write_text(md, encoding="utf-8")
    return md


def silenciar_bibliotecas(verboso=False):
    """Docling/transformers/HF escrevem avisos de rotina (celula orfa de tabela, symlink do cache
    no Windows, barras de progresso) — varios deles no stdout, que aqui e canal de resultado.
    Ficam so com --verboso. Erros continuam aparecendo."""
    import logging
    import os
    if verboso:
        return
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
    os.environ.setdefault("TQDM_DISABLE", "1")
    # Os loggers do TableFormer levam o nome da classe ("MatchingPostProcessor") e sao criados
    # quando o modelo carrega; por isso a varredura do registro, e nao uma lista de nomes.
    for nome, lg in list(logging.root.manager.loggerDict.items()):
        if nome.split(".")[0] != "doc2md" and isinstance(lg, logging.Logger):
            lg.setLevel(logging.ERROR)


def criar_processador(cfg, threads, overrides=None, verboso=False, forcar=False):
    """overrides: {id: {...}}; `formulas = "latex"` num documento liga o modelo de formula."""
    silenciar_bibliotecas(verboso)
    overrides = overrides or {}
    conversores = {}

    def conversor(latex):
        if latex not in conversores:
            t = time.monotonic()
            util.LOG.info("carregando modelos do Docling (%s, %d threads%s)...", cfg.dispositivo,
                          threads, ", formulas -> LaTeX" if latex else "")
            conversores[latex] = Conversor(threads, latex=latex, dispositivo=cfg.dispositivo)
            silenciar_bibliotecas(verboso)   # de novo: os loggers do TableFormer nascem agora
            util.LOG.info("modelos carregados em %.0fs", time.monotonic() - t)
        return conversores[latex]

    def processar(linha):
        silenciar_bibliotecas(verboso)   # loggers de terceiros nascem ao longo da conversao
        pdf, bloqueio = pdf_de_entrada(cfg, linha)
        if bloqueio:
            return Feito("pendente", aviso=bloqueio)
        id_ = linha["id"]
        md_path = cfg.pasta("estrutura") / f"{id_}.md"
        json_path = md_path.with_suffix(".json")
        assets = cfg.pasta("assets") / id_
        md_path.parent.mkdir(parents=True, exist_ok=True)

        gravada = versao_registrada(linha)
        so_exportacao = (not forcar and json_path.exists() and gravada is not None
                         and gravada >= VERSAO_CONVERSAO)
        t = time.monotonic()
        if so_exportacao:
            md_path.unlink(missing_ok=True)
            doc, md, resgatados = reexportar(json_path, md_path, assets, pdf=pdf)
            parcial = ""
        else:
            for velho in (md_path, json_path):
                velho.unlink(missing_ok=True)
            shutil.rmtree(assets, ignore_errors=True)
            latex = overrides.get(id_, {}).get("formulas") == "latex"
            doc, md, parcial, resgatados = conversor(latex).converter(pdf, md_path, json_path, assets)
        dt = time.monotonic() - t

        ref = _caracteres_pdftotext(pdf, cfg.timeout)
        cobertura = _alfanumericos(md) / ref if ref else 0.0
        paginas = len(doc.pages)
        titulos = len(re.findall(r"(?m)^#{1,6} \S", md))
        tabelas = len(doc.tables)
        figuras = len(list(assets.glob("*.png"))) if assets.exists() else 0
        ancoras = len(re.findall(r"<!-- p\.\d+ -->", md))
        brutas = md.count(MARCA_FORMULA) + md.count(MARCA_FORMULA_IMG)
        recortadas = md.count(MARCA_FORMULA_IMG)
        resumo = (("reexportado do JSON: " if so_exportacao else "")
                  + f"{paginas} pag, {titulos} titulos ({len(resgatados)} resgatados do rodape), "
                  f"{tabelas} tabelas, {figuras} figuras, "
                  f"{brutas} formulas ({recortadas} com recorte), "
                  f"cobertura {cobertura:.2f}, {dt:.0f}s ({dt / max(paginas, 1):.1f} s/pag)")
        # Reexportacao mexe no Markdown, nao no JSON: as tabelas (que saem do PDF, pelas paginas
        # do JSON) continuam validas e nao precisam ser refeitas.
        invalida = ("limpeza", "metadados") if so_exportacao else None
        if not md.strip() or cobertura < COBERTURA_MINIMA:
            return Feito("falhou", resumo, f"saida abaixo do limiar: cobertura {cobertura:.2f} "
                                           f"< {COBERTURA_MINIMA} dos caracteres do pdftotext")
        avisos = []
        if parcial:
            avisos.append(f"conversao parcial: {parcial}")
        if ancoras < paginas * 0.5:
            avisos.append(f"so {ancoras} ancoras de pagina para {paginas} paginas")
        return Feito("ok", resumo, "; ".join(avisos), invalida)

    return processar
