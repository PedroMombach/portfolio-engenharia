"""
main.py

Ponto de entrada: le os CSVs de bomba, define as curvas de sistema,
calcula as interseccoes (Q, H, Eta1, NPSHr) para cada par bomba-sistema,
imprime/salva a tabela consolidada e gera o grafico.

Para adicionar um novo caso de sistema (alem de Nom/Min/Max), basta
inserir mais uma SystemCurve(...) na lista `systems` abaixo -- o loop em
run_intersections() e o grafico ja cobrem N sistemas automaticamente.
"""

from pathlib import Path

from pump_intersect import PumpCurve, SystemCurve, run_intersections
from pump_plot import plot_curves


# --------------------------------------------------------------------------
# Configuracao
# --------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
CSV_DIR = BASE_DIR / "curvas_bombas"
OUTPUT_DIR = BASE_DIR / "outputs"
OUT_TABLE = OUTPUT_DIR / "intersecoes.csv"
OUT_PLOT = OUTPUT_DIR / "curvas_bombas.png"

Qnom = 1500  # L/s

# Curvas de sistema: [dG, AMT, NPSHd] em m.c.a.
# Para incluir mais casos, so adicionar mais SystemCurve(...) aqui.
systems = [
    SystemCurve(name="Nominal", dG=5.2, AMT=6.00, NPSHd=12.5),
    SystemCurve(name="Mínimo", dG=2.10, AMT=2.91, NPSHd=15.6),
    SystemCurve(name="Máximo", dG=7.6, AMT=8.71, NPSHd=12.5)
]

# Bombas: CSVs com colunas [Q, H, Eta1, NPSH]
pump_files = {
    "Pump1": CSV_DIR / "Pump1.csv",
    "Pump2": CSV_DIR / "Pump2.csv",
    "Pump3": CSV_DIR / "Pump3.csv",
}


# --------------------------------------------------------------------------
# Execucao
# --------------------------------------------------------------------------

def main():
    pumps = [PumpCurve.from_csv(path, name=name) for name, path in pump_files.items()]

    intersections_df = run_intersections(pumps, systems, Qnom)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(intersections_df.to_string(index=False))
    intersections_df.to_csv(OUT_TABLE, index=False)
    print(f"\nTabela salva em: {OUT_TABLE}")

    plot_curves(pumps, systems, Qnom, intersections_df, OUT_PLOT, scatter = True)
    print(f"Grafico salvo em: {OUT_PLOT}")


if __name__ == "__main__":
    main()
