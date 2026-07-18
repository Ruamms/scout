# Fato Relevante

**O raio-x dos ativos da bolsa.**

> *EN summary: Fato Relevante is an open-source tool that builds a fact-based "x-ray" of Brazilian REITs (FIIs) from official public data (CVM open data, B3/FNET filings, Central Bank series). A deterministic engine computes indicators and auditable red flags; a local LLM (Ollama) reads management reports and extracts quoted facts. Facts with sources — never buy/sell recommendations.*

## O que é

Ferramenta open source que monta um raio-x de FIIs a partir de **dados públicos oficiais** (ações e outras classes no roadmap). O princípio cabe em uma frase: **fatos, não dicas**. Tudo o que aparece na tela tem fonte, data e critério público — a decisão de investir é sempre do investidor.

## Como funciona

Duas camadas, com uma fronteira rígida entre elas:

1. **Camada quantitativa (determinística, sem IA)** — baixa o histórico oficial (informes mensais e trimestrais da CVM desde 2016), calcula os indicadores (PL, VP/cota ajustado por desdobramento, P/VP, DY, vacância ponderada por área, diluição…) e roda **9 red flags auditáveis** — cada alerta traz o fato, a conta que o disparou e a fonte. Um **selo de síntese** (Sem alertas → Alerta grave) resume o resultado com critérios 100% públicos.
2. **Camada qualitativa (IA local)** — baixa o último relatório gerencial no FNET e um LLM rodando **na sua máquina** (Ollama) extrai os fatos citando os trechos. O modelo **nunca produz números**: recebe os indicadores prontos como contexto e só interpreta texto.

Números vêm de código. Texto vem de IA. Nunca o contrário.

## O que o raio-x mostra

Indicadores com histórico e glossário para leigos (ícones "?"), red flags com evidência, **imóveis do fundo** com vacância e inadimplência individuais, **outros fundos do mesmo administrador** (cada um com seu selo), **pares do segmento** com a média, gráficos (cotação × VP, P/VP, DY em R$/cota, PL, vacância, rentabilidade × CDI × IPCA com e sem reinvestimento) e calculadoras interativas — incluindo "e se eu tivesse investido?", que usa o passado real, não projeção.

## Fontes de dados

| Fonte | O que fornece |
|---|---|
| [CVM Dados Abertos](https://dados.cvm.gov.br) | Informes mensais e trimestrais de FII (2016+): PL, cotas, rendimentos, imóveis, vacância, resultado financeiro — oficial |
| FNET (B3) | Relatórios gerenciais e fatos relevantes (PDFs oficiais dos fundos) |
| Yahoo Finance | Cotações (atraso de ~15 min em relação ao pregão — limite de toda fonte gratuita) |
| Banco Central (SGS) | CDI e IPCA para os comparativos de rentabilidade |

## Site

O raio-x de todos os FIIs negociáveis, atualizado diariamente via GitHub Actions:
**https://ruamms.github.io/fato-relevante/** — índice buscável, página por fundo,
rankings do dia com critérios explícitos.

## Como usar

Com [uv](https://docs.astral.sh/uv/) instalado (`pip install uv`):

```
uv sync
uv run fato atualizar              # baixa os dados oficiais da CVM (1ª vez: ~20 MB)
uv run fato analisar HGLG11        # raio-x no terminal
uv run fato analisar HGLG11 --html # relatório completo com gráficos, no navegador
uv run fato ranking --por dy --sem-alertas   # top 10 por critério explícito
uv run fato site                   # gera o site estático completo
uv run fato ia HGLG11              # IA local lê o relatório gerencial (requer Ollama)
```

Sem argumentos (`uv run fato` ou duplo clique no exe), abre o **modo interativo**, que aceita os mesmos comandos.

### Leitura por IA (opcional, 100% local)

```
winget install Ollama.Ollama
ollama pull qwen2.5:14b     # ou llama3.1:8b para GPUs com menos de 10 GB
uv run fato ia HGLG11
```

Nada sai da sua máquina e não há custo de token. A saída cita os trechos do relatório que sustentam cada fato.

### Gerar o executável (Windows)

Rode `gerar_exe.bat` na raiz do projeto: ele produz um `dist\fato.exe` único que
funciona em qualquer Windows sem Python instalado.

> Nota: antivírus às vezes desconfiam de executáveis PyInstaller recém-gerados
> (falso positivo conhecido). Se o Defender reclamar, é isso.

## Status

Fase 1 (raio-x quantitativo + site) completa · Fase 2 (IA local sobre relatórios) em andamento — acompanhe o [ROADMAP](ROADMAP.md) e a [visão de produto](docs/VISAO.md).

## Apoie

O projeto é gratuito e sem anúncios. Se ele te ajudou: [página de apoio (PIX)](https://ruamms.github.io/fato-relevante/apoie.html).

## Aviso legal

Este projeto **não é recomendação de investimento** e seu autor não é analista de valores mobiliários credenciado (Resolução CVM 20/2021). A ferramenta apresenta fatos, indicadores e alertas extraídos de dados públicos, com as respectivas fontes. Rentabilidade passada não garante resultado futuro. Toda decisão de investimento é de responsabilidade exclusiva do investidor.

## Licença

[MIT](LICENSE)
