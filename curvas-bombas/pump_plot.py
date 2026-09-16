"""
pump_plot.py

Modulo de plotagem: curvas de bomba, curvas de sistema e pontos de
interseccao. Separado de pump_intersect.py para manter calculo e
visualizacao independentes (o calculo nao depende de matplotlib).
"""

import numpy as np
import matplotlib
matplotlib.rcParams["figure.dpi"] = 600
from matplotlib import pyplot as plt

PUMP_COLORS = [
    "#56B4E9",  # azul claro (sky blue)
    "#D55E00",  # vermelho/terracota (vermillion)
    "#009E73",  # verde (bluish green)
    "#E69F00",  # laranja
    "#F0E442",  # amarelo
    "#0072B2",  # azul escuro (blue)
    "#CC79A7",  # rosa/magenta (reddish purple)
]

SYSTEM_LINESTYLES = ["--", "-.", ":", (0, (3, 1, 1, 1))]
SYSTEM_LINEWIDTH = 1
pump_legend_loc = "upper right"
system_legend_loc = "upper left"


def plot_curves(pumps, systems, Qnom, intersections_df, out_path,
                Qv_max=2000, Qv_points=1001, scatter = True):
    """Plota curvas H-Q de todas as bombas, todas as curvas de sistema
    (linha continua no dominio de Qv) e marca os pontos de interseccao.
 
    Parametros
    ----------
    pumps             : lista de PumpCurve
    systems           : lista de SystemCurve
    Qnom              : vazao nominal (parametrizacao das curvas de sistema)
    intersections_df  : DataFrame retornado por run_intersections()
    out_path          : caminho do arquivo de saida (.png)
    Qv_max, Qv_points : dominio/densidade usados para desenhar as curvas
                         de sistema como linha continua (independente do CSV)
    """
    fig, ax = plt.subplots()
 
    Qv = np.linspace(0, Qv_max, num=Qv_points)
 
    # curvas de bomba (dados discretos do CSV), cor conforme PUMP_COLORS
    pump_lines = []
    for idx, pump in enumerate(pumps):
        color = PUMP_COLORS[idx % len(PUMP_COLORS)]
        line, = ax.plot(pump.data["Q"], pump.data["H"], color=color,
                         label=f"{pump.name}")
        pump_lines.append(line)
 
    # curvas de sistema (continuas, funcao parametrica), sempre pretas,
    # linestyle conforme SYSTEM_LINESTYLES. Indexacao modular pura em
    # Python (nao np.resize): SYSTEM_LINESTYLES mistura strings ("--") com
    # tuplas de dash pattern, formato heterogeneo que np.resize nao aceita.
    system_lines = []
    for idx, system in enumerate(systems):
        ls = SYSTEM_LINESTYLES[idx % len(SYSTEM_LINESTYLES)]
        line, = ax.plot(Qv, system.H(Qv, Qnom), color="black", linestyle=ls,
                         linewidth=SYSTEM_LINEWIDTH, label=f"{system.name}")
        system_lines.append(line)
 
    # pontos de interseccao
    found = intersections_df[intersections_df["Encontrado"]]

    if scatter:
        ax.scatter(found["Q"], found["H"], color="black", zorder=5,
                   label="Interseccoes", marker = "x", s = 25, linewidths = 0.9)
 
    ax.set_xlabel("Q [L/s]")
    ax.set_ylabel("H [m.c.a.]")
    #ax.set_title("Curvas de bomba x sistema")
 
    # duas legendas independentes; add_artist preserva a primeira quando
    # a segunda e criada (por padrao so a ultima legend() sobreviveria)
    pump_legend = ax.legend(handles=pump_lines, loc=pump_legend_loc,
                             fontsize="small", title="Bombas")
    ax.add_artist(pump_legend)
    ax.legend(handles=system_lines, loc=system_legend_loc,
              fontsize="small", title="Curvas de\nsistema")
    ax.grid(True)

    ax.set_xbound(lower = 500, upper = Qv_max)
    ax.set_ybound(lower = 0)
 
    fig.savefig(out_path)
    plt.close(fig)
 
