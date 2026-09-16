# Doc2MD

**Português** | [English](README.en.md) · [Artigo](docs/artigo.md) · [Método e medições](docs/metodologia.md) · [Direitos e privacidade](docs/direitos-e-privacidade.md)

Converte um acervo de **normas, manuais e literatura técnica em PDF** para
Markdown que uma IA consegue consultar. O Markdown mantém a referência à
página de origem, e cada documento sai com metadados, tabelas em CSV e um
relatório de qualidade.

O ponto central é **não transformar uma leitura duvidosa em texto com cara de
fonte confiável**. Uma figura sem eixos, uma célula na coluna errada ou uma
equação com um índice trocado continuam parecendo convincentes depois de
convertidas. Por isso, o Doc2MD guarda a evidência (recorte da página e
posição do elemento) junto com o texto extraído. Assim, a interpretação pode
ser feita depois, com o contexto da pergunta. O [artigo](docs/artigo.md) conta
como se chegou a essa decisão.

## Executar

Requer o [Anaconda](https://www.anaconda.com/download) ou o [Miniconda](https://docs.conda.io/projects/miniconda/). Use o **Anaconda PowerShell Prompt**
(menu Iniciar), porque o instalador é um script PowerShell. Entre nesta pasta
e execute:

```powershell
.\instalar.ps1                 # cria o ambiente 'doc2md' e baixa os idiomas do OCR
conda activate doc2md
python main.py doutor          # confere se todas as dependências estão presentes
python main.py init            # pergunta a pasta dos PDFs e a pasta de saída
python main.py tudo            # roda o pipeline completo
```

Observações:

- **GPU:** com uma placa NVIDIA compatível, use `.\instalar.ps1 -Gpu`. A CPU
  também funciona, só é mais lenta.
- **Modelos:** na primeira conversão, o Docling baixa seus modelos. Depois
  disso, o processamento roda offline.
- **Tempo e disco:** acervos grandes levam horas e ocupam alguns GB. A pasta
  de saída deve ficar fora da pasta de entrada.
- **Sem perguntas:** copie [config.example.toml](config.example.toml) para
  `config.toml`, edite os caminhos e rode `python main.py tudo`.

O Markdown final fica em `<saida>/corpus/`. Na mesma pasta de saída ficam
também:

- `manifesto.csv`, com o estado de cada documento em cada etapa;
- `relatorio-qa.md`, com o veredito de qualidade e os motivos.

## Como funciona

| Etapa | O que faz |
| --- | --- |
| `inventariar` | Calcula o hash, verifica a integridade e faz a triagem de cada PDF: texto nativo, texto com tabelas densas, scan, camada de texto corrompida ou misto. |
| `ocr` | Aplica OCR (OCRmyPDF/Tesseract) só onde a triagem indicou. |
| `converter` | Docling gera o Markdown, um JSON com a posição de cada bloco e as imagens. |
| `tabelas` | Extrai para CSV as tabelas solicitadas. |
| `limpar` | Recompõe a hifenização e transforma itens numerados em títulos. |
| `metadados` | Adiciona cabeçalho YAML e âncoras de página `<!-- p.N -->`. |
| `qa` | Verifica cobertura de texto, itens, tabelas, âncoras e dados bloqueados. |

Algumas propriedades do pipeline:

- **Execução retomável:** o manifesto evita refazer etapas já concluídas e
  invalida as etapas seguintes quando algo muda.
- **Falhas isoladas:** a falha de um documento não interrompe os outros.
- **Saída vazia é falha:** um resultado vazio nunca é tratado como sucesso.
- **Entrada intocada:** os PDFs de entrada nunca são alterados.

A triagem só **sugere** a rota. Uma decisão humana registrada em um arquivo de
[overrides](overrides.example.toml) prevalece sobre ela.

**Fórmulas** saem como **recorte da página + texto extraído**, marcadas como
não confiáveis para cálculo. **Figuras** continuam como imagens. As tabelas
solicitadas ganham CSV com referência à página.

## Limites

- **O QA automático detecta perdas grosseiras**, mas **não mede a correção**
  de figuras, tabelas, OCR ou fórmulas. A conferência visual continua humana.
- **A própria fonte pode conter erros**, e nenhuma conversão corrige isso.
  Antes de usar um valor em cálculo, confira imagem, unidades e contexto.
- **Não é um anonimizador.** O perfil público sinaliza números de CPF no
  texto. Veja a [nota de direitos e privacidade](docs/direitos-e-privacidade.md)
  antes de compartilhar resultados.

Este repositório traz código, configuração de exemplo e testes com um PDF
sintético. **Não inclui** os documentos do acervo usado no desenvolvimento nem
os resultados da conversão.

Testes: `python -m unittest discover -s tests -v`.

Licença do código: [MIT](LICENSE). Os documentos que você converter e as
dependências instaladas têm direitos e licenças próprios.
