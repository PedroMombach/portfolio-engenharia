"""Validações e integração; executar com python -m unittest discover -s tests -v."""
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
import uuid
from unittest.mock import patch
import xml.etree.ElementTree as ET
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import lista_materiais as g  # noqa: E402
EXAMPLE = ROOT / 'Emissoes/exemplo/emissao.json'


def fingerprint(paths):
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.is_file()}


def subset_workbook(source, destination, count):
    """Fixture derivada do XLSX real: mantém apenas N linhas de itens."""
    ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with ZipFile(source) as original, ZipFile(destination, 'w') as target:
        for item in original.infolist():
            content = original.read(item.filename)
            if item.filename == 'xl/worksheets/sheet1.xml':
                document = ET.fromstring(content)
                data = document.find('s:sheetData', ns)
                for row in list(data):
                    if int(row.attrib['r']) > count + 1:
                        data.remove(row)
                content = ET.tostring(document, encoding='utf-8', xml_declaration=True)
            target.writestr(item, content)


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.catalog = g.validate_catalog(g.read_sheet(ROOT / 'DB/data.xlsx', 'Catalogo', g.CATALOG_COLUMNS))
        self.items = g.read_sheet(ROOT / 'Emissoes/exemplo/itens.xlsx', 'Itens', ('COD_ELEMENTO', 'QUANTIDADE'))

    def test_example_has_five_families_and_two_long_tables(self):
        self.assertEqual(len(self.catalog), 69)
        families = {row['COD_FAMILIA'] for row in self.catalog}
        self.assertEqual(len(families), 5)
        for family in families:
            expected = 30 if family in ('MEC-AC-10001', 'MEC-FF-20001') else 3
            self.assertEqual(sum(row['COD_FAMILIA'] == family for row in self.catalog), expected)

    def test_numeric_quantities_zero_and_fraction(self):
        items = g.validate_items(self.items)
        self.assertEqual(items['MEC-AI-30001-001'], Decimal('12.5'))
        self.assertEqual(items['MEC-AI-30001-003'], 0)
        groups = g.select_materials(self.catalog, items)
        selected = [row['COD_ELEMENTO'] for types in groups.values() for families in types.values()
                    for rows in families.values() for row in rows]
        self.assertNotIn('MEC-AI-30001-003', selected)
        with self.assertRaisesRegex(g.InputError, 'quantidade positiva'):
            g.select_materials(self.catalog, {'MEC-AI-30001-003': Decimal('0')})
        self.assertEqual(g.format_quantity(Decimal('12.500')), '12,5')
        self.assertEqual(g.format_quantity(Decimal('100')), '100')

    def test_bad_quantities(self):
        for value in (None, '', '12', 'abc', True, -1, float('nan'), float('inf')):
            with self.subTest(value=value), self.assertRaises(g.InputError):
                g.validate_items([{'COD_ELEMENTO': 'TESTE', 'QUANTIDADE': value}])

    def test_duplicate_and_missing_item_codes(self):
        with self.assertRaisesRegex(g.InputError, 'duplicado'):
            g.validate_items([self.items[0], self.items[0]])
        with self.assertRaisesRegex(g.InputError, 'ausente'):
            g.validate_items([{'QUANTIDADE': 1}])

    def test_catalog_duplicate_missing_unit_and_family_conflict(self):
        with self.assertRaisesRegex(g.InputError, 'duplicado'):
            g.validate_catalog([self.catalog[0], self.catalog[0]])
        for column in ('UNIDADE', 'DESCR_FAMILIA', 'COD_FAMILIA', 'COD_CLIENTE_ELEMENTO', 'TITULO_FAMILIA'):
            with self.subTest(column=column), self.assertRaisesRegex(g.InputError, 'ausente'):
                g.validate_catalog([{**self.catalog[0], column: None}])
        rows = deepcopy(self.catalog[:2])
        rows[1]['COD_CLIENTE_ELEMENTO'] = rows[0]['COD_CLIENTE_ELEMENTO']
        with self.assertRaisesRegex(g.InputError, 'COD_CLIENTE_ELEMENTO duplicado'):
            g.validate_catalog(rows)
        rows = deepcopy(self.catalog[:2])
        rows[1]['MATERIAL'] = 'OUTRO MATERIAL'
        with self.assertRaisesRegex(g.InputError, 'inconsistentes'):
            g.validate_catalog(rows)

    def test_optional_reference_is_blank(self):
        row = {**self.catalog[0], 'REF_COMERCIAL': None}
        self.assertEqual(g.validate_catalog([row])[0]['REF_COMERCIAL'], '')

    def test_selection_uses_catalog_order_and_selected_elements_only(self):
        requested = dict(reversed(list(g.validate_items(self.items).items())))
        groups = g.select_materials(self.catalog, requested)
        self.assertEqual(list(groups), ['AÇO CARBONO', 'FERRO FUNDIDO', 'AÇO INOXIDÁVEL'])
        self.assertEqual(list(groups['AÇO CARBONO']), ['CURVA', 'FLANGE'])
        single = g.select_materials(self.catalog, {'MEC-AI-30001-002': Decimal('7')})
        self.assertEqual(list(single), ['AÇO INOXIDÁVEL'])
        self.assertEqual(single['AÇO INOXIDÁVEL']['TUBO']['MEC-AI-30001'][0]['QUANTIDADE'], 7)
        with self.assertRaisesRegex(g.InputError, 'não encontrados'):
            g.select_materials(self.catalog, {'DESCONHECIDO': 1})

    def test_latex_escape_is_single_pass(self):
        self.assertEqual(g.latex_escape('a\\b_&%${}#~^'),
                         r'a\textbackslash{}b\_\&\%\$\{\}\#\textasciitilde{}\textasciicircum{}')
        self.assertEqual(g.latex_escape(None), '')
        self.assertEqual(g.latex_escape('µm'), r'\ensuremath{\mu}m')

    def test_missing_sheet_and_headers(self):
        with self.assertRaisesRegex(g.InputError, 'não encontrada'):
            g.read_sheet(ROOT / 'DB/data.xlsx', 'NaoExiste', g.CATALOG_COLUMNS)
        with self.assertRaisesRegex(g.InputError, 'cabeçalhos'):
            g.read_sheet(ROOT / 'DB/data.xlsx', 'Catalogo', ('QUANTIDADE',))


