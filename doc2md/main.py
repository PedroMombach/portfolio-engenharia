#!/usr/bin/env python3
"""Doc2MD — conversor de acervo documental (PDF) para Markdown consumivel por IA.

Unico ponto de entrada. O contrato da linha de comando esta no README.md; se esta
implementacao divergir dele, e a implementacao que esta errada.

Codigos de saida: 0 ok | 1 algum documento falhou (o lote seguiu) | 2 erro de uso/configuracao.
"""
import argparse
import sys
import time
from collections import Counter
from pathlib import Path

from etapas import estrutura, higiene, limpeza, metadados, ocr, qa, renomear, tabelas, triagem
from nucleo import ambiente, config, lote, util
from nucleo.manifesto import Manifesto

RAIZ = Path(__file__).resolve().parent
LOG = util.LOG

OK, FALHA_DOC, ERRO_USO = 0, 1, 2


# --- init ------------------------------------------------------------------------------------

def _perguntar(texto, padrao, interativo, opcao):
    """interativo: dict mutavel, para que o primeiro EOF desligue as perguntas seguintes."""
    sufixo = f" [{padrao}]" if padrao not in (None, "") else ""
    while interativo["sim"]:
        try:
            r = input(f"{texto}{sufixo}: ").strip().strip('"')
        except EOFError:  # no Windows, stdin = NUL passa por TTY
            print()
            interativo["sim"] = False
            break
        if r or padrao is not None:
            return r or padrao
    if padrao is None:
        raise config.ErroConfig(f"{opcao} e obrigatorio fora do modo interativo")
    return padrao


def cmd_init(args):
    destino = args.config.resolve()
    if destino.exists() and not args.forcar:
        raise config.ErroConfig(f"{destino} ja existe; use --forcar para sobrescrever")
    interativo = {"sim": sys.stdin.isatty()}
    entrada = args.entrada or Path(_perguntar(
        "Diretorio de entrada (acervo de PDFs, somente leitura)", None, interativo, "--entrada"))
    entrada = Path(entrada).resolve()
    saida = args.saida or Path(_perguntar(
        "Diretorio de saida", str(entrada.parent / f"{entrada.name}-MD"), interativo, "--saida"))
    saida = Path(saida).resolve()
    config.validar_caminhos(entrada, saida, RAIZ)
    achado = config.procurar_overrides(entrada)
    overrides = _perguntar("Arquivo de overrides (vazio = nenhum)",
                           str(achado) if achado else "", interativo, "--overrides")
    perfis = sorted(p.stem for p in (RAIZ / "perfis").glob("*.toml"))
    perfil = _perguntar(f"Perfil de limpeza ({', '.join(perfis)})", "padrao", interativo, "--perfil")
    if perfil not in perfis:
        raise config.ErroConfig(f"perfil '{perfil}' nao existe em perfis/")
    texto = config.gerar_toml(entrada, saida, overrides, perfil, args.jobs or 0)
    if args.simular:
        print(texto)
        LOG.info("--simular: %s nao foi gravado", destino)
        return OK
    destino.write_text(texto, encoding="utf-8")
    LOG.info("config gravado: %s", destino)
    LOG.info("proximo passo: python main.py doutor   e depois   python main.py inventariar")
    return OK


# --- doutor ----------------------------------------------------------------------------------

def cmd_doutor(args):
    try:
        cfg = _config(args, exigir=False)
    except config.ErroConfig as e:
        LOG.warning("config ignorado: %s", e)
        cfg = None
    checagens = ambiente.checar(cfg)
    rotulo = {"ok": "[ ok  ]", "aviso": "[AVISO]", "falta": "[FALTA]"}
    print(f"Doc2MD doutor — {RAIZ}\n")
    for c in checagens:
        print(f"{rotulo[c.estado]} {c.nome:<12} {c.detalhe}")
        if c.correcao and c.estado != "ok":
            print(f"{'':20}-> {c.correcao}")
    bloqueados = {}
    for c in checagens:
        if c.estado == "falta":
            for cmd in c.comandos:
                bloqueados.setdefault(cmd, []).append(c.nome)
    prontos = [n for n in COMANDOS if n != "tudo" and n not in bloqueados
               and "todos" not in bloqueados]
    print(f"\nComandos prontos:    {', '.join(prontos) or '(nenhum)'}")
    if bloqueados:
        print("Comandos bloqueados: " + "; ".join(f"{k} (falta {', '.join(v)})"
                                                 for k, v in bloqueados.items()))
    return OK if not bloqueados else FALHA_DOC


