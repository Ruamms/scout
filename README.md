<p align="center">
  <img src="assets/scout-logo.png" alt="Scout — nós exploramos, você decide" width="420">
</p>

# Scout

**Nós exploramos. Você decide.**

O scout vai antes. Observa. Lê o terreno. Encontra os perigos. Volta —
e entrega o relatório para quem vai tomar a decisão. É exatamente isso
que este projeto faz com os ativos da bolsa: **lemos os documentos oficiais
para que você não precise garimpar**.

A dúvida que trava todo investidor de FII — *"será que tem algum problema escondido
naquele relatório de 200 páginas?"* — vira uma lista de alertas com a conta, a fonte
e **exatamente o que merece a sua atenção**. A decisão continua sendo sua.

> *EN summary: Scout is an open-source tool that builds a fact-based "x-ray" of Brazilian REITs (FIIs) from official public data (CVM open data, B3/FNET filings, Central Bank series). A deterministic engine computes indicators and auditable red flags; a local LLM (Ollama) reads management reports and extracts quoted facts. Facts with sources — never buy/sell recommendations.*

## O problema

Entender um único FII hoje significa cruzar informes mensais e trimestrais na CVM,
relatórios gerenciais em PDF no FNET, cotação num site, vacância em outro — e torcer
para nenhum deles esconder o critério. Quem faz isso para 5 fundos desiste no terceiro.

## O que o Scout entrega

Um **raio-x por fundo**: indicadores com histórico e explicação para leigos, **red flags
com evidência** ("distribuiu R$ 710M com resultado de R$ 473M — veja a fonte"), os
imóveis com vacância e inadimplência um a um, os outros fundos do mesmo administrador,
os pares do segmento, gráficos comparando com CDI e inflação, calculadoras com dados
reais — e a IA local lendo o relatório gerencial e citando os trechos que importam.

Você ainda vai abrir o PDF de vez em quando — mas vai abrir **o PDF certo, sabendo o
que procurar**.

O princípio cabe em uma frase: **fatos, não dicas**. A decisão é sempre do investidor.

## Por que confiar

Porque nada aqui é caixa-preta:

1. **Todo número sai de código determinístico** sobre dados oficiais (CVM desde 2016, FNET, Banco Central) — nunca de IA. As **9 red flags** têm critérios públicos neste repositório: você pode auditar cada limiar.
2. **A IA só interpreta texto** — roda 100% na sua máquina (Ollama), recebe os indicadores prontos e extrai fatos do relatório **citando os trechos** para você conferir no original. Nunca produz números, nunca opina.
3. **"Não avaliado" é diferente de "aprovado"**: quando falta histórico para uma regra rodar, a tela diz isso — honestidade que gráfico bonito não substitui.

## Fontes de dados

| Fonte | O que fornece |
|---|---|
| [CVM Dados Abertos](https://dados.cvm.gov.br) | Informes mensais e trimestrais de FII (2016+): PL, cotas, rendimentos, imóveis, vacância, resultado financeiro — oficial |
| FNET (B3) | Relatórios gerenciais e fatos relevantes (PDFs oficiais dos fundos) |
| Yahoo Finance | Cotações (atraso de ~15 min em relação ao pregão — limite de toda fonte gratuita) |
| Banco Central (SGS) | CDI e IPCA para os comparativos de rentabilidade |

## Site

O raio-x de todos os FIIs negociáveis, atualizado diariamente via GitHub Actions:
**https://ruamms.github.io/scout/** — índice buscável, página por fundo,
rankings do dia com critérios explícitos.

## Como usar

Com [uv](https://docs.astral.sh/uv/) instalado (`pip install uv`):

```
uv sync
uv run scout atualizar              # baixa os dados oficiais da CVM (1ª vez: ~20 MB)
uv run scout analisar HGLG11        # raio-x no terminal
uv run scout analisar HGLG11 --html # relatório completo com gráficos, no navegador
uv run scout ranking --por dy --sem-alertas   # top 10 por critério explícito
uv run scout site                   # gera o site estático completo
uv run scout ia HGLG11              # IA local lê o relatório gerencial (requer Ollama)
```

Sem argumentos (`uv run scout` ou duplo clique no exe), abre o **modo interativo**, que aceita os mesmos comandos.

### Leitura por IA (opcional, 100% local)

```
winget install Ollama.Ollama
ollama pull qwen2.5:14b     # ou llama3.1:8b para GPUs com menos de 10 GB
uv run scout ia HGLG11
```

Nada sai da sua máquina e não há custo de token. A saída cita os trechos do relatório que sustentam cada fato.

### Gerar o executável (Windows)

Rode `gerar_exe.bat` na raiz do projeto: ele produz um `dist\scout.exe` único que
funciona em qualquer Windows sem Python instalado.

> Nota: antivírus às vezes desconfiam de executáveis PyInstaller recém-gerados
> (falso positivo conhecido). Se o Defender reclamar, é isso.

## Status

Fase 1 (raio-x quantitativo + site) completa · Fase 2 (IA local sobre relatórios) em andamento — acompanhe o [ROADMAP](ROADMAP.md) e a [visão de produto](docs/VISAO.md).

## Apoie

O projeto é gratuito e sem anúncios. Se ele te ajudou: [página de apoio (PIX)](https://ruamms.github.io/scout/apoie.html).

## Aviso legal

Este projeto **não é recomendação de investimento** e seu autor não é analista de valores mobiliários credenciado (Resolução CVM 20/2021). A ferramenta apresenta fatos, indicadores e alertas extraídos de dados públicos, com as respectivas fontes. Rentabilidade passada não garante resultado futuro. Toda decisão de investimento é de responsabilidade exclusiva do investidor.

## Licença

[MIT](LICENSE)
