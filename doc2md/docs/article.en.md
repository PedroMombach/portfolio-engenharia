# Converting a technical library for AI without turning errors into "facts"

**Doc2MD, a case study** · September 2026 · [Português](artigo.md) · [Methods and measurements](methods.en.md)

## Why this project exists

In my experience, generative AI as it comes out of the box still does not
produce good engineering documents and procedures. Three things are missing:

- level of detail;
- domain terminology;
- judgement on how to approach each problem.

Getting there requires better context management: giving the AI the right
technical base at the right moment.

Doc2MD handles the first part. It converts a library of PDF standards,
manuals and technical literature into Markdown, the raw format that feeds that
base. The project writes no specifications itself; it prepares the material
those specifications will rest on.

The development library covered **hydromechanical equipment**: gates, trash
racks, valves and penstocks. Its core alone was about **3,000 pages** (3,758 in
the final record, across 37 documents), of four kinds:

- hand-fed scans;
- documents with handwritten notes;
- scans with no text layer;
- "ordinary" PDFs of varying quality.

One constraint shaped the project from the start: conversion had to be
**affordable**. The goal was that someone with a basic AI subscription and a
mid-range laptop could process the whole library.

## Why an off-the-shelf converter was not enough

The first attempt used [MarkItDown](https://github.com/microsoft/markitdown).
In the trial run at the time, results were weak exactly where a standard
carries its technical content: **figures, equations and tables**. On one
standard, the tested configuration recognised no headings at all. On a
36-page scan, it returned an essentially empty file with no warning. These
results apply to that version and configuration; they are not an assessment
of the current tool.

The recurring pattern was this: **identifying an element without the
document's context does not work well**. Low resolution, specks and scribbles
in scanned documents feed straight into the extraction. After conversion, the
original information is gone and the error leaves no trace.

So the question changed. It was no longer "which converter is best?" but
"what must be preserved so that a later reading can still be checked?":

- **Figures and charts:** axes, scale, legend and the paragraph that sets the
  conditions of use.
- **Tables:** which header and unit each number belongs to.
- **Equations:** subscripts, fractions and symbols.

## The central decision

Doc2MD uses [Docling](https://github.com/docling-project/docling) for layout
analysis and OCRmyPDF/Tesseract for scanned documents. One rule governs how
each kind of element is handled:

> **When automatic extraction is not reliable enough to skip checking, the
> original evidence is kept alongside the result, not replaced by it.**

In practice, the pipeline works like this:

1. A cheap triage step separates PDFs with usable text, scans and mixed files,
   and OCR runs only where needed.
2. Each document becomes Markdown with page anchors (`<!-- p.N -->`) and
   metadata.
3. A JSON file records where every block sits on the page. With it, the export
   can be redone in seconds, without repeating layout analysis.
4. Selected tables are also written as CSV.
5. Figures stay as images linked from the text.
6. Formulas get the treatment described below.

## Formulas: why Doc2MD does not generate LaTeX

The library held **2,472 formulas** in 27 of the 37 documents. For about
**31 %** of them, the text the PDF provides comes with the symbols out of
reading order. An example from ABNT NBR 6123:

```text
Extracted text:     2 s s 4 d F C q π =
What the page shows: F = Cs · q · π d² / 4
```

Faced with this, Docling's default behaviour is to **drop** the formula and
leave only a `formula-not-decoded` comment. In a single document of the
library, that would have deleted 24 formulas without any warning.

Five approaches were tested on the **same 44 formulas** from four documents.
One was a clean native PDF; the other three were among the worst scans in the
library.

| Route | What it is |
| --- | --- |
| A | Docling's own formula enrichment |
| B | Image crop of the formula, using the position Docling already records |
| C | pix2tex (LaTeX-OCR) on the crops |
| D | dots.ocr, a 3-billion-parameter vision model, on the crops |
| E | Visual reading of the crops by a generative AI (14 of the 44) |

Paid services that send documents off-site were excluded without testing,
since they break the local-processing premise.

### Cost was not the deciding factor

| Route (laptop with a 6 GB RTX 3050) | Per formula | Whole library (estimated) |
| --- | --- | --- |
| A · Docling on CPU | 18–65 s | ~32 h |
| A · Docling on GPU | 1–4 s | ~2 h |
| C · pix2tex on CPU | 0.8–2.2 s | ~1 h |
| D · dots.ocr on GPU | 4–22 s | 3–15 h |
| **B · crop** | **0.02 s** | **~10 min** |

The GPU made Docling's models about 16 times faster. As a result, device
selection became a setting for the whole conversion. Running a vision model on
**full pages** was out of the question: measured on a cloud T4 GPU, it took more
than 3 minutes per page, which means over nine days for the library. Per crop,
the cost drops to seconds, because a vision model's cost grows with image size
and a crop has about 50 times fewer pixels than a page.

### Quality was

The real problem was that **the routes disagree with one another**, and the
error comes wrapped in well-formed LaTeX.

| Comparison | Identical transcriptions |
| --- | --- |
| A × C | 3 of 44 |
| A × D | 5 of 44 |
| C × D | 1 of 44 |
| All three | 1 of 44 |

The comparison is textual and penalises purely notational differences, so it
understates real agreement. Even so, no route can serve as a reference to
validate the others.

A case from DIN 4114-2, with the same image given to every route:

- A: `\omega_y = \frac{F \cdot \sigma_{z\upsilon}|}{S}`
- C: `o_{Y} = \frac{F \cdot o_{Y0}}{S}`
- D: `\omega_{\gamma} = \frac{F \cdot \sigma_{ZU}}{S}`
- E: `\omega_y = \frac{F \cdot \sigma_{zul}}{S}` (*zul* for *zulässig*:
  allowable stress)

The first three render nicely. All of them are wrong, and nothing in the
output says so.

### The error that settled it

In one scanned standard, the page shows the head-loss law for fully rough
turbulent flow:

```text
λ^(−1/2) = −2 · log( ε / (3.71 · D) )
```

This expression is the roughness term of the Colebrook-White equation. There
is a scan speck right after the coefficient, and the vision model read
**−2.1** in both configurations tested. The correct coefficient is 2. That
error changes the head-loss calculation for a penstock directly, and the
resulting LaTeX looked flawless.

The defect was only caught because the crop could be opened and compared with
the page. That is exactly what the adopted solution preserves.

The visual reading (route E) got these cases right through **domain
knowledge**, not sharper eyesight. It recognised the equation and its
coefficient, and knew that `zul` abbreviates *zulässig*. A specialised model
sees symbols inside a box, with no document around them. That reading was not
blind, covered only 14 formulas and cannot be automated. It explains why the
models fail; it is not a production route.

### The adopted solution

Scrambled text is obviously suspicious, so a reader checks it by reflex. A
plausible but wrong transcription looks trustworthy and enters the knowledge
base unchecked. For a library meant to support engineering products, the second kind of error is the costly one.

So every formula comes out in the Markdown like this:

```text
<!-- formula: recorte fiel da pagina; o texto abaixo e o do PDF, e a ordem dos simbolos pode estar trocada -->
![formula](../assets/<id>/formula-p007-01.png)

`text extracted from the PDF`
```

The output has four properties:

- **Full coverage:** all 2,472 formulas have a crop, including those in
  scanned documents.
- **Faithful:** the crop is the page itself, not a reading of it. This does
  not guarantee that the page is right, or that the crop captures the whole
  formula: in poor scans, a formula can come out in pieces.
- **Machine-readable flag:** the comment lets the next stage decide what to do,
  including sending the crop to a vision model **at query time**, together
  with the surrounding paragraph.
- **Reversible decision:** every formula's position is stored, so a different
  output does not require reconverting the library.

## When the error is in the source

Not every error comes from conversion. In the first equation of API 421 (1990
edition), a minus sign between the densities is missing. As printed, the
equation multiplies the densities instead of subtracting them. Two things
expose the problem:

- a dimensional check;
- cross-reading the equation against the paragraph that introduces it and the
  standard's technical appendix, where it appears in the correct form.

Better OCR would transcribe a misprinted equation more faithfully, but would
not make it correct. That kind of check needs the whole document, which is one
more reason to keep the evidence rather than a frozen transcription.

## What the project delivers, and what it does not

Even with proper context, generative AI still makes mistakes when consuming the
library. It makes far fewer than with the alternatives tested, and they are
manageable: critical documents can be routed to better extraction formats.

Doc2MD **does not eliminate** the risk of wrong conversions. It reduces it
substantially and, above all, makes errors **visible** instead of hiding them
behind well-formatted output. Human inspection somewhere in the workflow is
still needed. That is a conclusion of the project, not a to-do for the next
version.

---

The standards mentioned are cited by identification only. The short excerpts
are used as examples for discussion. No document from the library is
distributed with this repository; see [rights and privacy](rights-and-privacy.en.md).
