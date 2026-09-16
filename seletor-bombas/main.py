"""Seletor de bombas — ponto de entrada.

Ajuste os parâmetros abaixo e execute:  python main.py
"""

from pathlib import Path

from pump_selector import SelectionCriteria, run_cases

ROOT = Path(__file__).resolve().parent

# --- Arquivos ---------------------------------------------------------------
DATABASE = ROOT / "DB" / "PumpDatabase.xlsx"    # banco de bombas (sintético)
INPUTS = ROOT / "ExampleInputs.xlsx"            # casos a selecionar (aba Cases)
TEMPLATE = ROOT / "TemplateSaida.xlsx"          # modelo do relatório
OUTPUT_DIR = ROOT / "outputs"

# --- Execução ---------------------------------------------------------------
CASE = None   # None = todos | 1, 2, ... = posição | "nome" = nome exato
MODE = None   # None = modo da planilha | "manual" | "abacus" | "optimize"

# --- Critérios de aceitação -------------------------------------------------
CRITERIA = SelectionCriteria(
    min_frequency_hz=30.0,
    max_frequency_hz=60.0,
    min_motor_margin=0.05,             # folga mínima de potência do motor
    min_npsh_absolute_margin_m=0.6,    # NPSHd - NPSHr >= 0,6 m
    min_npsh_ratio=1.25,               # NPSHd / NPSHr >= 1,25
    missing_npsh_policy="allow_with_warning",   # ou "reject"
)

if __name__ == "__main__":
    run_cases(DATABASE, INPUTS, TEMPLATE, OUTPUT_DIR, CASE, MODE, CRITERIA)