# --- inventariar (etapas 0 + 1) ----------------------------------------------------------------

def cmd_inventariar(args):
    cfg = _config(args)
    overrides = config.carregar_overrides(cfg.overrides)
    jobs = cfg.nucleos()
    man = Manifesto.carregar(cfg.saida)

    arquivos, ignorados = higiene.varrer(cfg.entrada, cfg.extensoes)
    if ignorados:
        LOG.info("fora do escopo (ignorados): %s",
                 ", ".join(f"{len(n)} {ext}" for ext, n in sorted(ignorados.items())))
    for ext in set(ignorados) & set(higiene.PARCIAIS):
        LOG.warning("download incompleto (%s): %s — refaca o download", ext, ", ".join(ignorados[ext]))
    for nome in ignorados.get(".epub", []):
        LOG.warning("EPUB fora do escopo; converta com outra ferramenta: %s", nome)
    if not arquivos:
        raise config.ErroConfig(f"nenhum {'/'.join(cfg.extensoes)} em {cfg.entrada}")

    falhas = 0
    docs = {}
    for p in arquivos:
        id_ = util.slug(p.stem)
        if id_ in docs:
            LOG.error("id duplicado '%s': %s e %s — renomeie um deles; o segundo foi ignorado",
                      id_, docs[id_].name, p.name)
            falhas += 1
            continue
        docs[id_] = p

    filtrado = bool(args.so_doc or args.so_rota)
    alvo = [i for i in docs if not filtrado or _selecionado(man.linhas.get(i), i, args)]
    if args.so_doc and not alvo:
        raise config.ErroConfig(f"--so-doc {args.so_doc}: nenhum documento com esse id na entrada")

    # 0 — hash
    t0 = time.monotonic()
    hashes = {}
    for i, h, erro in util.em_paralelo(lambda i: util.sha256(docs[i]), alvo, jobs):
        if erro:
            LOG.error("%s: nao foi possivel ler (%s)", i, erro)
            falhas += 1
        else:
            hashes[i] = h
    LOG.info("sha256 de %d arquivo(s) em %.1fs", len(hashes), time.monotonic() - t0)

    # Reconciliacao com o manifesto: novo, inalterado, alterado, renomeado, removido.
    ausentes = set() if filtrado else set(man.linhas) - set(docs)
    por_sha = {man.linhas[a]["sha256_origem"]: a for a in ausentes if man.linhas[a]["sha256_origem"]}
    para_triar = []
    for i in hashes:
        linha = man.linhas.get(i)
        if linha is None:
            antigo = por_sha.pop(hashes[i], None)
            if antigo:
                LOG.info("renomeado: %s -> %s (diagnostico preservado)", antigo, i)
                ausentes.discard(antigo)
                linha = man.renomear(antigo, i)
                man.invalidar(linha, "ocr")  # as saidas ficaram com o id antigo
            else:
                linha = man.nova(i)
        elif linha["sha256_origem"] and linha["sha256_origem"] != hashes[i]:
            LOG.warning("%s: o PDF mudou desde o ultimo inventario; etapas seguintes invalidadas", i)
            man.invalidar(linha, "triagem")
        linha["arquivo_origem"] = docs[i].relative_to(cfg.entrada).as_posix()
        linha["sha256_origem"] = hashes[i]
        man.anotar(linha, "higiene", "; ".join(higiene.avisos_nome(docs[i])))
        if (args.forcar or man.versao(linha, "triagem") != triagem.VERSAO
                or linha["rota_sugerida"] in ("", "ERRO")
                or (linha["integridade"] in ("", "nao_verificado") and higiene.verificador())):
            para_triar.append(i)
    for a in sorted(ausentes):
        LOG.warning("%s: arquivo nao existe mais na entrada; removido do manifesto", a)
        man.remover(a)

    # 1 — integridade + diagnostico
    def triar(i):
        t = time.monotonic()
        integ = higiene.integridade(docs[i], cfg.timeout)
        return integ, triagem.diagnosticar(docs[i], cfg.timeout), time.monotonic() - t

    LOG.info("triagem de %d documento(s) (%d ja triados e inalterados), %d em paralelo",
             len(para_triar), len(hashes) - len(para_triar), jobs)
    for k, (i, res, erro) in enumerate(util.em_paralelo(triar, para_triar, jobs), 1):
        linha = man.linhas[i]
        if erro:
            falhas += 1
            linha["rota_sugerida"] = "ERRO"
            man.definir_versao(linha, "triagem", None)
            man.anotar(linha, "triagem", str(erro))
            LOG.error("[%2d/%d] %s: FALHOU — %s", k, len(para_triar), i, erro)
        else:
            integ, diag, dt = res
            avisos = diag.pop("avisos")
            linha.update({c: str(v) for c, v in diag.items()})
            linha["integridade"] = integ
            man.definir_versao(linha, "triagem", triagem.VERSAO)
            man.anotar(linha, "triagem", "; ".join(avisos))
            LOG.info("[%2d/%d] %-64s rota %s  %4s pag  %5.1fs", k, len(para_triar), i,
                     diag["rota_sugerida"], diag["paginas"], dt)
        if not args.simular:
            man.salvar_parcial()

    # Decisao efetiva: override curado > heuristica. Mudou rota ou idioma -> refazer do OCR em diante.
    for i in hashes:
        linha = man.linhas[i]
        nova = triagem.decidir(i, linha["rota_sugerida"], overrides.get(i))
        mudou_rota = linha["rota_efetiva"] and linha["rota_efetiva"] != nova["rota_efetiva"]
        mudou_idioma = (linha["idioma_ocr"] and linha["idioma_ocr"] != nova["idioma_ocr"]
                        and nova["rota_efetiva"] in ("C", "D", "E"))
        if mudou_rota or mudou_idioma:
            LOG.warning("%s: rota/idioma mudou (%s/%s -> %s/%s); etapas invalidadas", i,
                        linha["rota_efetiva"], linha["idioma_ocr"],
                        nova["rota_efetiva"], nova["idioma_ocr"])
            man.invalidar(linha, "ocr")
        linha.update(nova)
    for id_ in sorted(set(overrides) - set(docs)):
        LOG.warning("overrides [%s]: nenhum documento com esse id (erro de digitacao?)", id_)

    if args.simular:
        LOG.info("--simular: manifesto nao gravado")
    else:
        man.salvar()
    _resumo(man, overrides, hashes)
    return FALHA_DOC if falhas else OK


