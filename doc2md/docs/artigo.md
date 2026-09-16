# Converter um acervo técnico para IA sem transformar erro em "verdade"

**Doc2MD, um estudo de caso** · setembro de 2026 · [English](article.en.md) · [Método e medições](metodologia.md)

## Por que este projeto existe

Na minha experiência, as IAs generativas, na forma em que vêm, ainda não
produzem boa documentação e bons procedimentos de engenharia. Faltam três
coisas:

- nível de detalhe;
- terminologia específica;
- critério sobre como abordar cada problema.

Para chegar lá, é preciso gerenciar melhor o contexto: dar à IA a base técnica
certa, no momento certo.

O Doc2MD resolve a primeira parte disso. Ele converte um acervo de normas,
manuais e literatura técnica em PDF para Markdown, que é o formato bruto que
alimenta essa base. O projeto não escreve especificação nenhuma: prepara o
material que vai sustentar essa escrita.

O acervo usado no desenvolvimento era de **equipamentos hidromecânicos**:
comportas, grades, válvulas e condutos. Só o núcleo básico somava cerca de
**3.000 páginas** (3.758 no registro final, em 37 documentos), de quatro
tipos:

- documentos escaneados à mão;
- documentos com anotações manuscritas;
- digitalizações sem camada de texto;
- PDFs "comuns", de qualidade variável.

Uma restrição orientou o projeto desde o início: a conversão tinha de ser
**viável a baixo custo**. A meta era que alguém com uma assinatura básica de IA
e um notebook de configuração média conseguisse processar o acervo inteiro.

## Por que um conversor pronto não bastou

