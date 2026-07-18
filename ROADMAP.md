# Roadmap

Cada etapa é pensada para gerar valor sozinha — e virar conteúdo (post/vídeo) ao ser concluída.
A visão de produto completa (referências de mercado, backlog e decisões de design) está em [docs/VISAO.md](docs/VISAO.md). **v1 = 100% FIIs.**

## Fase 1 — Fundação (MVP CLI, foco em FIIs)

- [x] **Coletor CVM** — informes mensais de FII (2016+) baixados para SQLite local (`~/.fato-relevante`), com ticker→CNPJ resolvido pelo ISIN e normalização dos dois vocabulários de coluna (pré e pós Resolução CVM 175)
- [x] **Indicadores** — cotação de mercado (Yahoo Finance, candles mensais desde 2011, sem chave), oscilações 12m e no ano, P/VP atual e média histórica, PL, VP/cota (média ajustada por desdobramento), nº de cotas, valor do ativo, DY mensal (fração→%, com filtro de lixo auto-declarado), cotistas
  - sincronização de cotação é preguiçosa (1x/dia por ticker) e degrada com aviso quando offline
  - pendente para depois: rendimento em R$ por cota, receita (informe trimestral)
- [x] **Motor de red flags** — 6 regras auditáveis, cada uma com severidade, evidência numérica e fonte; regras sem histórico suficiente aparecem como "não avaliadas" (nunca como aprovação silenciosa)
  - distribuição acima da variação patrimonial · diluição destrutiva por emissão · VP/cota em queda relevante · base de cotistas (mínimo legal de 100 para isenção de IR, Lei 14.754/2023) · P/VP fora da faixa histórica · rendimentos irregulares
  - pendente para leva 2: vacância fora da curva (precisa do informe trimestral da CVM)
- [x] **M5 — Relatório HTML com gráficos** — página única auto-contida (gráficos SVG gerados em Python puro): cotação × VP/cota, P/VP com média histórica, DY e PL com alternância **Ano/Mês**, e **rentabilidade acumulada com proventos × CDI × IPCA** (fontes: Yahoo ajustado + SGS/Banco Central) em janelas de 12 meses/5 anos/máximo; selo-síntese de 5 níveis (critérios públicos — ver VISAO.md) no HTML e no terminal; data de atualização por fonte; disclaimer; `fato analisar TICKER --html` salva e abre no navegador
  - pendente: linha do IFIX no gráfico de rentabilidade (sem fonte pública programável hoje — Yahoo não tem histórico do índice, Stooq exige desafio JS; candidata futura: arquivos oficiais da B3)
- [x] **M6 — Informe trimestral CVM** — coletor dos informes trimestrais (2016+); tabela de imóveis com área, % da receita, vacância e inadimplência POR IMÓVEL (terminal + HTML); indicador e gráfico de vacância ponderada por área; 3 red flags novas: **rendimentos vs resultado financeiro (exata, substitui o proxy)**, **vacância alta** e **fundo novo (<24 meses)**; motor ganhou supressão de regra (proxy some quando a exata roda)
  - gotcha de escala CVM: no mesmo arquivo, vacância/inadimplência são FRAÇÃO (1.0=100%) e % receita é PERCENTUAL (0-100)
  - pendente: agrupamento por estado (parsing de endereço), setores/inquilinos, e usar reservas acumuladas para refinar a regra de distribuição
- [x] **M7 — Raio-x do administrador** — seção "Administrador" no terminal e no HTML: outros FIIs da mesma casa com ticker (derivado do ISIN), idade, segmento e **selo individual** (calculado sem cotação), com link cruzado entre relatórios; migração automática da base (recarrega informes mensais para preencher o administrador histórico)
- [ ] **M8 — Ranking / pesquisa avançada** — `fato ranking`: top N fundos por DY/P-VP/PL/cotistas com filtro "sem alertas" e por segmento; critério sempre explícito na saída; inclui a comparação com pares do mesmo segmento na página do fundo (estilo "comparando com outros FIIs")
- [ ] **M9 — Site estático** — GitHub Actions gera as páginas de todos os FIIs + rankings 1x/dia e publica no GitHub Pages

## Fase 2 — Camada qualitativa

- [ ] **Coletor FNET** — localizar e baixar o último relatório gerencial e fatos relevantes do fundo
- [ ] **LLM local (Ollama)** — extração de fatos dos relatórios: resumo com citação do trecho-fonte, conectado aos indicadores da Fase 1
- [ ] **Oscilações com contexto** — cruzar variações de cotação com fatos/eventos do período
- [ ] **Gestor** — identificar a gestora via FNET e enriquecer o raio-x do administrador

## Fase 3 — Outras classes (depois da v1 FII completa)

- [ ] **Ações** — DFP/ITR da CVM + Formulário de Referência (histórico de diretoria, sempre factual)
- [ ] **ETFs** — composição, taxa, tracking error
- [ ] **Renda fixa/CDB** — alerta de concentração acima do teto do FGC (R$ 250 mil) e saúde do emissor (IF.data/BCB)
- [ ] **Comparação entre ativos** — mesmo raio-x lado a lado
- [ ] **API/site dinâmico** — expor o núcleo via FastAPI quando o site estático não bastar

## Princípios que não mudam

- Todo número sai de código determinístico e testável; IA só interpreta texto.
- Toda afirmação tem fonte.
- Fatos e alertas — nunca recomendação de compra ou venda.