def _resumo(man, overrides, ids):
    linhas = [l for l in man.ordenadas() if l["id"] in ids]
    w = max([len(l["id"]) for l in linhas] + [2])
    print(f"\n{'id':<{w}} {'pag':>4}  sug efet  legado revisar  integridade")
    for l in linhas:
        print(f"{l['id']:<{w}} {l['paginas']:>4}  {l['rota_sugerida']:^3} {l['rota_efetiva']:^4}"
              f"  {l['suspeita_ocr_legado']:^6} {l['revisar']:^7}  {l['integridade']}")
    div = [l for l in linhas if l["rota_sugerida"] != l["rota_efetiva"]]
    if div:
        print("\nRota sugerida x efetiva (a decisao curada vence):")
        for l in div:
            motivo = overrides.get(l["id"], {}).get("motivo", "")
            print(f"  {l['id']}: {l['rota_sugerida']} -> {l['rota_efetiva']}"
                  + (f"  ({motivo})" if motivo else ""))
    sem_ov = [l["id"] for l in linhas if overrides and l["id"] not in overrides]
    if sem_ov:
        print(f"\nSem override (vale a rota sugerida): {', '.join(sem_ov)}")
    cont = Counter(l["rota_efetiva"] for l in linhas)
    pags = Counter()
    for l in linhas:
        pags[l["rota_efetiva"]] += int(l["paginas"] or 0)
    print("\nPor rota efetiva: " + "  ".join(f"{r}={cont[r]} ({pags[r]} pag)" for r in sorted(cont)))
    print(f"Documentos: {len(linhas)}   Manifesto: {man.caminho}")


# --- etapas 2-6 ---------------------------------------------------------------------------------

