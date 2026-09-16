"""config.toml (onde estao entrada e saida, como rodar) e overrides.toml (decisao humana por documento)."""
import datetime
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from . import util

ROTAS = ("A", "B", "C", "D", "E")
EXTRAS = ("F", "G")
STATUS = ("vigente", "cancelada", "projeto", "traducao")
CHAVES_OVERRIDE = {"rota", "idioma_ocr", "motivo", "limpeza_extra", "tabelas", "status", "extras",
                   "perfil", "emissor", "codigo", "ano", "titulo", "observacao", "formulas"}


class ErroConfig(Exception):
    pass


@dataclass
class Config:
    entrada: Path | None = None
    saida: Path | None = None
    overrides: Path | None = None
    perfil: str = "padrao"
    jobs: int = 0
    timeout: int = 300
    extensoes: list = field(default_factory=lambda: [".pdf"])
    disco_min_gb: float = 5.0
    acuracia_min: float = 90.0   # etapa 4: abaixo disso a tabela vai para revisao no QA
    dispositivo: str = "auto"    # auto | cpu | cuda — onde rodam os modelos do Docling
    ferramentas: dict = field(default_factory=dict)
    arquivo: Path | None = None

    def nucleos(self):
        return self.jobs if self.jobs > 0 else util.nucleos_padrao()

    def pasta(self, nome):
        """Subdiretorios da saida, um por produto:
        trabalho/  PDF normalizado pelo OCR (etapa 2)
        estrutura/ Markdown + JSON do Docling (etapa 3)
        assets/    figuras, assets/<id>/*.png (etapa 3)
        tabelas/   <id>-<n>.csv (etapa 4)
        limpo/     Markdown apos a limpeza (etapa 5)
        corpus/    Markdown final, com front-matter e ancoras (etapa 6)"""
        return self.saida / nome


