"""Gera docs/exemplo/catalogo-sintetico.pdf, um catálogo fictício para demonstrar o app.

Página 1: curvas H, η e NPSHr com aparência de scan (rotação, ruído e manchas),
          para demonstrar a calibração por três pontos.
Página 2: gráfico log-log vetorial de perda de carga, para demonstrar eixos logarítmicos.

Uso: python tools/gerar_catalogo_sintetico.py
Dependências: matplotlib, além das já usadas pelo app (numpy, Pillow, pypdfium2).
"""

import tempfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pypdfium2 as pdfium  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter  # noqa: E402

OUTPUT = Path(__file__).resolve().parents[1] / "docs" / "exemplo" / "catalogo-sintetico.pdf"
A4_IN = (8.27, 11.69)
DPI = 200
INK = "#1a1a1a"
SEED = 7

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 8,
    "axes.edgecolor": INK,
    "axes.linewidth": 0.8,
    "xtick.color": INK,
    "ytick.color": INK,
})


# --- elementos comuns ----------------------------------------------------------

def add_header(fig, title, subtitle):
    fig.text(0.08, 0.955, "HIDROVALE", fontsize=20, weight="bold", color=INK)
    fig.text(0.08, 0.94, "Bombas centrífugas · catálogo técnico fictício para demonstração",
             fontsize=7.5, color="#555")
    fig.add_artist(plt.Line2D([0.08, 0.92], [0.932, 0.932], color=INK, lw=1.2))
    fig.text(0.08, 0.905, title, fontsize=13, weight="bold", color=INK)
    fig.text(0.08, 0.89, subtitle, fontsize=8, color="#333")
    fig.text(0.08, 0.03, "Documento sintético. Marca, modelos e valores são fictícios.",
             fontsize=6.5, color="#777")


def style_linear_axis(ax, ylim, ylabel, show_x):
    ax.set_xlim(0, 35)
    ax.set_ylim(*ylim)
    ax.set_ylabel(ylabel)
    ax.grid(True, which="major", color="#999", lw=0.5)
    ax.grid(True, which="minor", color="#ccc", lw=0.3)
    ax.minorticks_on()
    if show_x:
        ax.set_xlabel("Q  [L/s]")
    else:
        ax.set_xticklabels([])


# --- página 1: curvas de desempenho --------------------------------------------

def draw_performance_page(path):
    fig = plt.figure(figsize=A4_IN)
    add_header(fig, "HV-S04  ·  4 polos  ·  1750 rpm  ·  60 Hz",
               "Curvas características para água limpa a 20 °C")
    q = np.linspace(0, 32, 200)

    ax_h = fig.add_axes([0.12, 0.58, 0.78, 0.28])
    for ratio, label in ((1.00, "Ø 220"), (0.93, "Ø 205"), (0.86, "Ø 190")):
        qd = q[q <= 30 * ratio]
        head = 38 * ratio**2 - 0.021 * qd**2 / ratio**0.5 + 0.08 * qd * ratio
        ax_h.plot(qd, head, color=INK, lw=1.3)
        ax_h.text(qd[-1] + 0.3, head[-1], label, fontsize=7.5, va="center")
    style_linear_axis(ax_h, (0, 45), "H  [m]", show_x=False)

    ax_eta = fig.add_axes([0.12, 0.38, 0.78, 0.18])
    qe = q[q <= 30]
    ax_eta.plot(qe, 76 * (1 - ((qe - 19) / 19) ** 2), color=INK, lw=1.3)
    ax_eta.text(24, 72, "Ø 220", fontsize=7.5)
    style_linear_axis(ax_eta, (0, 90), "η  [%]", show_x=False)

    ax_npsh = fig.add_axes([0.12, 0.21, 0.78, 0.15])
    qn = q[(q >= 5) & (q <= 30)]
    ax_npsh.plot(qn, 1.2 + 0.0045 * qn**2, color=INK, lw=1.3)
    style_linear_axis(ax_npsh, (0, 6), "NPSHr  [m]", show_x=True)

    fig.text(0.12, 0.15, "Curvas típicas; valores ilustrativos.", fontsize=7, color="#333")
    fig.savefig(path, dpi=DPI)
    plt.close(fig)


