# Doc2MD

[Português](README.md) | **English** · [Article](docs/article.en.md) · [Methods and measurements](docs/methods.en.md) · [Rights and privacy](docs/rights-and-privacy.en.md)

Converts a library of **PDF standards, manuals and technical literature** into
Markdown that an AI can query. The Markdown keeps a reference to the source
page, and each document comes with metadata, CSV tables and a quality report.
Command names and console messages are in Portuguese.

The core idea is **not to turn an uncertain reading into text that looks like
a trustworthy source**. A figure without axes, a table cell under the wrong
column or an equation with a misplaced subscript still look convincing after
conversion. So Doc2MD keeps the evidence (page crop and element position)
alongside the extracted text. That lets interpretation happen later, in the
context of a real question. The [article](docs/article.en.md) explains how
that decision was reached.

## Running

Requires [Anaconda](https://www.anaconda.com/download) or [Miniconda](https://docs.conda.io/projects/miniconda/). Use **Anaconda PowerShell Prompt** (Start
menu), because the installer is a PowerShell script. Go to this folder and run:

```powershell
.\instalar.ps1                 # creates the 'doc2md' environment and OCR language data
conda activate doc2md
python main.py doutor          # checks that all dependencies are present
python main.py init            # asks for the PDF folder and the output folder
python main.py tudo            # runs the full pipeline
```

Notes:

- **GPU:** with a compatible NVIDIA card, use `.\instalar.ps1 -Gpu`. CPU also
  works, just more slowly.
- **Models:** on first conversion, Docling downloads its models. After that,
  processing runs offline.
- **Time and disk:** large libraries take hours and use a few GB. The output
  folder must be outside the input folder.
- **No prompts:** copy [config.example.toml](config.example.toml) to
  `config.toml`, edit the paths and run `python main.py tudo`.

The final Markdown is written to `<output>/corpus/`. The output folder also
holds:

- `manifesto.csv`, with each document's state at each stage;
- `relatorio-qa.md`, with the quality verdict and its reasons.

## How it works

| Stage | What it does |
| --- | --- |
| `inventariar` | Computes the hash, checks integrity and triages each PDF: native text, text with dense tables, scan, corrupted text layer, or mixed. |
| `ocr` | Runs OCR (OCRmyPDF/Tesseract) only where triage calls for it. |
| `converter` | Docling produces the Markdown, a JSON file with every block's position, and the images. |
| `tabelas` | Extracts requested tables to CSV. |
| `limpar` | Rejoins hyphenation and turns numbered items into headings. |
| `metadados` | Adds a YAML header and page anchors `<!-- p.N -->`. |
| `qa` | Checks text coverage, items, tables, anchors and blocked data. |

Some properties of the pipeline:

- **Resumable:** the manifest skips completed stages and invalidates later
  stages when something changes.
- **Isolated failures:** one failed document does not stop the others.
- **Empty output is a failure:** an empty result is never treated as success.
- **Input untouched:** the input PDFs are never modified.

Triage only **suggests** a route. A human decision recorded in an
[overrides](overrides.example.toml) file takes precedence.

**Formulas** are output as **page crop + extracted text**, flagged as
unreliable for calculation. **Figures** stay as images. Requested tables get a
CSV with a page reference.

## Limits

- **Automated QA catches gross losses**, but **does not measure correctness**
  of figures, tables, OCR or formulas. Visual checking remains a human task.
- **The source itself can be wrong**, and no conversion fixes that. Check the
  image, units and context before using a value in a calculation.
- **It is not an anonymiser.** The public profile flags Brazilian personal tax
  numbers (CPF) in the text. Read the
  [rights and privacy note](docs/rights-and-privacy.en.md) before sharing
  results.

This repository contains code, an example configuration and tests with a
synthetic PDF. It **does not include** the documents of the development
library or their conversion results.

Tests: `python -m unittest discover -s tests -v`.

Code licence: [MIT](LICENSE). The documents you convert and the dependencies
you install have their own rights and licences.
