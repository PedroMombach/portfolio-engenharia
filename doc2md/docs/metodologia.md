# Apêndice técnico: método, medições e limites

[Artigo](artigo.md) · [English](methods.en.md)

Este apêndice descreve **registros históricos** do desenvolvimento de Doc2MD, concluídos em setembro de 2026. Os PDFs de normas e livros, seus recortes e os overrides usados na avaliação não fazem parte do repositório público. Os testes sintéticos incluídos aqui verificam comportamento do código, não reproduzem as medições abaixo.

## Acervo e fluxo

O registro final descreve 37 documentos e 3.758 páginas. A triagem havia sido calibrada em 36 PDFs antes da incorporação do último documento. A unidade de estado é o documento: `manifesto.csv` guarda SHA-256, integridade, diagnóstico, rota efetiva, versão e estado de cada etapa, métricas e observações. Se o original, rota ou idioma de OCR muda, etapas dependentes voltam a `pendente`; falhas individuais ficam registradas sem parar o lote.

| Rota | Diagnóstico | Tratamento |
| --- | --- | --- |
| A | Texto nativo utilizável | PDF original → Docling. |
| B | Texto nativo denso ou com indícios de tabelas | PDF original → Docling; tabelas conforme override. |
| C | Quase nenhuma página com texto | OCRmyPDF `--force-ocr`. |
| D | Camada de texto corrompida | OCRmyPDF `--force-ocr` na cópia de trabalho. |
| E | Mistura de páginas com e sem texto | OCRmyPDF `--redo-ocr`, com tratamento de exceções do PDF. |
| F, extra | Tabelas que devem ser dados estruturados | Camelot → CSV com página, método, dimensões e score. |

O diagnóstico combina Poppler (`pdfinfo`, `pdftotext`, `pdfimages`, `pdffonts`), cobertura de texto por página, caracteres de controle, tokens anômalos e cobertura de imagem. A versão de referência é **Poppler 24.04**. Na comparação registrada com 26.09, 7 dos 36 PDFs tiveram métricas de caracteres ou tokens alteradas. A rota é sugestão: OCR legado ruim, porém plausível, pode passar como texto nativo. A decisão humana em `overrides.toml` prevalece.

OCRmyPDF/Tesseract cria um PDF de trabalho para C–E; Docling trabalha nesse PDF e não refaz OCR internamente. O JSON do Docling guarda procedência por bloco, página e `bbox`. O Markdown recebe `<!-- p.N -->`; figuras e fórmulas são assets relativos. A etapa de tabelas consulta páginas do JSON ou um intervalo curado. O perfil de limpeza transforma a apresentação e pode conter regras adicionais definidas pelo operador. O corpus final recebe front matter YAML. O QA avalia o corpus de novo a cada execução, sem confiar no veredito anterior.

## Casos de aceitação documentados

| Marco | Evidência do ensaio original | Papel no desenho |
| --- | --- | --- |
| M1, triagem | 36 PDFs; um scan de 36 páginas devolvia zero caracteres por `pdftotext`; outro tinha fração de caracteres de controle 0,236. | Separar ausência de texto, corrupção e texto nativo; saída vazia nunca equivale a sucesso. |
| M2, OCR | Scan sem texto precisava produzir camada consultável; a fração de caracteres de controle do PDF corrompido deveria cair abaixo de 0,01. | Usar `force` quando é preciso descartar a camada ruim. |
| M3, estrutura | Em um documento de referência, a configuração histórica de MarkItDown produziu zero headings; o critério exigia títulos e símbolo grego preservado. | Processar layout com Docling e manter JSON de procedência. É um caso isolado, sem versão do comparador registrada. |
| M4, tabelas | Em uma tabela de referência, Camelot `stream`: **21 × 6**, score **100,0**; `lattice`: **19 × 5**, score **99,57**. | Método de extração é curado por documento. Score não atesta célula correta. |
| M5, limpeza/metadados | O estudo detectou marcas de exemplar também no JSON intermediário e exigiu âncoras em todos os documentos. | Separar corpus, ativos e estado; revisar todas as camadas antes de compartilhar. A versão pública não inclui regras que removam avisos de restrição. |
| M6, QA | A remoção intencional de um item numerado precisava reprovar o documento. | Comparar corpus com a origem, além de checar âncoras, cobertura e tabelas solicitadas. |
| M7, execução | Dois PDFs em acervo temporário percorriam `doutor`, `init`, `renomear` e `tudo`. | Verificar execução do zero e retomada sem intervenção manual. |

