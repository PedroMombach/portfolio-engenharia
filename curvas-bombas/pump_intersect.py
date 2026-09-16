"""
pump_intersect.py

Modulo de calculo: interseccao entre curvas de bomba (Q,H) e curvas de
sistema (H = f(Q)), com interpolacao de Eta1 e NPSHr no ponto de operacao.

Dependencias: pandas, numpy, shapely
"""

from dataclasses import dataclass
import numpy as np
import pandas as pd
from shapely.geometry import LineString


# --------------------------------------------------------------------------
# Estruturas de dados
# --------------------------------------------------------------------------

@dataclass
class SystemCurve:
    """Curva de sistema parametrizada por dG, AMT e NPSHd em Q nominal.

    H(Q) = dG + (AMT - dG) * (Q / Qnom)**2

    Atributos
    ---------
    name   : identificador da curva (ex.: "Nom", "Min", "Max")
    dG     : desnivel geometrico [m.c.a.]
    AMT    : altura manometrica total no ponto nominal [m.c.a.]
    NPSHd  : NPSH disponivel no ponto nominal [m.c.a.]
    """
    name: str
    dG: float
    AMT: float
    NPSHd: float

    def H(self, Qv, Qnom):
        """Altura de sistema H(Q) para um array (ou escalar) de vazao Qv."""
        Qv = np.asarray(Qv, dtype=float)
        return self.dG + (self.AMT - self.dG) * (Qv / Qnom) ** 2


@dataclass
class PumpCurve:
    """Curva de bomba lida de CSV, colunas [Q, H, Eta1, NPSH].

    Atributos
    ---------
    name : identificador da bomba (ex.: "Pump1")
    data : DataFrame com colunas Q, H, Eta1, NPSH, ordenado por Q crescente
    """
    name: str
    data: pd.DataFrame

    @classmethod
    def from_csv(cls, path, name=None):
        df = pd.read_csv(path, header=0)
        required = {"Q", "H", "Eta1", "NPSH"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(
                f"CSV '{path}' esta faltando as colunas {sorted(missing)}; "
                f"colunas encontradas: {list(df.columns)}"
            )
        df = df.sort_values("Q").reset_index(drop=True)
        return cls(name=name or path, data=df)


@dataclass
class IntersectionResult:
    """Resultado de uma interseccao bomba x sistema."""
    pump: str
    system: str
    Q: float
    H: float
    Eta1: float
    NPSHr: float
    found: bool = True
    note: str = ""


# --------------------------------------------------------------------------
# Interpolacao auxiliar
# --------------------------------------------------------------------------

def _interp_at(df: pd.DataFrame, col: str, Q_target: float) -> float:
    """Interpola linearmente df[col] em Q = Q_target, usando df['Q'] como x.

    Assume df ja ordenado por Q crescente (garantido em PumpCurve.from_csv).
    np.interp faz clamp nas bordas (nao extrapola); como Q_target sempre
    vem de dentro do intervalo [Q.min(), Q.max()] por construcao do
    algoritmo de interseccao, isso nao chega a ser exercitado na pratica.
    """
    return float(np.interp(Q_target, df["Q"], df[col]))


# --------------------------------------------------------------------------
# Calculo de interseccao
# --------------------------------------------------------------------------

def find_intersection(pump: PumpCurve, system: SystemCurve, Qnom: float) -> IntersectionResult:
    """Encontra o ponto de operacao (interseccao) entre uma curva de bomba
    e uma curva de sistema, e interpola Eta1/NPSHr nesse ponto.

    Metodo: mesmo principio do script original -- localiza o segmento onde
    o sinal de (H_bomba - H_sistema) muda, monta um LineString local para
    cada curva nesse segmento e usa shapely para achar o ponto exato de
    cruzamento (interpolacao linear entre os dois pontos do CSV que
    cercam a raiz). So funciona corretamente quando ha exatamente UM
    cruzamento no intervalo de Q do CSV da bomba. Em caso de multiplas
    mudancas de sinal, retorna a primeira e registra um aviso.
    """
    Q = pump.data["Q"].to_numpy()
    H = pump.data["H"].to_numpy()

    Hsys = system.H(Q, Qnom)
    deltas = np.sign(H - Hsys)

    change_idx = np.where(deltas[1:] != deltas[:-1])[0]

    if len(change_idx) == 0:
        return IntersectionResult(
            pump=pump.name, system=system.name,
            Q=np.nan, H=np.nan, Eta1=np.nan, NPSHr=np.nan,
            found=False,
            note="Nenhum cruzamento encontrado no intervalo de Q do CSV "
                 "(curva de bomba nao cruza a curva de sistema).",
        )

    if len(change_idx) > 1:
        # Documentado como premissa do usuario (nao ocorre no caso de uso
        # atual), mas mantemos o aviso caso os dados mudem no futuro.
        note = (
            f"{len(change_idx)} cruzamentos detectados; retornando apenas "
            f"o primeiro (Q={Q[change_idx[0]]:.1f}). Revise os dados de "
            f"entrada se isso for inesperado."
        )
    else:
        note = ""

    i = change_idx[0]

    retaSys = LineString([(Q[i], Hsys[i]), (Q[i + 1], Hsys[i + 1])])
    retaPump = LineString([(Q[i], H[i]), (Q[i + 1], H[i + 1])])

    point = retaSys.intersection(retaPump)

    if point.is_empty:
        return IntersectionResult(
            pump=pump.name, system=system.name,
            Q=np.nan, H=np.nan, Eta1=np.nan, NPSHr=np.nan,
            found=False,
            note="Segmentos com mudanca de sinal nao produziram interseccao "
                 "geometrica valida (verificar dados de entrada).",
        )

    Q_int, H_int = point.x, point.y

    eta1_int = _interp_at(pump.data, "Eta1", Q_int)
    npshr_int = _interp_at(pump.data, "NPSH", Q_int)

    return IntersectionResult(
        pump=pump.name, system=system.name,
        Q=Q_int, H=H_int, Eta1=eta1_int, NPSHr=npshr_int,
        found=True, note=note,
    )


def run_intersections(pumps, systems, Qnom) -> pd.DataFrame:
    """Roda find_intersection para todo par (bomba, sistema) e retorna
    uma tabela consolidada.

    Parametros
    ----------
    pumps   : lista de PumpCurve
    systems : lista de SystemCurve (2, 3 ou N -- Nom/Min/Max/o-que-vier)
    Qnom    : vazao nominal usada na parametrizacao de SystemCurve.H

    Retorna
    -------
    DataFrame com colunas: Bomba, Sistema, Q, H, Eta1, NPSHr, Encontrado, Obs

    Este loop duplo e o ponto de extensao para novos casos de sistema:
    basta adicionar mais SystemCurve() a lista `systems` (ver main.py).
    """
    rows = []
    for pump in pumps:
        for system in systems:
            r = find_intersection(pump, system, Qnom)
            rows.append({
                "Bomba": r.pump,
                "Sistema": r.system,
                "Q": r.Q,
                "H": r.H,
                "Eta1": r.Eta1,
                "NPSHr": r.NPSHr,
                "Encontrado": r.found,
                "Obs": r.note,
            })
    return pd.DataFrame(rows)