def simulate_scan(png_path, pdf_path, rng):
    """Rotação leve, desfoque, ruído, manchas, sombra de borda e tom amarelado."""
    img = Image.open(png_path).convert("L")
    img = img.rotate(-1.8, resample=Image.BICUBIC, fillcolor=255)
    img = img.filter(ImageFilter.GaussianBlur(0.7))

    pixels = np.asarray(img).astype(float) + rng.normal(0, 9, (img.height, img.width))
    img = Image.fromarray(np.clip(pixels, 0, 255).astype("uint8"))

    draw = ImageDraw.Draw(img)
    for _ in range(90):
        x, y, r = rng.integers(0, img.width), rng.integers(0, img.height), rng.integers(1, 4)
        draw.ellipse([x, y, x + r, y + r], fill=int(rng.integers(40, 120)))

    pixels = np.asarray(img).astype(float)
    rows = np.linspace(0, 1, img.height)[:, None]
    cols = np.linspace(0, 1, img.width)[None, :]
    pixels *= 1 - 0.10 * np.exp(-cols / 0.03) - 0.06 * np.exp(-(1 - rows) / 0.02)

    rgb = np.stack([pixels, pixels * 0.985, pixels * 0.94], axis=-1)
    scan = Image.fromarray(np.clip(rgb, 0, 255).astype("uint8"))
    scan.save(pdf_path, resolution=DPI, quality=80)


# --- página 2: perda de carga em escala log-log --------------------------------

def head_loss_per_100m(q_lps, diameter_m, roughness_m=0.26e-3, viscosity=1.0e-6):
    """Darcy-Weisbach com fator de atrito de Swamee-Jain."""
    velocity = q_lps / 1000 / (np.pi * diameter_m**2 / 4)
    reynolds = velocity * diameter_m / viscosity
    friction = 0.25 / np.log10(roughness_m / (3.7 * diameter_m) + 5.74 / reynolds**0.9) ** 2
    return velocity, friction / diameter_m * velocity**2 / (2 * 9.80665) * 100


def draw_head_loss_page(path):
    fig = plt.figure(figsize=A4_IN)
    add_header(fig, "Perda de carga na tubulação de recalque",
               "Tubo de ferro fundido, ε = 0,26 mm, água a 20 °C  ·  escala logarítmica")
    ax = fig.add_axes([0.13, 0.22, 0.76, 0.62])

    for dn in (80, 100, 150, 200, 250):
        q = np.logspace(np.log10(0.5), np.log10(200), 300)
        velocity, loss = head_loss_per_100m(q, dn / 1000)
        valid = (velocity >= 0.3) & (velocity <= 3.5)
        ax.loglog(q[valid], loss[valid], color=INK, lw=1.2)
        ax.text(q[valid][-1] * 1.04, loss[valid][-1], f"DN {dn}", fontsize=7.5, va="center")

    comma = FuncFormatter(lambda value, _: f"{value:g}".replace(".", ","))
    ax.xaxis.set_major_formatter(comma)
    ax.yaxis.set_major_formatter(comma)
    ax.set_xlim(0.5, 300)
    ax.set_ylim(0.05, 50)
    ax.set_xlabel("Q  [L/s]")
    ax.set_ylabel("J  [m / 100 m]")
    ax.grid(True, which="both", color="#bbb", lw=0.4)

    fig.text(0.13, 0.15, "Curvas limitadas a velocidades entre 0,3 e 3,5 m/s.",
             fontsize=7, color="#333")
    fig.savefig(path)
    plt.close(fig)


# --- montagem -------------------------------------------------------------------

def main():
    rng = np.random.default_rng(SEED)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        draw_performance_page(tmp / "p1.png")
        simulate_scan(tmp / "p1.png", tmp / "p1.pdf", rng)
        draw_head_loss_page(tmp / "p2.pdf")

        document = pdfium.PdfDocument.new()
        for part in ("p1.pdf", "p2.pdf"):
            source = pdfium.PdfDocument(tmp / part)
            document.import_pages(source)
            source.close()
        document.save(OUTPUT)
        document.close()
    print(f"gerado: {OUTPUT}")


if __name__ == "__main__":
    main()
