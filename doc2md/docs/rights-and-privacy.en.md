# Source rights and privacy in the public edition

[Article](article.en.md) · [Português](direitos-e-privacidade.md)

This note records a September 2026 risk review of distributing the **software**. It does not determine whether a particular license permits conversion or publication of a particular PDF.

## Free software does not make the source documents free

The repository's MIT license covers its code and original documentation. Standards, books and manuals, and the Markdown, crops or CSV derived from them, may have separate rights and restrictions. Brazil's [Copyright Act, arts. 28–29](https://www.planalto.gov.br/ccivil_03/leis/l9610.htm), addresses authorization for reproduction, adaptation, distribution and database storage, subject to statutory exceptions in [arts. 46 onward](https://www.planalto.gov.br/ccivil_03/leis/l9610.htm). Check the license or other legal basis for the **specific collection** before publishing a corpus, crops or working PDFs. This public edition contains none of them.

“Unauthorized copy” is a restriction notice, not personal data. A specialized profile in the private edition removed that notice along with nominal markings. **That rule is not distributed here.** Deleting the notice does not grant redistribution rights and would reduce provenance of the copy. The public `padrao` profile preserves such notices. Anyone adding custom rules remains responsible for reviewing both the deleted content and rights in the source.

## CPF, CNPJ and the limits of regex

Brazil's [LGPD, art. 5(I)](https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709compilado.htm), defines personal data by its relationship to an **identified or identifiable natural person**. A CPF identifies a natural person. A company's CNPJ is **not inherently personal data in isolation**; this is an inference from the statutory definition, not blanket permission to disclose associated records. Brazil's [data protection authority notes](https://www.gov.br/anpd/pt-br/assuntos/noticias/NotaTcnica54.2025MTP2025.pdf/%40%40display-file/file) that CNPJ-linked information about individual entrepreneurs may concern the natural person. The previous profile described every CNPJ match as an LGPD requirement; that wording has been removed.

The public profile flags one **textual CPF pattern** in final Markdown during QA and redacts matching text items in intermediate JSON. This is a partial safeguard, **not anonymization**. OCR may omit digits or punctuation; names and other identifiers need no CPF; input and working PDFs and image assets may still display personal information. The [LGPD definition of anonymization](https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709compilado.htm) concerns whether a person can still be identified by reasonably available technical means. The [authority's technical study](https://www.gov.br/anpd/pt-br/centrais-de-conteudo/documentos-tecnicos-orientativos/estudo_tecnico_sobre_anonimizacao_de_dados_na_lgpd_uma_visao_de_processo_baseado_em_risco_e_tecnicas_computacionais.pdf/%40%40display-file/file) treats anonymization as a risk process, not a single pattern replacement.

Preserving images is central to Doc2MD's engineering purpose. It also means that publishing conversion results requires inspection of **images, JSON, corpus and working PDFs**. Automated QA certifies neither privacy nor publication rights. The public edition contains only code, illustrative configuration and synthetic-PDF tests.
