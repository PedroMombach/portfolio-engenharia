"""manifesto.csv — o estado da ferramenta; uma linha por documento, no diretorio de saida.

Cada etapa le o manifesto, faz so o que falta e regrava. Idempotencia: uma etapa pula o
documento se estado_X == ok E a versao registrada da etapa e a atual. Mudanca de sha256 da
origem (detectada no `inventariar`) ou da rota/idioma efetivos invalida as etapas seguintes.
`--forcar` ignora tudo isso.

Colunas acrescentadas a mao pelo usuario sao preservadas ao regravar.
"""
import csv
import io
import threading
import time
from pathlib import Path

from . import util

NOME = "manifesto.csv"

ETAPAS = ("ocr", "estrutura", "tabelas", "limpeza", "metadados")
ESTADOS = ("pendente", "ok", "falhou", "pulado")

# Quem consome a saida de quem. Nao e a ordem do pipeline: `tabelas` gera CSV a partir do PDF e
# nao alimenta a limpeza, entao reextrair tabela nao obriga a refazer o Markdown.
DEPENDENTES = {
    "ocr": ("estrutura", "tabelas", "limpeza", "metadados"),
    "estrutura": ("tabelas", "limpeza", "metadados"),
    "tabelas": (),
    "limpeza": ("metadados",),
    "metadados": (),
}

DIAGNOSTICO = [
    "paginas", "produtor", "cripto", "pag_sem_texto", "pag_pobres", "frac_com_texto",
    "car_por_pag", "frac_ctrl", "frac_sujos", "frac_stopwords", "tokens", "cobertura_img",
    "ocr_embutido", "suspeita_ocr_legado", "revisar", "rota_sugerida",
]
METRICAS = ["conf_ocr_media", "cobertura_texto", "tabelas_extraidas", "itens_faltantes",
            "linhas_removidas", "qa"]

COLUNAS = [
    "id", "arquivo_origem", "mb", "sha256_origem", "integridade",   # etapa 0
    *DIAGNOSTICO,                                                   # etapa 1
    "rota_efetiva", "rotas_extras", "idioma_ocr", "status_doc",     # decisao (override > triagem)
    *[f"estado_{e}" for e in ETAPAS],                               # etapas 2-6
    *METRICAS,                                                      # etapa 7
    "versoes", "observacao",
]


