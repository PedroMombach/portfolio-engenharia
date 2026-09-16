"""Public, synthetic checks. No third-party PDFs or private benchmark data."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from etapas import limpeza, qa, triagem
from nucleo import ambiente, config
from nucleo.manifesto import Manifesto

TEST_DIR = Path(__file__).resolve().parent
PROJECT_DIR = TEST_DIR.parent


def pasta_temporaria():
    return tempfile.TemporaryDirectory(prefix=".test-tmp-", dir=TEST_DIR)


def criar_pdf_sintetico(caminho):
    """Create a one-page PDF with a native text layer, using only the standard library."""
    linhas = [
        "1 INTRODUCTION",
        "This synthetic technical document has selectable text and no image layer.",
        "2 METHOD",
        "Its purpose is to exercise PDF triage without distributing a real standard.",
        "3 CONCLUSION",
        "The page reference and extracted text can be checked with Poppler.",
    ]
    comandos = ["BT /F1 12 Tf 72 750 Td 16 TL"]
    for n, linha in enumerate(linhas):
        texto = linha.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        comandos.append(("" if n == 0 else "T* ") + f"({texto}) Tj")
    comandos.append("ET")
    stream = "\n".join(comandos).encode("ascii") + b"\n"
    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"endstream",
    ]
    dados = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for numero, corpo in enumerate(objetos, 1):
        offsets.append(len(dados))
        dados.extend(f"{numero} 0 obj\n".encode("ascii") + corpo + b"\nendobj\n")
    inicio_xref = len(dados)
    dados.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode("ascii"))
    for off in offsets[1:]:
        dados.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    dados.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
        f"startxref\n{inicio_xref}\n%%EOF\n".encode("ascii")
    )
    caminho.write_bytes(dados)


class TestesPublicos(unittest.TestCase):
    def test_manifesto_invalida_dependentes_e_preserva_coluna_manual(self):
        with pasta_temporaria() as pasta:
            man = Manifesto(Path(pasta))
            man.extras = ["conferido_por"]
            linha = man.nova("SPEC-2026-example")
            linha["conferido_por"] = "revisor"
            linha["observacao"] = "anotacao manual"
            for etapa in ("estrutura", "tabelas", "limpeza", "metadados"):
                man.marcar(linha, etapa, "ok", 1)
            linha["qa"] = "aprovado"
            man.invalidar_apos(linha, "estrutura")
            self.assertEqual(linha["estado_tabelas"], "pendente")
            self.assertEqual(linha["estado_metadados"], "pendente")
            self.assertEqual(linha["qa"], "")
            man.salvar()
            recarregado = Manifesto.carregar(Path(pasta)).linhas["SPEC-2026-example"]
            self.assertEqual(recarregado["conferido_por"], "revisor")
            self.assertEqual(recarregado["observacao"], "anotacao manual")

    def test_qa_detecta_item_perdido(self):
        origem = "4.1 Escopo\n4.2 Premissas\n4.3 Critérios\n4.4 Resultado\n"
        corpus = "#### 4.1 Escopo\n#### 4.2 Premissas\n#### 4.4 Resultado\n"
        self.assertIn("4.3", qa.itens_perdidos(corpus, origem))

    def test_perfil_publico_preserva_aviso_de_restricao(self):
        regras = limpeza.carregar_regras(config.Config(), PROJECT_DIR, {})
        texto = "<!-- p.1 -->\nCópia não autorizada\n4.1 Regras de cálculo\n"
        resultado, _ = limpeza.limpar_texto(texto, regras)
        self.assertIn("Cópia não autorizada", resultado)
        self.assertIn("<!-- p.1 -->", resultado)

    def test_config_recusa_saida_dentro_da_entrada(self):
        with pasta_temporaria() as pasta:
            entrada = Path(pasta) / "pdfs"
            entrada.mkdir()
            with self.assertRaises(config.ErroConfig):
                config.validar_caminhos(entrada, entrada / "saida")

    @unittest.skipUnless(ambiente.localizar("pdfinfo") and ambiente.localizar("pdftotext"),
                         "Poppler nao instalado: teste de integracao da triagem ignorado")
    def test_pdf_sintetico_segue_rota_de_texto_nativo(self):
        with pasta_temporaria() as pasta:
            pdf = Path(pasta) / "SPEC-2026-example.pdf"
            criar_pdf_sintetico(pdf)
            diag = triagem.diagnosticar(pdf)
            self.assertEqual(diag["paginas"], 1)
            self.assertEqual(diag["rota_sugerida"], "A")
            self.assertGreater(diag["car_por_pag"], 80)

    @unittest.skipUnless(os.environ.get("DOC2MD_FULL_SMOKE") == "1",
                         "defina DOC2MD_FULL_SMOKE=1 para converter o PDF sintetico")
    def test_pipeline_completo_em_pdf_sintetico(self):
        with tempfile.TemporaryDirectory(prefix="doc2md-smoke-") as pasta:
            raiz = Path(pasta)
            entrada, saida = raiz / "entrada", raiz / "saida"
            entrada.mkdir()
            criar_pdf_sintetico(entrada / "SPEC-2026-example.pdf")
            comando = [sys.executable, str(PROJECT_DIR / "main.py"), "tudo",
                       "--entrada", str(entrada), "--saida", str(saida), "--jobs", "1"]
            processo = subprocess.run(comando, cwd=PROJECT_DIR, capture_output=True,
                                      text=True, errors="replace", timeout=300)
            self.assertEqual(processo.returncode, 0,
                             f"stdout:\n{processo.stdout}\nstderr:\n{processo.stderr}")
            corpus = (saida / "corpus" / "SPEC-2026-example.md").read_text(encoding="utf-8")
            self.assertIn("<!-- p.1 -->", corpus)
            self.assertIn("origem_sha256:", corpus)
            self.assertIn("#", corpus)


if __name__ == "__main__":
    unittest.main()