O limite de **95% de cobertura** compara caracteres alfanuméricos do Markdown com o texto extraído do PDF, descontando linhas que um perfil configurado manda remover. Ele sinaliza perdas grosseiras, não precisão do OCR ou sentido da informação. Itens do PDF ausentes no corpus reprovam nas rotas nativas A/B e geram revisão nas rotas OCR C–E, onde a própria numeração pode estar errada. OCR com confiança média abaixo de 85%, lacunas de numeração, tabelas de baixo score e fórmulas suspeitas pedem revisão. A inspeção visual de três páginas por documento permanece humana.

## Ensaio de fórmulas

O acervo final tinha **2.472 blocos de fórmula em 27 documentos**; cerca de **31%** tinham uma assinatura textual de ordem de leitura suspeita (`=` ausente ou no fim). O exportador padrão do Docling podia substituir blocos por `<!-- formula-not-decoded -->`. O ensaio de alternativas usou as mesmas **44 fórmulas de quatro documentos**: um PDF nativo tipograficamente limpo e três scans difíceis. Comparou enriquecimento do Docling, pix2tex, dots.ocr e o recorte de imagem; houve leitura visual contextual de 14 fórmulas, sem cegamento. Essa seleção não estima uma taxa de erro populacional.

| Comparação textual de LaTeX | Strings coincidentes |
| --- | ---: |
| Docling × pix2tex | 3/44 (7%) |
| Docling × dots.ocr | 5/44 (11%) |
| pix2tex × dots.ocr | 1/44 (2%) |
| Os três | 1/44 (2%) |

Diferenças de sintaxe equivalentes podem reduzir a concordância medida; concordância não prova exatidão. Um ensaio de resolução diferente mudou muitas transcrições, e uma leitura plausível alterou um coeficiente. Por isso o padrão é recortar pelo `bbox` do Docling e guardar também o texto extraído, sinalizado como não confiável para cálculo. O recorte preserva o que a página mostra; **não garante** que a página esteja correta nem que o `bbox` inclua a fórmula inteira. Em scan ruim, fragmentos podem sair como imagens separadas.

No equipamento da avaliação (RTX 3050 Laptop, 6 GB), modelos Docling foram aproximadamente **16× mais rápidos em GPU** num ensaio de 100 fórmulas. Gerar o recorte custou aproximadamente **0,02 s por fórmula**, contra segundos para enriquecimento; esses valores são observações de hardware e configuração específicos. O custo de consultar um modelo visual posteriormente, caso a caso, **não foi medido**. A arquitetura preserva essa opção sem impor uma transcrição automática e potencialmente enganosa ao acervo inteiro.

## Reprodução pública e limites

Execute `python -m unittest discover -s tests -v` dentro desta pasta. O teste opcional `DOC2MD_FULL_SMOKE=1` converte um PDF sintético pelo pipeline completo. O ensaio histórico depende de fontes licenciadas que não são redistribuídas. Para comparações novas, registre versão e opções de cada ferramenta, PDFs usados com autorização, páginas amostradas, critério de conferência humana e métricas por documento. O resultado histórico de MarkItDown não deve ser interpretado como desempenho da versão atual.

Fontes de funcionamento: [MarkItDown](https://github.com/microsoft/markitdown), [Docling](https://docling-project.github.io/docling/), [Camelot](https://camelot-py.readthedocs.io/) e [OCRmyPDF](https://ocrmypdf.readthedocs.io/). As métricas desta página vêm do registro do projeto, não dessas documentações.
