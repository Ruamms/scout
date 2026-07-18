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
- [x] **M5 — Relatório HTML com gráficos** — página única auto-contida (~15 KB, gráficos SVG gerados em Python puro): cotação × VP/cota, P/VP com média histórica, DY por ano, PL por ano; selo-síntese de 5 níveis (critérios públicos — ver VISAO.md) no HTML e no terminal; data de atualização por fonte; disclaimer; `fato analisar TICKER --html` salva e abre no navegador
- [ ] **M6 — Informe trimestral CVM** — lista de imóveis resumida (por estado + top imóveis por % da receita, com vacância e inadimplência individuais); vacância com histórico; resultado financeiro real → red flag de distribuição exata; red flags de vacância e de "fundo novo"
- [ ] **M7 — Raio-x do administrador** — outros FIIs do mesmo administrador, com idade, segmento e contagem de alertas, linkáveis
- [ ] **M8 — Site estático** — GitHub Actions gera as páginas de todos os FIIs 1x/dia e publica no GitHub Pages

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
