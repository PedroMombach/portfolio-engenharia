"""Compilação com pdflatex até as referências (sumário, links) estabilizarem."""

from __future__ import annotations

from pathlib import Path
import re
import shutil
import subprocess

from .entrada import InputError

MAX_PASSES = 4
TIMEOUT_S = 180
PDFLATEX_ARGS = (
    "-interaction=nonstopmode", "-halt-on-error", "-file-line-error",
    "-no-shell-escape", "main.tex",
)
UNRESOLVED = re.compile(
    r"undefined references|Reference .* undefined|Rerun to get|Label\(s\) may have changed"
)


def _auxiliary_state(work: Path) -> tuple[bytes, ...]:
    files = (work / f"main.{ext}" for ext in ("aux", "toc", "out"))
    return tuple(path.read_bytes() if path.exists() else b"" for path in files)


def compile_pdf(work: Path, executable=None) -> int:
    """Executa pdflatex em ``work`` e devolve o número de passagens."""
    executable = executable or shutil.which("pdflatex")
    if not executable:
        raise InputError(
            "pdflatex não encontrado no PATH. Instale MiKTeX/TeX Live ou use SOMENTE_TEX = True."
        )

    console_log = work / "pdflatex-console.log"
    previous = None
    for attempt in range(1, MAX_PASSES + 1):
        command = [str(executable), *PDFLATEX_ARGS]
        try:
            process = subprocess.run(
                command, cwd=work, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, timeout=TIMEOUT_S,
            )
        except subprocess.TimeoutExpired as exc:
            console_log.write_bytes(exc.stdout or b"")
            raise InputError(
                f"pdflatex excedeu {TIMEOUT_S} segundos. Consulte {console_log}"
            ) from exc

        with console_log.open("ab" if attempt > 1 else "wb") as log:
            log.write(process.stdout)
        if process.returncode:
            raise InputError(
                f"pdflatex falhou (passagem {attempt}). "
                f"Consulte {console_log} e {work / 'main.log'}"
            )

        state = _auxiliary_state(work)
        latex_log = (work / "main.log").read_text(encoding="utf-8", errors="replace")
        if state == previous and not UNRESOLVED.search(latex_log):
            shutil.copy2(work / "main.pdf", work.parent / "main.pdf")
            return attempt
        previous = state

    raise InputError(
        f"Referências não estabilizaram após quatro passagens. Consulte {work / 'main.log'}"
    )
