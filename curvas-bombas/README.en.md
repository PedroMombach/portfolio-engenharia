# Pump curves and operating points

[Português](README.md) | **English**

A basic utility. Intersecting a few candidate pump curves with the system
curves (nominal, minimum and maximum) and producing the operating-point table
and chart is a frequent project task. This script does nothing beyond that: it
**standardises the task**, so the result always comes out in the same format
instead of a new spreadsheet for every study.

![Pump and system curves with operating points](outputs/curvas_bombas.png)

## Running

Requires [Anaconda](https://www.anaconda.com/download) or [Miniconda](https://docs.conda.io/projects/miniconda/). Open **Anaconda Prompt** from the Start menu, go to
this folder (`cd /d "path\to\this\folder"`) and run the commands below. The
first one is only needed the first time:

```bat
conda env create -f environment.yml
conda activate curvas-bombas
python main.py
```

The table is printed and saved to `outputs/intersecoes.csv`. The chart is
saved to `outputs/curvas_bombas.png`.

## Using your own data

- **Pumps:** one CSV per pump in `curvas_bombas/`, with columns `Q` (L/s),
  `H` (m), `Eta1` (%) and `NPSH` (m). This is the format exported by the
  [Curve Extractor](../extrator-de-curvas/README.en.md). Register each file in
  the `pump_files` dictionary in `main.py`.
- **Systems:** edit the `systems` list in `main.py`. Each curve is defined by
  its static head `dG` and total head `AMT` at the nominal flow `Qnom`:

  ```text
  H_system(Q) = dG + (AMT − dG) · (Q / Qnom)²
  ```

## What the script computes

For each pump × system pair, the script:

1. finds where the two curves cross;
2. computes the flow and head at that operating point;
3. interpolates efficiency and required NPSH there.

The `Encontrado` column says whether a crossing was found, and `Obs` flags
ambiguous cases.

Known limits, consistent with a utility:

- the crossing is solved on the segments between CSV points, so accuracy
  depends on point spacing;
- no extrapolation beyond the curve's flow range;
- with more than one crossing, the first one is used and a warning is added;
- gaps in the CSV (for example, NPSH not reported) become empty cells in the
  table;
- available NPSH (`NPSHd`) is only recorded; the cavitation check belongs to the
  [Pump selector](../seletor-bombas/README.en.md).

## Layout

```text
main.py             configuration and run
pump_intersect.py   curves, crossings and table
pump_plot.py        chart
curvas_bombas/      one CSV per pump
outputs/            example table and chart
```

The example curves are labelled only as Pump1, Pump2 and Pump3.

License: [MIT](LICENSE).