def carregar(caminho, entrada=None, saida=None, jobs=None, exigir=True, raiz_ferramenta=None):
    """Le o config.toml (se existir) e aplica as opcoes da linha de comando por cima.
    exigir=True: entrada e saida precisam estar definidas e validas."""
    cfg = Config()
    caminho = Path(caminho)
    if caminho.exists():
        try:
            dados = tomllib.loads(caminho.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as e:
            raise ErroConfig(f"{caminho}: TOML invalido — {e}")
        base = caminho.resolve().parent
        cam = dados.get("caminhos", {})
        exe = dados.get("execucao", {})

        def resolver(v):
            return (base / v).resolve() if v else None

        cfg.entrada = resolver(cam.get("entrada"))
        cfg.saida = resolver(cam.get("saida"))
        cfg.overrides = resolver(cam.get("overrides"))
        cfg.perfil = exe.get("perfil", cfg.perfil)
        cfg.jobs = int(exe.get("jobs", cfg.jobs))
        cfg.timeout = int(exe.get("timeout", cfg.timeout))
        cfg.extensoes = [e.lower() for e in exe.get("extensoes", cfg.extensoes)]
        cfg.dispositivo = str(exe.get("dispositivo", cfg.dispositivo)).lower()
        if cfg.dispositivo not in ("auto", "cpu", "cuda"):
            raise ErroConfig(f"[execucao].dispositivo invalido: {cfg.dispositivo} (auto/cpu/cuda)")
        lim = dados.get("limiares", {})
        cfg.disco_min_gb = float(lim.get("disco_min_gb", cfg.disco_min_gb))
        cfg.acuracia_min = float(lim.get("acuracia_min", cfg.acuracia_min))
        cfg.ferramentas = dict(dados.get("ferramentas", {}))
        cfg.arquivo = caminho.resolve()
    elif exigir and not (entrada and saida):
        raise ErroConfig(f"{caminho} nao existe. Rode `python main.py init` "
                         "ou informe --entrada e --saida.")

    if entrada:
        cfg.entrada = Path(entrada).resolve()
    if saida:
        cfg.saida = Path(saida).resolve()
    if jobs:
        cfg.jobs = jobs
    if cfg.overrides is None and cfg.entrada:
        cfg.overrides = procurar_overrides(cfg.entrada)
    if exigir:
        validar_caminhos(cfg.entrada, cfg.saida, raiz_ferramenta)
    return cfg


def validar_caminhos(entrada, saida, raiz_ferramenta=None):
    if not entrada:
        raise ErroConfig("diretorio de entrada nao definido (config.toml ou --entrada)")
    if not saida:
        raise ErroConfig("diretorio de saida nao definido (config.toml ou --saida)")
    if not Path(entrada).is_dir():
        raise ErroConfig(f"entrada nao encontrada: {entrada}")
    # Regra 1: nenhum comando escreve na entrada.
    if util.dentro_de(saida, entrada):
        raise ErroConfig(f"a saida ({saida}) nao pode ficar dentro da entrada ({entrada}): "
                         "a entrada e somente leitura")
    if raiz_ferramenta:
        for nome, p in (("entrada", entrada), ("saida", saida)):
            if util.dentro_de(p, raiz_ferramenta):
                raise ErroConfig(f"a {nome} ({p}) nao pode ficar dentro do diretorio da ferramenta: "
                                 "o acervo fica fora dela")


def procurar_overrides(entrada):
    """Sem caminho explicito: procura overrides*.toml na entrada e ao lado dela."""
    for d in (Path(entrada), Path(entrada).parent):
        achados = sorted(d.glob("overrides*.toml"))
        if len(achados) == 1:
            return achados[0].resolve()
        if len(achados) > 1:
            nomes = ", ".join(a.name for a in achados)
            raise ErroConfig(f"mais de um overrides*.toml em {d} ({nomes}); "
                             "defina [caminhos].overrides no config.toml")
    return None


def carregar_overrides(caminho, avisar=util.LOG.warning):
    """Devolve {id: {...}}. Erros de esquema abortam: override errado e decisao humana perdida."""
    if not caminho:
        return {}
    caminho = Path(caminho)
    if not caminho.exists():
        raise ErroConfig(f"overrides nao encontrado: {caminho}")
    try:
        dados = tomllib.loads(caminho.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise ErroConfig(f"{caminho}: TOML invalido — {e}")
    erros = []
    for id_, ov in dados.items():
        if not isinstance(ov, dict):
            erros.append(f"[{id_}] deveria ser uma tabela")
            continue
        aninhadas = [k for k, v in ov.items() if isinstance(v, dict) and k != "tabelas"]
        if aninhadas:
            erros.append(f"[{id_}.{aninhadas[0]}] virou subtabela: id com ponto precisa de aspas, "
                         f'ex.: ["{id_}.{aninhadas[0]}"]')
            continue
        for k in set(ov) - CHAVES_OVERRIDE:
            avisar(f"overrides [{id_}]: chave desconhecida '{k}' (ignorada)")
        if "rota" in ov and ov["rota"] not in ROTAS:
            erros.append(f"[{id_}] rota '{ov['rota']}' invalida (use {'/'.join(ROTAS)})")
        if "status" in ov and ov["status"] not in STATUS:
            erros.append(f"[{id_}] status '{ov['status']}' invalido (use {'/'.join(STATUS)})")
        if ov.get("formulas", "texto") not in ("texto", "latex"):
            erros.append(f"[{id_}] formulas '{ov['formulas']}' invalido (use texto/latex)")
        if set(ov.get("extras", [])) - set(EXTRAS):
            erros.append(f"[{id_}] extras {ov['extras']} invalidos (use {'/'.join(EXTRAS)})")
        if "idioma_ocr" in ov and not all(p.isalpha() and len(p) == 3
                                          for p in str(ov["idioma_ocr"]).split("+")):
            erros.append(f"[{id_}] idioma_ocr '{ov['idioma_ocr']}' invalido (ex.: 'por+eng')")
    if erros:
        raise ErroConfig(f"{caminho}:\n  " + "\n  ".join(erros))
    return dados


def carregar_perfil(raiz_ferramenta, nome, _vistos=None):
    """perfis/<nome>.toml, resolvendo `herda`. Listas do perfil-filho somam-se as do pai
    (remover_linhas, qa.bloquear); escalares do filho vencem."""
    _vistos = _vistos or []
    if nome in _vistos:
        raise ErroConfig(f"perfis: heranca circular em {' -> '.join(_vistos + [nome])}")
    caminho = Path(raiz_ferramenta) / "perfis" / f"{nome}.toml"
    if not caminho.exists():
        disponiveis = ", ".join(sorted(p.stem for p in caminho.parent.glob("*.toml")))
        raise ErroConfig(f"perfil '{nome}' nao existe (disponiveis: {disponiveis})")
    try:
        dados = tomllib.loads(caminho.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise ErroConfig(f"{caminho}: TOML invalido — {e}")
    if pai := dados.pop("herda", None):
        base = carregar_perfil(raiz_ferramenta, pai, _vistos + [nome])
        base["qa"] = {"bloquear": base.get("qa", {}).get("bloquear", [])
                      + dados.get("qa", {}).get("bloquear", [])}
        for lista in ("remover_linhas", "remover_trechos"):
            base[lista] = base.get(lista, []) + dados.get(lista, [])
        dados = {**base, **{k: v for k, v in dados.items()
                            if k not in ("qa", "remover_linhas", "remover_trechos")}}
    dados.setdefault("remover_linhas", [])
    dados.setdefault("remover_trechos", [])
    dados.setdefault("qa", {}).setdefault("bloquear", [])
    dados["nome"] = nome
    return dados


def _toml_str(v):
    v = str(v)
    # String literal ('...') dispensa escapar as barras invertidas dos caminhos do Windows.
    return f"'{v}'" if "'" not in v else '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'


def gerar_toml(entrada, saida, overrides, perfil, jobs):
    return f"""\
# config.toml - gerado por `python main.py init` em {datetime.date.today():%d/%m/%Y}. Nao versionar.
# Caminhos relativos sao resolvidos a partir deste arquivo.

[caminhos]
entrada   = {_toml_str(entrada)}   # acervo de PDFs; somente leitura para a ferramenta
saida     = {_toml_str(saida)}   # manifesto.csv, Markdown, CSV, relatorio de QA
overrides = {_toml_str(overrides or "")}   # decisoes curadas por documento ("" = nenhuma)

[execucao]
perfil    = "{perfil}"      # perfis/<perfil>.toml: regras de limpeza (etapa 5)
jobs      = {jobs}              # 0 = nucleos - 1
timeout   = 300            # segundos por chamada de ferramenta externa
extensoes = [".pdf"]
dispositivo = "auto"       # onde rodam os modelos do Docling: auto | cpu | cuda
                           # (auto usa a GPU quando ha uma; medido: 16x mais rapido)

[limiares]
disco_min_gb = 5           # o `doutor` avisa abaixo disso (Docling gera assets de imagem)
acuracia_min = 90          # etapa 4: tabela abaixo disso vai para revisao no QA

[ferramentas]
# Caminho explicito de executaveis fora do PATH, se precisar:
# tesseract = 'C:\\Program Files\\Tesseract-OCR\\tesseract.exe'
# qpdf      = 'C:\\Program Files\\qpdf\\bin\\qpdf.exe'
"""