O primeiro teste foi com o [MarkItDown](https://github.com/microsoft/markitdown).
No ensaio feito na época, o resultado foi fraco justamente nos elementos que
carregam a informação técnica de uma norma: **figuras, equações e tabelas**.
Em um documento normativo, a configuração testada não reconheceu nenhum
título. Em um scan de 36 páginas, devolveu praticamente um arquivo vazio, sem
nenhum aviso. Esses resultados valem para aquela versão e configuração; não
são uma avaliação da ferramenta atual.

O padrão que se repetiu foi este: **identificar um elemento sem o contexto do
documento não produz bons resultados**. Baixa resolução, respingos e rabiscos
em documentos escaneados afetam diretamente a extração. Depois da conversão, a
informação original se perde, e o erro fica sem rastro.

Por isso a pergunta mudou. Deixou de ser "qual conversor é melhor?" e passou a
ser "o que precisa ser preservado para que uma leitura posterior continue
verificável?":

- **Em figuras e ábacos:** eixos, escala, legenda e o parágrafo que define as
  condições de uso.
- **Em tabelas:** a que cabeçalho e unidade cada número pertence.
- **Em equações:** índices, frações e símbolos.

## A decisão central

O Doc2MD usa o [Docling](https://github.com/docling-project/docling) para a
análise de layout e o OCRmyPDF/Tesseract para os documentos escaneados. Uma
regra orienta o tratamento de cada tipo de elemento:

> **Quando a extração automática não é confiável o bastante para dispensar
> conferência, o dado original é preservado junto do resultado, e não
> substituído por ele.**

Na prática, o pipeline funciona assim:

1. Uma triagem barata separa PDFs com texto utilizável, scans e arquivos
   mistos, e aplica OCR só onde é necessário.
2. Cada documento vira um Markdown com âncoras de página (`<!-- p.N -->`) e
   metadados.
3. Um JSON guarda a posição de cada bloco. Com ele, dá para refazer a
   exportação em segundos, sem repetir a análise de layout.
4. As tabelas escolhidas também saem em CSV.
5. Figuras continuam como imagens ligadas ao texto.
6. As fórmulas recebem o tratamento descrito a seguir.

## O caso das fórmulas: por que o Doc2MD não gera LaTeX

O acervo tinha **2.472 fórmulas**, em 27 dos 37 documentos. Em cerca de **31 %**
delas, o texto que o PDF entrega vem com os símbolos fora da ordem de leitura.
Um exemplo, tirado da ABNT NBR 6123:

```text
Texto extraído:       2 s s 4 d F C q π =
O que a página mostra: F = Cs · q · π d² / 4
```

Diante disso, o comportamento padrão do Docling é **apagar** a fórmula e
deixar só um comentário `formula-not-decoded`. Em um único documento do
acervo, isso eliminaria 24 fórmulas sem nenhum aviso.

Cinco caminhos foram testados sobre as **mesmas 44 fórmulas**, de quatro
documentos. Um deles era um PDF nativo limpo; os outros três estavam entre os
piores scans do acervo.

| Rota | O que é |
| --- | --- |
| A | Enriquecimento de fórmula do próprio Docling |
| B | Recorte da imagem da fórmula, pela posição que o Docling já registra |
| C | pix2tex (LaTeX-OCR) sobre os recortes |
| D | dots.ocr, um modelo de visão de 3 bilhões de parâmetros, sobre os recortes |
| E | Leitura visual de uma IA generativa sobre os recortes (14 das 44) |

Ferramentas pagas que enviam o documento para fora foram descartadas sem
teste, porque contrariam a premissa de rodar localmente.

### O custo não decidiu

| Rota (notebook com RTX 3050 de 6 GB) | Por fórmula | Acervo inteiro (estimado) |
| --- | --- | --- |
| A · Docling em CPU | 18 a 65 s | ~32 h |
| A · Docling em GPU | 1 a 4 s | ~2 h |
| C · pix2tex em CPU | 0,8 a 2,2 s | ~1 h |
| D · dots.ocr em GPU | 4 a 22 s | 3 a 15 h |
| **B · recorte** | **0,02 s** | **~10 min** |

A GPU acelerou os modelos do Docling em cerca de 16 vezes. Por isso, a escolha
do dispositivo passou a valer para toda a conversão. Processar **páginas
inteiras** com um modelo de visão ficou fora de questão: medido em uma GPU T4 de
nuvem, levou mais de 3 minutos por página, o que daria mais de nove dias para
o acervo. Por recorte, o custo cai para segundos, porque o custo de um modelo
de visão cresce com o tamanho da imagem, e um recorte tem cerca de 50 vezes
menos pixels que a página.

### A qualidade decidiu

O problema real foi que **as rotas discordam entre si**, e o erro vem embalado
em um LaTeX bem formado.

| Comparação | Transcrições idênticas |
| --- | --- |
| A × C | 3 de 44 |
| A × D | 5 de 44 |
| C × D | 1 de 44 |
| As três | 1 de 44 |

A comparação é textual e penaliza diferenças só de escrita, então subestima a
concordância real. Ainda assim, nenhuma rota serve de referência para validar
as outras.

Um caso da DIN 4114-2, com a mesma imagem para todas as rotas:

- A: `\omega_y = \frac{F \cdot \sigma_{z\upsilon}|}{S}`
- C: `o_{Y} = \frac{F \cdot o_{Y0}}{S}`
- D: `\omega_{\gamma} = \frac{F \cdot \sigma_{ZU}}{S}`
- E: `\omega_y = \frac{F \cdot \sigma_{zul}}{S}` (*zul*, de *zulässig*: tensão
  admissível)

As três primeiras transcrições renderizam bem. Todas estão erradas, e nada no
resultado indica isso.

### O erro que fechou a questão

Em uma norma escaneada, a página traz a lei de perda de carga para escoamento
turbulento em regime rugoso:

```text
λ^(−1/2) = −2 · log( ε / (3,71 · D) )
```

Essa expressão é o termo de rugosidade da equação de Colebrook-White. Logo
após o coeficiente, há um respingo do scan, e o modelo de visão leu **−2,1**
nas duas configurações testadas. O coeficiente correto é 2. Esse erro altera
diretamente o cálculo de perda de carga em um conduto forçado, e o LaTeX
gerado saía impecável.

O defeito só apareceu porque foi possível abrir o recorte e comparar com a
página. É exatamente isso que a solução adotada preserva.

A leitura visual (rota E) acertou esses casos por **conhecimento de domínio**,
não por enxergar melhor. Ela reconheceu a equação e o coeficiente, e sabia que
`zul` abrevia *zulässig*. Um modelo especializado vê símbolos dentro de um
retângulo, sem o documento em volta. Essa leitura não foi cega, cobriu só 14
fórmulas e não é automatizável. Ela explica por que os modelos falham, mas não
é uma rota de produção.

### A solução adotada

Texto embaralhado é obviamente suspeito, e quem lê confere por reflexo. Uma
transcrição plausível e errada parece confiável e entra na base sem
conferência. Para um acervo que vai apoiar produtos de engenharia, o segundo tipo de erro é o caro.

Por isso, cada fórmula sai no Markdown assim:

```text
<!-- formula: recorte fiel da pagina; o texto abaixo e o do PDF, e a ordem dos simbolos pode estar trocada -->
![formula](../assets/<id>/formula-p007-01.png)

`texto extraído do PDF`
```

Essa saída tem quatro propriedades:

- **Cobertura total:** todas as 2.472 fórmulas têm recorte, inclusive as dos
  documentos escaneados.
- **Fidelidade:** o recorte é a própria página, não uma leitura dela. Isso não
  garante que a página esteja certa, nem que o recorte pegue a fórmula
  inteira: em scans ruins, uma fórmula pode sair em pedaços.
- **Marcação legível por máquina:** o comentário permite que a etapa seguinte
  decida o que fazer, inclusive mandar o recorte a um modelo de visão **na
  hora da consulta**, junto com o parágrafo vizinho.
- **Decisão reversível:** a posição de cada fórmula fica guardada, então gerar
  outra saída não exige reconverter o acervo.

## Quando o erro está na própria fonte

Nem todo erro nasce na conversão. Na primeira equação da API 421 (edição de
1990), falta um sinal de menos entre as densidades. Do jeito que está impressa,
a equação multiplica as densidades em vez de subtraí-las. Duas coisas expõem o
problema:

- uma análise dimensional;
- o cruzamento da equação com o parágrafo que a apresenta e com o apêndice
  técnico da norma, onde ela aparece na forma correta.

Um OCR melhor transcreveria com mais fidelidade uma equação impressa errada,
mas não a tornaria correta. Esse tipo de verificação exige o documento
inteiro, e é mais um motivo para guardar a evidência em vez de uma transcrição
congelada.

## O que o projeto entrega, e o que não entrega

Mesmo com contexto adequado, a IA generativa ainda erra ao consumir o acervo.
Erra muito menos que nas alternativas testadas, e de forma administrável:
documentos críticos podem ser direcionados a formatos de extração melhores.

O Doc2MD **não elimina** o risco de conversão errada. Ele o reduz bastante e,
principalmente, torna o erro **visível** em vez de escondê-lo atrás de uma
saída bem formatada. A inspeção humana em algum ponto do fluxo continua
necessária. Essa é uma conclusão do projeto, não uma pendência para a próxima
versão.

---

As normas citadas aparecem só como identificação. Os trechos curtos servem de
exemplo e crítica. Nenhum documento do acervo é distribuído com este
repositório; veja [direitos e privacidade](direitos-e-privacidade.md).