def _etapa(args, etapa, modulo, criar, jobs_doc):
    """Roda uma etapa pelo executor comum. `criar(cfg, threads)` devolve processar(linha)."""
    cfg = _config(args)
    man = Manifesto.carregar(cfg.saida)
    _, falhas = lote.rodar(man, cfg, args, etapa, modulo.VERSAO, criar(cfg, cfg.nucleos()),
                           jobs=jobs_doc(cfg))
    return FALHA_DOC if falhas else OK


def cmd_converter(args):
    if not ambiente.localizar("pdftotext"):
        raise config.ErroConfig("pdftotext ausente; rode `python main.py doutor`")
    try:
        import docling  # noqa: F401  (import leve; os modelos so carregam no 1o documento)
    except ImportError:
        raise config.ErroConfig("docling nao instalado neste ambiente; rode `python main.py doutor`")
    # Docling paraleliza por dentro (torch): um documento por vez, todas as threads nele.
    def criar(cfg, threads):
        ov = config.carregar_overrides(cfg.overrides)
        return estrutura.criar_processador(cfg, threads, ov, args.verboso, args.forcar)
    return _etapa(args, "estrutura", estrutura, criar, lambda cfg: 1)


def cmd_renomear(args):
    """Etapa 0b. Unico comando que escreve na entrada: simula por padrao e so aplica com --forcar."""
    cfg = _config(args)
    pares = renomear.ler_depara(args.depara)
    plano = renomear.planejar(cfg.entrada, pares)
    aplicar = args.forcar and not args.simular
    man = Manifesto.carregar(cfg.saida) if aplicar else None
    if aplicar:
        plano = renomear.aplicar(cfg.entrada, plano, man)
    parciais = renomear.isolar_parciais(cfg.entrada, aplicar)

    largura = max([len(o.as_posix()) for _, o, _, _ in plano] + [10])
    print(f"\n{'SIMULACAO' if not aplicar else 'EXECUCAO'} — {len(plano)} linha(s) no de-para\n")
    for status, origem, destino, _ in plano:
        print(f"[{status:<17}] {origem.as_posix():<{largura}} -> {destino.as_posix()}")
    for origem, destino in parciais:
        print(f"[{'DOWNLOAD_PARCIAL':<17}] {origem.as_posix():<{largura}} -> {destino.as_posix()}")
    contagem = Counter(s.split(":")[0] for s, _, _, _ in plano)
    print("\n" + "  ".join(f"{k}={v}" for k, v in sorted(contagem.items())))

    if aplicar:
        man.salvar()
        log = cfg.saida / "renomeacao-log.csv"
        renomear.gravar_log(log, plano, parciais)
        LOG.info("log: %s", log)
        LOG.info("rode `python main.py inventariar` para reconciliar o manifesto")
    else:
        LOG.info("nada foi alterado. Confira o de-para acima e rode com --forcar para aplicar.")
    return FALHA_DOC if any(s.startswith("FALHOU") for s, _, _, _ in plano) else OK


def cmd_ocr(args):
    if not ambiente.localizar("tesseract"):
        raise config.ErroConfig("tesseract ausente; rode `python main.py doutor`")
    # OCRmyPDF ja paraleliza por pagina (--jobs): um documento por vez.
    return _etapa(args, "ocr", ocr, lambda cfg, threads: ocr.criar_processador(cfg, threads),
                  lambda cfg: 1)


def cmd_limpar(args):
    def criar(cfg, threads):
        return limpeza.criar_processador(cfg, threads, config.carregar_overrides(cfg.overrides),
                                         raiz_ferramenta=RAIZ)
    return _etapa(args, "limpeza", limpeza, criar, lambda cfg: cfg.nucleos())


def cmd_metadados(args):
    def criar(cfg, threads):
        return metadados.criar_processador(cfg, threads, config.carregar_overrides(cfg.overrides))
    return _etapa(args, "metadados", metadados, criar, lambda cfg: cfg.nucleos())