class GenerationTests(unittest.TestCase):
    def setUp(self):
        temp_root = ROOT / 'tmp'
        temp_root.mkdir(exist_ok=True)
        # mkdir herda as permissões da pasta no Windows, inclusive em sandbox.
        self.folder = (temp_root / ('teste emissao ' + uuid.uuid4().hex)).resolve()
        self.folder.mkdir()
        self.addCleanup(self.remove_fixture)
        self.config = json.loads(EXAMPLE.read_text(encoding='utf-8-sig'))
        for key in ('catalogo', 'figuras', 'itens'):
            self.config[key] = str((EXAMPLE.parent / self.config[key]).resolve())

    def remove_fixture(self):
        if self.folder.parent != (ROOT / 'tmp').resolve() or self.folder.is_symlink():
            raise RuntimeError('Pasta de teste fora do diretório temporário esperado.')
        shutil.rmtree(self.folder)

    def write_config(self, **updates):
        config = {**self.config, **updates}
        path = self.folder / (config['identificador'] + '.json')
        path.write_text(json.dumps(config, ensure_ascii=False), encoding='utf-8')
        return path

    def test_config_validation_and_relative_paths(self):
        loaded = g.load_emission(EXAMPLE)
        self.assertEqual(loaded['catalogo'], (ROOT / 'DB/data.xlsx').resolve())
        for updates in ({'identificador':'../fora'}, {'identificador':'CON'}, {'pagina_inicial':0},
                        {'pagina_inicial':True}, {'titulo':''}, {'historico_revisoes':[]}, {'revisao':'9'}):
            # Do not use the unsafe identifier to construct the fixture path.
            p = self.folder / 'invalid.json'
            p.write_text(json.dumps({**self.config, **updates}), encoding='utf-8')
            with self.subTest(updates=updates), self.assertRaises(g.InputError):
                g.load_emission(p)

    def test_repeat_and_two_outputs_preserve_sources(self):
        inputs = [* (ROOT / 'Template').rglob('*.tex'), ROOT / 'DB/data.xlsx', EXAMPLE.parent / 'itens.xlsx']
        before = fingerprint(inputs)
        first = g.generate(self.write_config(), only_tex=True, output_root=self.folder)
        original = fingerprint((first['work'] / 'generated').glob('*.tex'))
        second = g.generate(self.write_config(identificador='outra', titulo='Outra lista'), only_tex=True, output_root=self.folder)
        self.assertNotEqual(first['output'], second['output'])
        self.assertEqual(original, fingerprint((first['work'] / 'generated').glob('*.tex')))
        g.generate(self.write_config(), only_tex=True, output_root=self.folder)
        self.assertEqual(original, fingerprint((first['work'] / 'generated').glob('*.tex')))
        self.assertEqual(before, fingerprint(inputs))

    def test_missing_image_warning_and_bank_paths(self):
        images = self.folder / 'figuras com espaços'
        images.mkdir()
        shutil.copy2(ROOT / 'DB/figs/MEC-AC-10001.pdf', images)
        result = g.generate(self.write_config(figuras=str(images)), only_tex=True, output_root=self.folder)
        self.assertEqual(len(result['warnings']), 4)
        content = (result['work'] / 'generated/mats.tex').read_text(encoding='utf-8')
        self.assertIn('imgs/handler.jpg', content)
        self.assertIn('Sem figura cadastrada', content)
        self.assertIn(images.as_posix(), content)
        self.assertNotIn('imgs/MEC-', content)
        self.assertFalse(list((result['work'] / 'imgs').glob('MEC-*')))

    def test_missing_pdflatex_does_not_report_success(self):
        with patch.object(g.shutil, 'which', return_value=None):
            with self.assertRaisesRegex(g.InputError, 'pdflatex não encontrado'):
                g.compile_pdf(self.folder)

    def test_compiler_failure_and_unstable_references(self):
        failure = subprocess.CompletedProcess([], 1, b'Compilation failed')
        with patch.object(g.subprocess, 'run', return_value=failure):
            with self.assertRaisesRegex(g.InputError, 'falhou'):
                g.compile_pdf(self.folder, executable='pdflatex')
        (self.folder / 'main.log').write_text('There were undefined references.')
        success = subprocess.CompletedProcess([], 0, b'Needs another pass')
        with patch.object(g.subprocess, 'run', return_value=success) as run:
            with self.assertRaisesRegex(g.InputError, 'quatro passagens'):
                g.compile_pdf(self.folder, executable='pdflatex')
            self.assertEqual(run.call_count, 4)

    @unittest.skipUnless(shutil.which('pdflatex'), 'pdflatex não disponível')
    def test_real_compilation_from_other_directory_with_spaces(self):
        items = self.folder / 'itens parciais.xlsx'
        subset_workbook(Path(self.config['itens']), items, 2)
        images = self.folder / 'banco com espaços'
        images.mkdir()
        shutil.copy2(ROOT / 'DB/figs/MEC-AC-10001.pdf', images)
        config = self.write_config(identificador='parcial', itens=str(items), figuras=str(images),
                                  titulo='Teste & revisão 50% #1', codigo_cliente=r'CLI_{1}\A', pagina_inicial=7)
        script = 'import sys; sys.path.insert(0, sys.argv[1]); import lista_materiais as g; g.generate(sys.argv[2], output_root=sys.argv[3])'
        result = subprocess.run([sys.executable, '-c', script, str(ROOT), str(config), str(self.folder)],
                                cwd=self.folder, capture_output=True, timeout=180)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
        work = self.folder / 'parcial/work'
        self.assertTrue((work.parent / 'main.pdf').is_file())
        content = (work / 'generated/mats.tex').read_text(encoding='utf-8')
        self.assertEqual(content.count(r'\begin{myTables}'), 1)
        self.assertNotIn('MEC-AC-10001-003', content)
        log = (work / 'main.log').read_text(errors='replace')
        self.assertNotIn('undefined references', log)
        first_pdf = (work.parent / 'main.pdf').read_bytes()
        second = g.generate(self.write_config(identificador='segunda', figuras=str(images)), output_root=self.folder)
        self.assertTrue((second['output'] / 'main.pdf').is_file())
        self.assertEqual(first_pdf, (work.parent / 'main.pdf').read_bytes())
        # A leitura do PDF é parte da verificação de integração quando pypdf existe.
        try:
            from pypdf import PdfReader
        except ImportError:
            self.skipTest('Instale o pypdf (environment.yml) para verificar paginação no PDF.')
        reader = PdfReader(second['output'] / 'main.pdf')
        pages = [p.extract_text() for p in reader.pages]
        toc = pages[1]
        self.assertNotIn('MEC-AC-10001', toc)
        self.assertNotIn('MEC-FF-20001', toc)
        self.assertTrue(reader.pages[1].get('/Annots'), 'O sumário precisa conter links clicáveis.')
        outline_titles = [entry['/Title'] for branch in reader.outline
                          for entry in (branch if isinstance(branch, list) else [branch])]
        for family in ('MEC-AC-40001', 'MEC-AC-10001', 'MEC-FF-20001',
                       'MEC-AI-50001', 'MEC-AI-30001'):
            self.assertTrue(any(family in title for title in outline_titles), family)
        for family in ('MEC-AC-10001', 'MEC-FF-20001'):
            starts = [i for i, page in enumerate(pages) if family + '-001' in page]
            ends = [i for i, page in enumerate(pages) if family + '-030' in page]
            self.assertEqual(len(starts), 1)
            self.assertEqual(len(ends), 1)
            self.assertGreater(ends[0], starts[0], f'{family}: tabela deve quebrar página')
            self.assertIn('continuação', pages[ends[0]])
            self.assertIn('Quantidade', pages[ends[0]])
        full_text = '\n'.join(pages)
        self.assertNotIn('SEÇÕES DESTA LISTA', full_text)
        for page in pages:
            if 'Código emitente' in page:
                self.assertLess(page.index('Quantidade'), page.index('Unidade'))
        self.assertIn('Sem figura cadastrada', full_text)
        self.assertIn('12,5', full_text)
        for row in g.read_sheet(ROOT / 'DB/data.xlsx', 'Catalogo', g.CATALOG_COLUMNS):
            expected = 0 if row['COD_ELEMENTO'] == 'MEC-AI-30001-003' else 1
            self.assertEqual(full_text.count(row['COD_ELEMENTO']), expected)
            self.assertEqual(full_text.count(row['COD_CLIENTE_ELEMENTO']), expected)


if __name__ == '__main__':
    unittest.main()
