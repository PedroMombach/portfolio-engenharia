# Lista de materiais em LaTeX (LM-LaTeX)

**Português** | [English](README.en.md)

Gerar a lista de materiais de um projeto em Excel é fácil: qualquer modelo BIM
ou banco de componentes exporta uma planilha com códigos e quantidades. O
difícil é transformar essa planilha em um **documento bem apresentado, para ser
lido por pessoas**. Este gerador faz essa parte. Ele recebe a planilha e devolve
um PDF diagramado, com:

- capa;
- sumário navegável;
- uma ficha por família de componentes, com figura, descrição e tabela de
  dimensões e quantidades;
- histórico de revisões.

![Capa, sumário e ficha de família do PDF de exemplo](docs/preview.png)

[Ver o PDF de exemplo completo](docs/exemplo.pdf)

## O problema

A planilha é boa para quem calcula, mas ruim para quem lê: o cliente, o
orçamentista ou o montador. A versão legível, com uma ficha por família, era
montada à mão no Word, tabela por tabela. O trabalho não era difícil, mas era
longo, sujeito a erro de transcrição e refeito a cada revisão de escopo. Mudar
uma quantidade significava achar a folha, corrigir a célula e reconferir
paginação, sumário e numeração.

Com o gerador, a planilha continua sendo a fonte única, e o documento é
recomposto a cada emissão. A diagramação fica a cargo do LaTeX, e a
conferência passa a ser só sobre os dados.

## Executar

Requer o [Anaconda](https://www.anaconda.com/download) ou o [Miniconda](https://docs.conda.io/projects/miniconda/) e, além deles, uma distribuição LaTeX com `pdflatex`: o
[MiKTeX](https://miktex.org/download) no Windows ou o TeX Live. No **Anaconda Prompt**, entre nesta pasta e execute:

```bat
conda env create -f environment.yml
conda activate lista-materiais-latex
python main.py
```

O PDF sai em `output/exemplo/main.pdf`. Os parâmetros ficam no topo do
`main.py`:

- qual emissão gerar;
- pasta de saída;
- opção de gerar só o `.tex`, sem compilar.

## Entradas

| Arquivo | Conteúdo |
| --- | --- |
| `DB/data.xlsx`, aba `Catalogo` | Cadastro dos componentes, uma linha por dimensão, com código do emitente e do cliente. |
| `DB/figs/` | Figuras esquemáticas, nomeadas pelo código da família (PDF, PNG ou JPG). |
| `Emissoes/<nome>/itens.xlsx`, aba `Itens` | Códigos e quantidades desta emissão. |
| `Emissoes/<nome>/emissao.json` | Capa, códigos do documento, revisão e histórico. |

Para uma nova emissão:

1. Copie a pasta `Emissoes/exemplo`.
2. Edite `itens.xlsx` e `emissao.json` na cópia.
3. Aponte `EMISSAO` no `main.py` para o novo JSON.

## Comportamentos que valem destacar

- **Organização:** o documento é organizado por material e, dentro de cada
  material, pelo tipo em ordem alfabética.
- **Paginação:** tabelas longas quebram de página e repetem o cabeçalho.
- **Quantidades:**
  - quantidade zero pode ficar na planilha, mas o item não entra no PDF;
  - quantidades fracionárias saem com vírgula decimal.
- **Erros apontados:** código desconhecido ou repetido, quantidade inválida e
  família inconsistente geram erro com a linha do problema.
- **Figura ausente:** a família recebe uma imagem de reserva e o problema é
  registrado em `avisos.log`.
- **Caracteres especiais:** caracteres do LaTeX (`&`, `%`, `_`…) são
  escapados automaticamente.
- **Compilação:** o `pdflatex` roda até o sumário e os links estabilizarem.

## Estrutura

```text
main.py                       parâmetros e execução
lista_materiais/entrada.py    leitura e validação do JSON e das planilhas
lista_materiais/latex.py      geração do LaTeX a partir do template
lista_materiais/compilar.py   compilação com pdflatex
Template/                     template LaTeX (layout, capa, identidade em TikZ)
DB/                           catálogo e figuras de exemplo
Emissoes/exemplo/             emissão de exemplo
docs/                         PDF e imagem de exemplo
tests/                        testes automatizados
```

Testes: `python -m unittest discover -s tests -v`. Um dos testes compila o PDF
de verdade, então exige o `pdflatex`.

## Relação com a ferramenta em uso

Esta é a versão pública de um gerador que uso em projetos. O conceito é o
mesmo: catálogo em planilha, figuras, template LaTeX e compilação por emissão.
Foram trocados três pontos:

- os dados, aqui sintéticos: nomes, códigos e marcas não correspondem a nada
  real;
- a identidade gráfica, refeita para este repositório;
- a forma de pedir a emissão: aqui é um JSON; no original, uma planilha
  alimentada pelo modelo BIM.

Licença: [MIT](LICENSE). O PDF usa a fonte Latin Modern Sans, distribuída sob a
GUST Font License; openpyxl, pypdf e a distribuição LaTeX mantêm suas próprias licenças.