class Manifesto:
    def __init__(self, saida):
        self.caminho = Path(saida) / NOME
        self.linhas = {}
        self.extras = []
        self._trava = threading.RLock()
        self._ultimo_salvamento = time.monotonic()

    @classmethod
    def carregar(cls, saida):
        m = cls(saida)
        if m.caminho.exists():
            with open(m.caminho, newline="", encoding="utf-8-sig") as f:
                leitor = csv.DictReader(f)
                m.extras = [c for c in (leitor.fieldnames or []) if c not in COLUNAS]
                for row in leitor:
                    linha = {c: (row.get(c) or "") for c in COLUNAS + m.extras}
                    m.linhas[linha["id"]] = linha
        return m

    # --- linhas -------------------------------------------------------------------------

    def nova(self, id_):
        linha = {c: "" for c in COLUNAS + self.extras}
        linha["id"] = id_
        for e in ETAPAS:
            linha[f"estado_{e}"] = "pendente"
        self.linhas[id_] = linha
        return linha

    def renomear(self, antigo, novo):
        linha = self.linhas.pop(antigo)
        linha["id"] = novo
        self.linhas[novo] = linha
        return linha

    def remover(self, id_):
        self.linhas.pop(id_, None)

    def filtrar(self, so_rota=None, so_doc=None):
        return [l for l in self.ordenadas()
                if (not so_doc or l["id"] == so_doc)
                and (not so_rota or l["rota_efetiva"] in so_rota)]

    def ordenadas(self):
        return sorted(self.linhas.values(), key=lambda l: (l["arquivo_origem"].lower(), l["id"]))

    # --- versoes e estados ------------------------------------------------------------------

    @staticmethod
    def _versoes(linha):
        return dict(p.split("=", 1) for p in linha["versoes"].split(";") if "=" in p)

    def versao(self, linha, etapa):
        v = self._versoes(linha).get(etapa)
        return int(v) if v and v.isdigit() else None

    def definir_versao(self, linha, etapa, versao):
        vs = self._versoes(linha)
        if versao is None:
            vs.pop(etapa, None)
        else:
            vs[etapa] = str(versao)
        linha["versoes"] = ";".join(f"{k}={v}" for k, v in vs.items())

    def precisa_rodar(self, linha, etapa, versao, forcar=False):
        return (forcar or linha[f"estado_{etapa}"] not in ("ok", "pulado")
                or self.versao(linha, etapa) != versao)

    def marcar(self, linha, etapa, estado, versao=None, motivo=""):
        assert estado in ESTADOS, estado
        with self._trava:
            linha[f"estado_{etapa}"] = estado
            self.definir_versao(linha, etapa, versao if estado in ("ok", "pulado") else None)
            self.anotar(linha, etapa, motivo)

    def invalidar_apos(self, linha, etapa, dependentes=None):
        """A etapa rodou de novo: quem consome a saida dela esta velho. Sem isso, reconverter um
        documento deixaria o Markdown limpo e o front-matter antigos marcados como 'ok'.
        `dependentes` permite a etapa dizer que refez menos do que o normal."""
        with self._trava:
            for dependente in (DEPENDENTES.get(etapa, ()) if dependentes is None else dependentes):
                linha[f"estado_{dependente}"] = "pendente"
                self.definir_versao(linha, dependente, None)
            linha["qa"] = ""   # o veredito sempre envelhece quando algo e refeito

    def invalidar(self, linha, desde, metricas=True):
        """Volta a 'pendente' a etapa `desde` e todas as seguintes; limpa as metricas de QA.
        desde='triagem' tambem apaga o diagnostico (o PDF de origem mudou)."""
        with self._trava:
            if desde == "triagem":
                for c in DIAGNOSTICO:
                    linha[c] = ""
                self.definir_versao(linha, "triagem", None)
                desde = ETAPAS[0]
            for e in ETAPAS[ETAPAS.index(desde):]:
                linha[f"estado_{e}"] = "pendente"
                self.definir_versao(linha, e, None)
            if metricas:
                for c in METRICAS:
                    linha[c] = ""

    @staticmethod
    def anotar(linha, etapa, msg=""):
        """Observacao e campo livre: texto manual e preservado; mensagens da ferramenta levam o
        prefixo [etapa] e sao substituidas quando a etapa roda de novo."""
        prefixo = f"[{etapa}]"
        partes = [p for p in linha["observacao"].split(" | ") if p and not p.startswith(prefixo)]
        if msg:
            partes.append(f"{prefixo} {msg}")
        linha["observacao"] = " | ".join(partes)

    # --- persistencia -----------------------------------------------------------------------

    def salvar_parcial(self, intervalo=5.0):
        """Checkpoint durante o lote, no maximo a cada `intervalo` s. Falhar aqui nao para o lote:
        o salvar() final e que precisa dar certo."""
        if time.monotonic() - self._ultimo_salvamento < intervalo:
            return
        try:
            self.salvar()
        except OSError as e:
            util.LOG.warning("checkpoint do manifesto falhou (%s); o lote segue", e)

    def salvar(self):
        self._ultimo_salvamento = time.monotonic()
        with self._trava:
            buf = io.StringIO()
            w = csv.DictWriter(buf, fieldnames=COLUNAS + self.extras, lineterminator="\r\n")
            w.writeheader()
            w.writerows(self.ordenadas())
            self.caminho.parent.mkdir(parents=True, exist_ok=True)
            # BOM: o Excel em pt-BR so abre os acentos certos com ele.
            util.gravar_atomico(self.caminho, buf.getvalue(), encoding="utf-8-sig")
