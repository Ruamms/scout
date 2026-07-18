# Fato Relevante

**O raio-x dos ativos da bolsa.**

> *EN summary: Fato Relevante is an open-source tool that builds a fact-based "x-ray" of Brazilian exchange-listed assets (REITs/FIIs first, stocks next) from official public data (CVM open data, B3 filings). A deterministic engine computes indicators and red flags; a local LLM reads management reports and extracts qualitative facts. Facts with sources — never buy/sell recommendations.*

## O que é

Ferramenta open source que monta um raio-x de ativos da bolsa brasileira a partir de **dados públicos oficiais** — começando por FIIs e evoluindo para ações e outras classes.

O princípio do projeto cabe em uma frase: **fatos, não dicas**. A ferramenta mostra o que os dados e os relatórios oficiais dizem sobre um ativo, com fonte para cada afirmação. A decisão de investir é sempre do investidor.

## Como funciona

Duas camadas, com uma fronteira rígida entre elas:

1. **Camada quantitativa (determinística, sem IA)** — baixa o histórico oficial do ativo (informes da CVM, dados da B3), calcula a série de indicadores (evolução de receita, patrimônio, distribuições, emissões de cotas/ações, P/VP...) e roda uma bateria de **red flags auditáveis** — regras explícitas, com a evidência de cada alerta.
2. **Camada qualitativa (LLM local)** — lê relatórios gerenciais e fatos relevantes (PDFs do FNET/CVM) e extrai os fatos importantes em linguagem natural. O modelo **nunca produz números**: recebe os indicadores já calculados como contexto e só interpreta texto.

Números vêm de código. Texto vem de IA. Nunca o contrário.

## Fontes de dados

| Fonte | O que fornece |
|---|---|
| [CVM Dados Abertos](https://dados.cvm.gov.br) | Informes mensais/trimestrais: PL, cotas, rendimentos, receita — histórico completo e oficial |
| FNET (B3) | Relatórios gerenciais, fatos relevantes, atas |
| Fundamentus | Snapshot atual para validação cruzada |
| brapi.dev | Série histórica de cotações |

## Site

O raio-x de todos os FIIs negociáveis, atualizado diariamente via GitHub Actions:
**https://ruamms.github.io/fato-relevante/** — índice buscável, página por fundo,
rankings do dia com critérios explícitos.

## Como rodar

Com [uv](https://docs.astral.sh/uv/) instalado:

```
uv sync
uv run fato analisar ADSH11
```

### Gerar o executável (Windows)

Rode `gerar_exe.bat` na raiz do projeto. Ele sincroniza as dependências e
empacota tudo com PyInstaller num único `dist\fato.exe`, que funciona em
qualquer Windows sem Python instalado:

```
dist\fato.exe analisar ADSH11
```

> Nota: antivírus às vezes desconfiam de executáveis PyInstaller recém-gerados
> (falso positivo conhecido). Se o Defender reclamar, é isso.

## Status

🚧 Em construção — acompanhe o [ROADMAP](ROADMAP.md).

## Aviso legal

Este projeto **não é recomendação de investimento** e seu autor não é analista de valores mobiliários credenciado (Resolução CVM 20/2021). A ferramenta apresenta fatos, indicadores e alertas extraídos de dados públicos, com as respectivas fontes. Rentabilidade passada não garante resultado futuro. Toda decisão de investimento é de responsabilidade exclusiva do investidor.

## Licença

[MIT](LICENSE)