def cmd_qa(args):
    """Etapa 7. Nao usa o executor comum: o QA nao e idempotente por projeto — ele reavalia
    tudo toda vez, senao a verificacao passaria a confiar no proprio carimbo anterior."""
    cfg = _config(args)
    overrides = config.carregar_overrides(cfg.overrides)
    man = Manifesto.carregar(cfg.saida)
    linhas = man.filtrar(args.so_rota, args.so_doc)
    if not linhas:
        raise config.ErroConfig("nenhum documento no manifesto (rode `python main.py inventariar`)")
    lote.conferir_origens(cfg, linhas, cfg.nucleos())

    prontos = [l for l in linhas if l["estado_metadados"] == "ok"]
    pendentes = [(l["id"], _motivo_pendente(l)) for l in linhas if l["estado_metadados"] != "ok"]

    def avaliar(linha):
        ov = overrides.get(linha["id"], {})
        regras = limpeza.carregar_regras(cfg, RAIZ, ov)
        pdf, bloqueio = estrutura.pdf_de_entrada(cfg, linha)
        if bloqueio:
            raise RuntimeError(bloqueio)
        md = (cfg.pasta("corpus") / f"{linha['id']}.md").read_text(encoding="utf-8")
        return qa.avaliar(cfg, linha, regras, pdf, md, _tabelas_docling(cfg, linha["id"]))

    resultados, reprovados = [], 0
    for k, (linha, res, erro) in enumerate(util.em_paralelo(avaliar, prontos, cfg.nucleos()), 1):
        if erro:
            veredito, reprovas, revisoes, metricas = "reprovado", [f"erro no QA: {erro}"], [], {}
        else:
            veredito, reprovas, revisoes, metricas = res
        for c, v in metricas.items():
            linha[c] = str(v)
        linha["qa"] = veredito
        man.anotar(linha, "qa", "; ".join(reprovas + revisoes))
        reprovados += veredito == "reprovado"
        resultados.append({"id": linha["id"], "veredito": veredito, "reprovas": reprovas,
                           "revisoes": revisoes, "metricas": metricas,
                           "tabelas": linha["tabelas_extraidas"]})
        nivel = LOG.error if veredito == "reprovado" else LOG.info
        nivel("[%2d/%d] %-64s %-10s %s", k, len(prontos), linha["id"], veredito,
              "; ".join(reprovas + revisoes)[:120])

    if args.simular:
        LOG.info("--simular: manifesto e relatorio nao gravados")
    else:
        man.salvar()
        caminho = cfg.saida / "relatorio-qa.md"
        util.gravar_atomico(caminho, qa.relatorio(cfg, resultados, pendentes))
        LOG.info("relatorio: %s", caminho)
    print(f"\nQA: {sum(r['veredito'] == 'aprovado' for r in resultados)} aprovado(s), "
          f"{sum(r['veredito'] == 'revisar' for r in resultados)} para revisar, "
          f"{reprovados} reprovado(s); {len(pendentes)} fora do QA (etapa pendente)")
    return FALHA_DOC if reprovados else OK


def _motivo_pendente(linha):
    for etapa in ("ocr", "estrutura", "tabelas", "limpeza", "metadados"):
        if linha[f"estado_{etapa}"] not in ("ok", "pulado"):
            return f"etapa {etapa} em '{linha[f'estado_{etapa}']}'"
    return "?"


def _tabelas_docling(cfg, id_):
    import json
    caminho = cfg.pasta("estrutura") / f"{id_}.json"
    if not caminho.exists():
        return None
    return len(json.loads(caminho.read_text(encoding="utf-8")).get("tables", []))


def cmd_tabelas(args):
    try:
        import camelot  # noqa: F401
    except ImportError:
        raise config.ErroConfig("camelot nao instalado neste ambiente; rode `python main.py doutor`")

    def criar(cfg, threads):
        return tabelas.criar_processador(cfg, threads, config.carregar_overrides(cfg.overrides))
    return _etapa(args, "tabelas", tabelas, criar, lambda cfg: cfg.nucleos())


def cmd_tudo(args):
    pior = OK
    for nome in ("inventariar", "ocr", "converter", "tabelas", "limpar", "metadados", "qa"):
        LOG.info("=== %s ===", nome)
        args.comando = nome
        rc = COMANDOS[nome][1](args)
        if rc == ERRO_USO:
            LOG.error("`tudo` interrompido em '%s'", nome)
            return rc
        pior = max(pior, rc)
    return pior


