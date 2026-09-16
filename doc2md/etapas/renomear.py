"""Etapa 0b — renomear: aplica um de-para CSV sobre o acervo de entrada.

Aplica um mapa de nomes em CSV, sem embutir nomes de um acervo no codigo.
E o UNICO ponto da ferramenta que escreve na entrada, e por isso ele:
  - simula por padrao: sem --forcar, nada e movido;
  - grava sha256 de cada arquivo antes de mover, em renomeacao-log.csv, na saida;
  - recusa destino existente, destino fora da entrada e nome que mude de pasta para fora dela;
  - isola download incompleto (.crdownload e afins) em _descartar\\ em vez de apagar.

Colunas aceitas no CSV (cabecalho, em qualquer ordem; sinonimos entre parenteses):
    nome_atual (atual, de, origem)      obrigatoria
    nome_novo  (novo, para, destino)    obrigatoria
    pasta_origem  (subpasta_origem)     opcional
    pasta_destino (subpasta_destino)    opcional
O nome pode trazer a subpasta embutida ("normas/exemplo.pdf").
"""
import csv
from pathlib import Path

from etapas import higiene
from nucleo import util
from nucleo.config import ErroConfig

VERSAO = 1

SINONIMOS = {
    "nome_atual": ("nome_atual", "atual", "de", "origem", "nomeatual"),
    "nome_novo": ("nome_novo", "novo", "para", "destino", "nomenovo"),
    "pasta_origem": ("pasta_origem", "subpasta_origem", "pastaorigem"),
    "pasta_destino": ("pasta_destino", "subpasta_destino", "pastadestino"),
}


class ErroDePara(ErroConfig):
    """Erro de uso: o main ja o trata e devolve codigo 2."""


def ler_depara(caminho):
    """Devolve [(relativo_origem, relativo_destino)] a partir do CSV."""
    caminho = Path(caminho)
    if not caminho.exists():
        raise ErroDePara(f"de-para nao encontrado: {caminho}")
    texto = caminho.read_text(encoding="utf-8-sig")
    amostra = texto[:4096]
    try:
        dialeto = csv.Sniffer().sniff(amostra, delimiters=",;\t")
    except csv.Error:
        dialeto = csv.excel
    leitor = csv.DictReader(texto.splitlines(), dialect=dialeto)
    colunas = {c.strip().lower().replace(" ", "_"): c for c in (leitor.fieldnames or [])}
    def coluna(chave):
        return next((colunas[s] for s in SINONIMOS[chave] if s in colunas), None)
    c_atual, c_novo = coluna("nome_atual"), coluna("nome_novo")
    if not c_atual or not c_novo:
        raise ErroDePara(f"{caminho}: o CSV precisa das colunas de nome atual e nome novo "
                         f"(encontradas: {', '.join(colunas) or 'nenhuma'})")
    c_po, c_pd = coluna("pasta_origem"), coluna("pasta_destino")
    pares = []
    for n, linha in enumerate(leitor, 2):
        atual, novo = (linha.get(c_atual) or "").strip(), (linha.get(c_novo) or "").strip()
        if not atual or not novo:
            continue
        origem = Path((linha.get(c_po) or "").strip()) / atual if c_po and linha.get(c_po) else Path(atual)
        destino = Path((linha.get(c_pd) or "").strip()) / novo if c_pd and linha.get(c_pd) else Path(novo)
        if ".." in origem.parts or ".." in destino.parts or destino.is_absolute():
            raise ErroDePara(f"{caminho}:{n}: caminho invalido ({origem} -> {destino})")
        pares.append((origem, destino))
    if not pares:
        raise ErroDePara(f"{caminho}: nenhuma linha utilizavel")
    return pares


def planejar(entrada, pares):
    """[(status, origem_rel, destino_rel, sha256)] sem tocar em nada."""
    plano = []
    destinos = {}
    for origem_rel, destino_rel in pares:
        origem, destino = entrada / origem_rel, entrada / destino_rel
        sha = ""
        if origem_rel == destino_rel:
            status = "JA_NO_PADRAO"
        elif not origem.exists():
            status = "DESTINO_JA_EXISTE" if destino.exists() else "ORIGEM_AUSENTE"
        elif destino.exists():
            status = "DESTINO_JA_EXISTE"
        elif destino_rel in destinos:
            status = "DESTINO_DUPLICADO"
        else:
            status = "PRONTO"
            destinos[destino_rel] = origem_rel
            sha = util.sha256(origem)
        plano.append((status, origem_rel, destino_rel, sha))
    return plano


def aplicar(entrada, plano, manifesto=None):
    """Move o que esta PRONTO. Devolve o plano com o status final."""
    final = []
    for status, origem_rel, destino_rel, sha in plano:
        if status != "PRONTO":
            final.append((status, origem_rel, destino_rel, sha))
            continue
        origem, destino = entrada / origem_rel, entrada / destino_rel
        try:
            destino.parent.mkdir(parents=True, exist_ok=True)
            origem.replace(destino)
            status = "RENOMEADO"
            if manifesto is not None:
                _seguir_no_manifesto(manifesto, origem_rel, destino_rel, sha)
        except OSError as e:
            status = f"FALHOU: {e}"
        final.append((status, origem_rel, destino_rel, sha))
    return final


def _seguir_no_manifesto(manifesto, origem_rel, destino_rel, sha):
    """O id vem do nome do arquivo: renomear muda o id. A linha acompanha, e o que ja foi
    produzido com o id antigo volta a pendente (as saidas levam o id no nome)."""
    antigo = util.slug(Path(origem_rel).stem)
    novo = util.slug(Path(destino_rel).stem)
    linha = manifesto.linhas.get(antigo)
    if linha is None or antigo == novo:
        return
    if novo in manifesto.linhas:
        manifesto.remover(novo)
    linha = manifesto.renomear(antigo, novo)
    linha["arquivo_origem"] = Path(destino_rel).as_posix()
    linha["sha256_origem"] = sha or linha["sha256_origem"]
    manifesto.invalidar(linha, "ocr")
    manifesto.anotar(linha, "renomear", f"renomeado de {Path(origem_rel).name}")


def isolar_parciais(entrada, aplicar_de_fato):
    """Download interrompido nao e descartado: vai para _descartar\\."""
    achados = []
    for caminho in sorted(entrada.rglob("*")):
        if caminho.is_file() and caminho.suffix.lower() in higiene.PARCIAIS:
            destino = entrada / "_descartar" / caminho.name
            achados.append((caminho.relative_to(entrada), destino.relative_to(entrada)))
            if aplicar_de_fato:
                destino.parent.mkdir(parents=True, exist_ok=True)
                caminho.replace(destino)
    return achados


def gravar_log(caminho, plano, parciais):
    linhas = ["status,origem,destino,sha256_origem"]
    linhas += [f'"{s}","{o.as_posix()}","{d.as_posix()}",{h}' for s, o, d, h in plano]
    linhas += [f'"DOWNLOAD_PARCIAL","{o.as_posix()}","{d.as_posix()}",' for o, d in parciais]
    util.gravar_atomico(caminho, "\n".join(linhas) + "\n", encoding="utf-8-sig")
