# Technical appendix: methods, measurements and limits

[Article](article.en.md) · [Português](metodologia.md)

This appendix reports **historical development records** from September 2026. The standards and books used in evaluation, their image crops and the associated overrides are not included in the public repository. Bundled synthetic tests check software behavior; they do not reproduce the measurements below.

## Collection and processing flow

The final record covers 37 documents and 3,758 pages. Triage had first been calibrated against 36 PDFs, before the last document was added. Each document has a row in `manifesto.csv` with a SHA-256 hash, integrity and triage diagnostics, effective route, stage states and versions, metrics and notes. A changed source, route or OCR language invalidates dependent stages. A document failure is recorded without stopping the batch.

| Route | Diagnosis | Processing |
| --- | --- | --- |
| A | Usable native text | Original PDF → Docling. |
| B | Dense native text or signs of tables | Original PDF → Docling; tables as requested. |
| C | Almost no pages with text | OCRmyPDF `--force-ocr`. |
| D | Corrupted text layer | OCRmyPDF `--force-ocr` on a working copy. |
| E | Mixed pages with and without text | OCRmyPDF `--redo-ocr`, with PDF-specific fallbacks. |
| F, extra | Tables required as structured data | Camelot → CSV with page, method, dimensions and score. |

Triage combines Poppler (`pdfinfo`, `pdftotext`, `pdfimages`, `pdffonts`), per-page text coverage, control characters, anomalous tokens and image coverage. The calibrated reference is **Poppler 24.04**. A recorded comparison with 26.09 changed character or token metrics for 7 of 36 PDFs. Routes are suggestions: poor but plausible legacy OCR may pass as native text. A human decision in `overrides.toml` takes precedence.

OCRmyPDF/Tesseract creates a working PDF for C–E; Docling reads that file with its own OCR disabled. Docling JSON retains item, page and bounding-box provenance. Markdown receives `<!-- p.N -->` anchors, with relative assets for figures and formulas. The table stage uses pages from JSON or a curated page range. Configurable profile rules adjust presentation; the final corpus gains YAML front matter. QA evaluates the corpus anew on each run rather than trusting an earlier verdict.

## Recorded acceptance cases

| Milestone | Evidence from the original trial | Design consequence |
| --- | --- | --- |
| M1, triage | 36 PDFs; one 36-page scan returned zero characters from `pdftotext`; a damaged text layer had a 0.236 fraction of control characters. | Distinguish missing text, damaged text and native text; empty output is never success. |
| M2, OCR | A textless scan needed searchable output; the damaged PDF's control-character fraction had to fall below 0.01. | Use `force` when the bad layer must be discarded. |
| M3, structure | Historical MarkItDown configuration returned zero headings for one reference standard; acceptance also required headings and a preserved Greek symbol. | Use Docling layout analysis and retain provenance JSON. This was one file, with no comparator version recorded. |
| M4, tables | On one reference table, Camelot `stream` gave **21 × 6**, reported score **100.0**; `lattice` gave **19 × 5**, score **99.57**. | Choose the table method per document. The score does not prove cell correctness. |
| M5, cleaning/metadata | Copy markings appeared in intermediate JSON as well as outside Markdown; every document needed page anchors. | Keep corpus, assets and state separate, and review every layer before sharing. The public edition does not include rules that strip restriction notices. |
| M6, QA | Deliberately deleting a numbered item had to reject the document. | Compare corpus with source text, plus anchors, coverage and requested tables. |
| M7, run from scratch | Two PDFs in a temporary collection passed through `doutor`, `init`, `renomear` and `tudo`. | Check fresh setup and resumable processing. |

The **95% coverage threshold** compares alphanumeric Markdown characters against text extracted from the PDF, discounting lines that a configured profile deliberately removes. It signals gross loss, not OCR accuracy or semantic correctness. A numbered item in the source but missing from the corpus rejects native routes A/B; it triggers review for OCR routes C–E, where OCR may corrupt the numbering itself. Mean OCR confidence below 85%, numbering gaps, low-score tables and suspect formulas also call for review. Visual inspection of three pages per document remains a human task.

## Formula trial

The final collection contained **2,472 formula blocks across 27 documents**. About **31%** had a textual sign of broken reading order (`=` missing or at the end). Docling's default export could replace blocks with `<!-- formula-not-decoded -->`. The alternative-method trial used the same **44 formulas from four documents**: one clean native-text PDF and three difficult scans. It compared Docling enrichment, pix2tex, dots.ocr and image crops; 14 formulas also received contextual visual reading, without blinding. This selection does not estimate a population error rate.

| Textual LaTeX comparison | Matching strings |
| --- | ---: |
| Docling × pix2tex | 3/44 (7%) |
| Docling × dots.ocr | 5/44 (11%) |
| pix2tex × dots.ocr | 1/44 (2%) |
| All three | 1/44 (2%) |

Equivalent syntax may reduce measured agreement; agreement does not prove correctness. Changing crop resolution altered many transcriptions, and a plausible reading changed a coefficient. The default therefore crops the image at Docling's bounding box and keeps extracted text marked as unsafe for calculation. The crop preserves what the page displays; it **does not prove** that the printed page is right or that the box covers the complete formula. Poor scans can yield adjacent fragments as separate images.

On the trial machine (RTX 3050 Laptop, 6 GB), Docling models ran about **16× faster on GPU** in a 100-formula experiment. Generating a crop took about **0.02 s per formula**, versus seconds for enrichment; these are observations for one hardware and configuration. Downstream, on-demand AI vision token or monetary cost **was not measured**. The architecture keeps that option available without imposing a potentially misleading automatic transcription on the whole collection.

## Public reproduction and limits

Run `python -m unittest discover -s tests -v` in this folder. Setting `DOC2MD_FULL_SMOKE=1` includes a full synthetic-PDF conversion. The historical trial requires licensed source documents that cannot be redistributed here. For a new comparison, record tool versions and options, authorized PDFs, sampled pages, human-review criteria and per-document metrics. The historical MarkItDown observation should not be treated as a result for its current version.

Tool references: [MarkItDown](https://github.com/microsoft/markitdown), [Docling](https://docling-project.github.io/docling/), [Camelot](https://camelot-py.readthedocs.io/) and [OCRmyPDF](https://ocrmypdf.readthedocs.io/). The measurements here come from the project record, not those documents.