COMANDOS = {
    "init": ("cria config.toml no diretorio atual, a partir de perguntas", cmd_init),
    "doutor": ("confere as dependencias externas e os idiomas do Tesseract", cmd_doutor),
    "inventariar": ("etapas 0+1: varre a entrada, calcula hash, diagnostica, escreve manifesto.csv",
                    cmd_inventariar),
    "renomear": ("etapa 0b: aplica um de-para CSV; --simular por padrao", cmd_renomear),
    "ocr": ("etapa 2: OCRmyPDF conforme a rota de cada documento", cmd_ocr),
    "converter": ("etapa 3: Docling -> Markdown + JSON + assets", cmd_converter),
    "tabelas": ("etapa 4: Camelot/pdfplumber -> CSV", cmd_tabelas),
    "limpar": ("etapa 5: regras do perfil, hifenizacao, headings", cmd_limpar),
    "metadados": ("etapa 6: front-matter YAML + ancoras <!-- p.N -->", cmd_metadados),
    "qa": ("etapa 7: criterios de aceitacao; codigo de saida != 0 se reprovar", cmd_qa),
    "tudo": ("encadeia inventariar -> qa", cmd_tudo),
}


# --- infraestrutura da CLI ---------------------------------------------------------------------

def _config(args, exigir=True):
    cfg = config.carregar(args.config, args.entrada, args.saida, args.jobs,
                          exigir=exigir, raiz_ferramenta=RAIZ)
    ambiente.configurar(cfg.ferramentas)
    if exigir and not args.simular:
        cfg.saida.mkdir(parents=True, exist_ok=True)
        if not getattr(args, "_log_arquivo", False):
            util.log_em_arquivo(cfg.saida / "doc2md.log")
            args._log_arquivo = True
            LOG.debug("comando: %s", " ".join(sys.argv))
    return cfg


def _selecionado(linha, id_, args):
    if args.so_doc and id_ != args.so_doc:
        return False
    if args.so_rota and (not linha or linha["rota_efetiva"] not in args.so_rota):
        return False
    return True


def _rotas(texto):
    rotas = {r.strip().upper() for r in texto.split(",") if r.strip()}
    if not rotas or rotas - set(config.ROTAS):
        raise argparse.ArgumentTypeError(f"rotas validas: {','.join(config.ROTAS)}")
    return rotas


def construir_parser():
    comum = argparse.ArgumentParser(add_help=False)
    g = comum.add_argument_group("opcoes globais")
    g.add_argument("--config", type=Path, default=Path("config.toml"), metavar="ARQ",
                   help="caminho do config.toml (padrao: ./config.toml)")
    g.add_argument("--entrada", type=Path, metavar="DIR", help="sobrescreve a entrada do config")
    g.add_argument("--saida", type=Path, metavar="DIR", help="sobrescreve a saida do config")
    g.add_argument("--so-rota", type=_rotas, metavar="A,B",
                   help="processa apenas documentos nessas rotas")
    g.add_argument("--so-doc", metavar="ID", help="processa apenas um documento")
    g.add_argument("--jobs", type=int, metavar="N", help="paralelismo (padrao: nucleos - 1)")
    g.add_argument("--simular", action="store_true", help="nao escreve nada; imprime o que faria")
    g.add_argument("--forcar", action="store_true", help="refaz etapa ja concluida")
    g.add_argument("--verboso", action="store_true")

    p = argparse.ArgumentParser(prog="python main.py",
                                description="Doc2MD: acervo de PDFs -> corpus Markdown para IA.")
    sub = p.add_subparsers(dest="comando", required=True, metavar="<comando>")
    for nome, (ajuda, _) in COMANDOS.items():
        sp = sub.add_parser(nome, parents=[comum], help=ajuda, description=ajuda)
        if nome == "renomear":
            sp.add_argument("depara", type=Path, metavar="DEPARA.csv",
                            help="CSV de-para (colunas: nome_atual, nome_novo, "
                                 "opcionalmente pasta_origem e pasta_destino)")
    return p


def main(argv=None):
    args = construir_parser().parse_args(argv)
    util.configurar_log(args.verboso)
    try:
        return COMANDOS[args.comando][1](args)
    except config.ErroConfig as e:
        LOG.error("%s", e)
        return ERRO_USO
    except OSError as e:
        LOG.error("%s", e, exc_info=args.verboso)
        return ERRO_USO
    except KeyboardInterrupt:
        LOG.error("interrompido; o manifesto guarda o que ja foi concluido")
        return 130


if __name__ == "__main__":
    sys.exit(main())
