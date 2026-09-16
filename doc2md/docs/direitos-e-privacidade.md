# Direitos sobre as fontes e privacidade na edição pública

[Artigo](artigo.md) · [English](rights-and-privacy.en.md)

Esta nota registra a revisão de risco da distribuição do **código**, feita em setembro de 2026. Ela não decide se uma licença específica autoriza a conversão ou a publicação de determinado PDF.

## Código livre não torna as fontes livres

A licença MIT deste repositório cobre o software e sua documentação original. PDFs de normas, livros e manuais, bem como o Markdown, imagens e CSV derivados deles, podem ter direitos e restrições próprios. A [Lei de Direitos Autorais, arts. 28–29](https://www.planalto.gov.br/ccivil_03/leis/l9610.htm), prevê autorização para modalidades como reprodução, adaptação, distribuição e armazenamento em base de dados, sujeitas às limitações legais dos [arts. 46 e seguintes](https://www.planalto.gov.br/ccivil_03/leis/l9610.htm). A conclusão prática é verificar a licença ou outra base jurídica **do acervo concreto** antes de publicar corpus, recortes ou PDFs de trabalho. Nenhum desses arquivos acompanha esta edição pública.

A frase “Cópia não autorizada” é um aviso de restrição, não um dado pessoal. O perfil especializado da versão privada a removia junto com marcas nominais. **Essa regra não é distribuída aqui.** Apagá-la não cria direito de redistribuir a obra e reduziria a rastreabilidade do exemplar. O perfil público `padrao` não remove avisos desse tipo. Quem criar regras próprias continua responsável por conferir o que elas apagam e os direitos sobre a fonte.

## CPF, CNPJ e o limite de regex

A [LGPD, art. 5º, I](https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709compilado.htm), define dado pessoal pela relação com uma **pessoa natural identificada ou identificável**. CPF é um identificador de pessoa natural. Um CNPJ de pessoa jurídica **não é, isoladamente, dado pessoal por definição**; essa é uma inferência a partir da lei, não licença para divulgar indiscriminadamente. A [ANPD observa](https://www.gov.br/anpd/pt-br/assuntos/noticias/NotaTcnica54.2025MTP2025.pdf/%40%40display-file/file) que dados ligados a MEI ou empresário individual, embora acompanhados de CNPJ, podem ser dados pessoais da pessoa física. A regra anterior tratava todo CNPJ como exigência da LGPD; essa formulação foi retirada.

O perfil público sinaliza uma **forma textual de CPF** no Markdown por meio do QA e redige textos correspondentes no JSON intermediário. Isso é uma barreira parcial, não anonimização. OCR pode omitir dígitos ou alterar pontuação; nomes e outros identificadores não dependem de CPF; o PDF de entrada, PDFs de trabalho e assets de imagem podem continuar a exibir dados. A [definição legal de anonimização](https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709compilado.htm) exige que a pessoa não seja identificável por meios técnicos razoáveis. A [ANPD trata anonimização como avaliação de risco](https://www.gov.br/anpd/pt-br/centrais-de-conteudo/documentos-tecnicos-orientativos/estudo_tecnico_sobre_anonimizacao_de_dados_na_lgpd_uma_visao_de_processo_baseado_em_risco_e_tecnicas_computacionais.pdf/%40%40display-file/file), não como uma única substituição de padrão.

Preservar imagens é essencial ao objetivo técnico do Doc2MD, mas também significa que uma publicação de resultados exige inspeção das **imagens, do JSON, do corpus e dos PDFs de trabalho**. O QA automático não certifica privacidade nem permissão de distribuição. A edição pública inclui apenas código, configuração ilustrativa e testes com PDF sintético.
