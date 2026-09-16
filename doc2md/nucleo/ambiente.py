"""Dependencias externas: localizar executaveis e conferir o ambiente (comando `doutor`).

O `doutor` existe para o pipeline nao morrer na pagina 200: ele confere antes e diz
exatamente o que fazer quando algo falta.
"""
import functools
import glob
import importlib.metadata
import importlib.util
import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from . import util

_CONFIGURADOS = {}

# Onde os instaladores do Windows costumam deixar o que nao entra no PATH.
LOCAIS_WINDOWS = {
    "tesseract": [r"%ProgramFiles%\Tesseract-OCR\tesseract.exe",
                  r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"],
    "qpdf": [r"%ProgramFiles%\qpdf*\bin\qpdf.exe"],
}

POPPLER = ("pdftotext", "pdfinfo", "pdfimages", "pdffonts")
# A versao 24.04 reproduz as metricas do estudo de calibracao descrito em docs/metodologia.md.
# Outras versoes podem alterar contagens de caracteres e tokens; confira a rota sugerida.
POPPLER_CALIBRADO = "24.04"
IDIOMAS_TESSERACT = ("eng", "por", "deu")

# modulo -> (distribuicao pip, comandos que dependem dele)
MODULOS = {
    "docling": ("docling", ("converter",)),
    "ocrmypdf": ("ocrmypdf", ("ocr",)),
    "pypdfium2": ("pypdfium2", ("ocr",)),
    "camelot": ("camelot-py", ("tabelas",)),
    "pdfplumber": ("pdfplumber", ("tabelas",)),
    "yaml": ("pyyaml", ("metadados",)),
    "jiwer": ("jiwer", ("qa",)),
}


def configurar(ferramentas):
    _CONFIGURADOS.clear()
    _CONFIGURADOS.update(ferramentas or {})
    localizar.cache_clear()


@functools.lru_cache(maxsize=None)
def localizar(nome):
    """Caminho do executavel, ou None. Ordem: config.toml > bin do ambiente conda
    (mesmo sem `conda activate`) > PATH > locais usuais do Windows."""
    if nome in _CONFIGURADOS:
        p = Path(_CONFIGURADOS[nome])
        return str(p) if p.exists() else None
    for d in (Path(sys.prefix) / "Library" / "bin", Path(sys.prefix) / "Scripts"):
        achado = shutil.which(nome, path=str(d))
        if achado:
            return achado
    achado = shutil.which(nome)
    if achado:
        return achado
    for padrao in LOCAIS_WINDOWS.get(nome, []):
        achados = sorted(glob.glob(os.path.expandvars(padrao)), reverse=True)
        if achados:
            return achados[0]
    return None


def exe(nome):
    """Para montar a linha de comando: o caminho encontrado, ou o nome puro (o erro de
    'executavel nao encontrado' sai com o nome certo)."""
    return localizar(nome) or nome


def tessdata():
    """Diretorio dos .traineddata. O Tesseract so o encontra sozinho quando TESSDATA_PREFIX esta
    definido — o que, num ambiente conda, depende de `conda activate`. Aqui ele e deduzido do
    caminho do executavel, para a ferramenta funcionar tambem chamada pelo python do ambiente."""
    if (p := os.environ.get("TESSDATA_PREFIX")) and Path(p).is_dir():
        return Path(p)
    caminho = localizar("tesseract")
    if not caminho:
        return None
    bin_dir = Path(caminho).parent
    candidatos = [c for c in (bin_dir.parent.parent / "share" / "tessdata",  # conda: <env>/share/...
                              bin_dir.parent / "share" / "tessdata",   # conda: <env>/Library/share/...
                              bin_dir / "tessdata",                    # ...\Tesseract-OCR\tessdata
                              bin_dir.parent / "tessdata") if c.is_dir()]
    # O Tesseract precisa dos idiomas E do diretorio `configs` no MESMO lugar; o pacote
    # conda-forge do Windows separa os dois, e ai `-l por` funciona mas a saida `tsv`/`pdf`
    # morre com TesseractConfigError. Prefira o diretorio completo.
    completo = [c for c in candidatos if any(c.glob("*.traineddata")) and (c / "configs").is_dir()]
    com_idioma = [c for c in candidatos if any(c.glob("*.traineddata"))]
    return next(iter(completo or com_idioma or candidatos), None)


def preparar_ocr():
    """Deixa TESSDATA_PREFIX no ambiente dos subprocessos (tesseract, ocrmypdf)."""
    if not os.environ.get("TESSDATA_PREFIX") and (d := tessdata()):
        os.environ["TESSDATA_PREFIX"] = str(d)
    return os.environ.get("TESSDATA_PREFIX")


def ambiente_conda():
    return os.environ.get("CONDA_DEFAULT_ENV") or Path(sys.prefix).name


# --- checagens ------------------------------------------------------------------------------

@dataclass
class Checagem:
    nome: str
    estado: str          # ok | aviso | falta
    detalhe: str
    correcao: str = ""
    comandos: tuple = ()  # comandos bloqueados quando estado == falta


def _versao(nome, *args):
    caminho = localizar(nome)
    if not caminho:
        return None, None
    try:
        r = util.executar([caminho, *args], timeout=30)
    except util.ErroExecucao as e:
        return caminho, f"erro: {e}"
    texto = (r.saida + "\n" + r.erro).strip()
    return caminho, texto


def _poppler():
    out = []
    for nome in POPPLER:
        caminho, texto = _versao(nome, "-v")
        if not caminho:
            out.append(Checagem(nome, "falta", "nao encontrado no PATH",
                                "conda install -c conda-forge poppler", ("inventariar", "qa")))
            continue
        m = re.search(r"version\s+([\d.]+)", texto or "")
        versao = m.group(1) if m else "?"
        if versao.startswith(POPPLER_CALIBRADO):
            out.append(Checagem(nome, "ok", f"poppler {versao}  ({caminho})"))
        else:
            out.append(Checagem(nome, "aviso", f"poppler {versao}  ({caminho})",
                                f"a triagem foi calibrada com poppler {POPPLER_CALIBRADO}; outra versao "
                                f"muda as metricas: conda install -c conda-forge poppler={POPPLER_CALIBRADO}"))
    return out


def _qpdf():
    caminho, texto = _versao("qpdf", "--version")
    if caminho:
        m = re.search(r"version\s+([\d.]+)", texto or "")
        return Checagem("qpdf", "ok", f"{m.group(1) if m else '?'}  ({caminho})")
    if importlib.util.find_spec("pikepdf"):
        return Checagem("qpdf", "aviso", "nao encontrado; integridade sera conferida pelo pikepdf",
                        "conda install -c conda-forge qpdf")
    return Checagem("qpdf", "aviso",
                    "nao encontrado (nem pikepdf): coluna `integridade` ficara 'nao_verificado'",
                    "conda install -c conda-forge qpdf")


def _tesseract():
    preparar_ocr()
    caminho, texto = _versao("tesseract", "--version")
    if not caminho:
        return [Checagem("tesseract", "falta", "nao encontrado",
                         "winget install -e --id UB-Mannheim.TesseractOCR  "
                         "(depois abra um terminal novo, ou defina [ferramentas].tesseract no config.toml)",
                         ("ocr",))]
    m = re.search(r"tesseract\s+v?(\d+)\.(\d+)(?:\.(\d+))?", texto or "", re.I)
    if not m:
        return [Checagem("tesseract", "falta", f"versao ilegivel: {(texto or '')[:60]!r}",
                         "reinstale: winget install -e --id UB-Mannheim.TesseractOCR", ("ocr",))]
    versao = ".".join(g for g in m.groups() if g)
    out = [Checagem("tesseract", "ok" if int(m.group(1)) >= 5 else "falta",
                    f"{versao}  ({caminho})",
                    "" if int(m.group(1)) >= 5 else
                    "precisa >= 5.0: winget upgrade -e --id UB-Mannheim.TesseractOCR", ("ocr",))]
    try:
        r = util.executar([caminho, "--list-langs"], timeout=30)
        texto = r.saida + "\n" + r.erro
    except util.ErroExecucao as e:
        texto = f"erro: {e}"
    langs = {l.strip() for l in texto.splitlines()[1:] if l.strip()}
    pasta = tessdata() or re.search(r'in "([^"]+)"', texto)
    pasta = (str(pasta) if isinstance(pasta, Path)
             else (pasta.group(1).rstrip("/\\") if pasta else r"C:\Program Files\Tesseract-OCR\tessdata"))
    faltam = [l for l in IDIOMAS_TESSERACT if l not in langs]
    if faltam:
        arqs = ", ".join(f"{l}.traineddata" for l in faltam)
        obrigatorio = "eng" in faltam
        out.append(Checagem("idiomas OCR", "falta" if obrigatorio else "aviso",
                            f"disponiveis: {', '.join(sorted(langs)) or '(nenhum)'}; "
                            f"faltam: {', '.join(faltam)}",
                            f"baixe {arqs} de https://github.com/tesseract-ocr/tessdata "
                            f"para {pasta} se esses idiomas forem usados",
                            ("ocr",) if obrigatorio else ()))
    else:
        out.append(Checagem("idiomas OCR", "ok", ", ".join(IDIOMAS_TESSERACT)))
    return out


def _modulos():
    out = []
    for mod, (dist, comandos) in MODULOS.items():
        if not importlib.util.find_spec(mod):
            out.append(Checagem(mod, "falta", "modulo Python ausente", f"pip install {dist}", comandos))
            continue
        try:
            v = importlib.metadata.version(dist)
        except importlib.metadata.PackageNotFoundError:
            v = "?"
        out.append(Checagem(mod, "ok", v))
    return out


def _python():
    v = sys.version_info
    env = ambiente_conda()
    detalhe = f"{v.major}.{v.minor}.{v.micro}  ({sys.executable}; ambiente: {env})"
    if v < (3, 11):
        return Checagem("python", "falta", detalhe,
                        "precisa >= 3.11 (tomllib); crie um ambiente novo", ("todos",))
    return Checagem("python", "ok", detalhe)


def _gpu(cfg):
    """A GPU nao e obrigatoria, mas muda a ordem de grandeza: medido, 16x nos modelos do Docling.
    Sem ela o `dispositivo = auto` cai para CPU, e o pipeline so fica lento."""
    if not importlib.util.find_spec("torch"):
        return Checagem("gpu", "aviso", "torch ausente: o `converter` nao roda", "pip install -r requirements.txt")
    import torch
    escolhido = (cfg.dispositivo if cfg else "auto")
    if torch.cuda.is_available():
        nome = torch.cuda.get_device_name(0)
        vram = torch.cuda.get_device_properties(0).total_mem / 1e9 if hasattr(
            torch.cuda.get_device_properties(0), "total_mem") else \
            torch.cuda.get_device_properties(0).total_memory / 1e9
        return Checagem("gpu", "ok", f"{nome}, {vram:.1f} GB, torch {torch.__version__} "
                                     f"(dispositivo = {escolhido})")
    if escolhido == "cuda":
        return Checagem("gpu", "falta", f"dispositivo = cuda, mas torch {torch.__version__} nao ve GPU",
                        "instale o torch CUDA (requirements-gpu.txt) ou use dispositivo = auto",
                        ("converter",))
    return Checagem("gpu", "aviso", f"sem GPU; os modelos rodam em CPU (torch {torch.__version__})",
                    "com GPU o `converter` fica ~16x mais rapido: veja requirements-gpu.txt")


def _disco(saida, minimo_gb):
    if not saida:
        return Checagem("disco", "aviso", "saida nao configurada; espaco nao conferido",
                        "python main.py init")
    alvo = Path(saida)
    while not alvo.exists() and alvo != alvo.parent:
        alvo = alvo.parent
    livre = shutil.disk_usage(alvo).free / 1e9
    if livre < minimo_gb:
        return Checagem("disco", "aviso", f"{livre:.1f} GB livres em {alvo} (minimo {minimo_gb:g} GB)",
                        "libere espaco ou aponte a saida para outro disco")
    return Checagem("disco", "ok", f"{livre:.1f} GB livres em {alvo}")


def checar(cfg=None):
    """Todas as checagens, na ordem em que o pipeline precisa delas."""
    return [
        _python(),
        *_poppler(),
        _qpdf(),
        *_tesseract(),
        *_modulos(),
        _gpu(cfg),
        _disco(cfg.saida if cfg else None, cfg.disco_min_gb if cfg else 5.0),
    ]
