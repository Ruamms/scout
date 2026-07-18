# Visão de produto

**v1 = 100% FIIs.** Outras classes de ativos só entram quando o raio-x de FII estiver completo (dados, visual e distribuição). Este documento registra para onde o produto evolui e o que aprendemos das referências de mercado.

## Princípios (não mudam)

1. Todo número sai de código determinístico e testável; IA só interpreta texto.
2. Toda afirmação tem fonte e data.
3. Fatos e alertas — nunca recomendação de compra ou venda.
4. "Não olhei" é diferente de "olhei e está ok": o que não foi avaliado aparece como não avaliado.

## O que as referências fazem (inventário de 18/07/2026, página do BTLG11)

### Investidor10
- 5 cards de topo: Cotação, DY 12M, P/VP, Liquidez diária, Variação 12M.
- Gráficos: cotação (1D–15A), comparação com índices, DY, dividendos (mensal/anual, até MAX), vacância (por ano até 2016), pizza de imóveis por estado, mini-gráfico de área por indicador.
- Histórico ANUAL de indicadores em tabela (Atual, 2025, 2024…): valor de mercado, P/VP, DY, liquidez, PL, VP/cota, vacância, cotistas, cotas.
- Checklist buy-and-hold com 8 critérios objetivos (ex.: +5 anos de bolsa, DY 5a > 8%, liquidez > R$ 700 mil/dia, +20 mil cotistas, PL > R$ 1 bi, 5+ imóveis, vacância física/financeira 12m < 10%).
- Lista de imóveis: pizza por estado + cards resumidos (nome, estado, área) com "ver mais".
- Comparação com pares (mesmo tipo/segmento) e vs média do segmento.
- Tabela de proventos (tipo, data com, pagamento, valor), comunicados, notícias, FAQ, avaliação por estrelas.
- Data de atualização: só um tooltip na cotação.

### AUVP Analítica
- Ficha compacta (segmento, tipo tijolo/papel, taxa adm, gestão, PL, VP/cota, vacância, nº de imóveis).
- Indicadores: DY, P/VP, VPA, PL, FFO Yield, FFO, Imóveis/PL, valor de mercado, alavancagem/PL, vacância física E financeira, taxa adm.
- Carteira de imóveis: donut por estado + card por imóvel com área e **vacância individual**.
- Dividendos: barras (R$) + linha (DY%) no mesmo gráfico, por ano.
- Rentabilidade vs CDI, IPCA e IFIX.
- **Selo de 4 níveis** (Azulim/Viável/Requer atenção/Bomba — "viável para estudo") — principal produto, atrás de paywall; critérios não são públicos.
- Simuladores (bola de neve, rentabilidade), comparador, votação da comunidade.
- Disclaimer: "fins informativos… não tem o objetivo de sugerir compra ou venda".
- **Não mostra data de atualização dos dados nem administrador/gestor.**

### Onde nós ganhamos (dados que eles não mostram ou escondem)
- % da receita do fundo POR imóvel e **inadimplência por imóvel** (informe trimestral CVM — nenhum dos dois mostra inadimplência).
- Critérios de classificação 100% públicos e auditáveis (AUVP esconde os dela).
- Data de atualização de cada fonte, sempre visível.
- Cruzamento por administrador (nenhum dos dois faz).
- Estado explícito de "não avaliado" para fundos novos.

## Backlog de produto (ordem de implementação)

### Fase 1 — v1 FII (em andamento)
- [x] Coletor CVM mensal, cotações, indicadores, motor de red flags (milestones 1–4)
- [ ] **M5 — Relatório HTML com gráficos**: página única auto-contida (SVG gerado em Python, sem lib JS externa) com: cotação, dividendos/DY (barras+linha), PL anual, P/VP vs média; selo-síntese dos alertas; data de atualização de cada fonte no cabeçalho; disclaimer.
- [ ] **M6 — Informe trimestral CVM**: lista de imóveis resumida (pizza por estado + top imóveis por % da receita, com vacância e inadimplência individuais); vacância física/financeira com histórico; resultado financeiro real (`Rendimentos_Declarados` vs `Resultado_Financeiro_Liquido` → red flag de distribuição EXATA, sem proxy); receita; red flag de vacância; regra "fundo novo" (<24 meses de histórico = ponto de atenção explícito).
- [ ] **M7 — Raio-x do administrador**: armazenar administrador (já vem no informe mensal); na página do fundo, listar outros FIIs do mesmo administrador com idade, segmento e contagem de alertas, cada um linkável ("gestor administra outros N fundos: XXXX11 (8 anos, logística, sem alertas)…").
- [ ] **M8 — Site estático**: GitHub Actions roda o coletor 1x/dia, gera a página HTML de todos os FIIs e publica no GitHub Pages (grátis). Página índice com busca simples client-side.

### Selo-síntese (decisão de design)
Inspirado no selo da AUVP, mas com duas diferenças de princípio: os critérios são públicos (é literalmente o resultado do motor de red flags) e o texto é factual:
- **Sem alertas** (verde) — todas as regras avaliadas, nenhuma disparou
- **Alertas leves** (amarelo) — só alertas de severidade baixa
- **Requer atenção** (laranja) — algum alerta de severidade média
- **Alerta grave** (vermelho) — algum alerta de severidade alta
- **Histórico insuficiente** (cinza) — regras demais não avaliadas para sintetizar (fundos novos)

Nunca usar linguagem de veredito de investimento ("bomba", "compre"). O selo resume os alertas; os alertas citam fonte. Isso mantém o produto no campo informativo (fora do escopo de recomendação da Resolução CVM 20).

### Fase 2 — Camada qualitativa (IA local)
- Coletor FNET: relatório gerencial + fatos relevantes.
- LLM local (Ollama) extrai fatos com citação do trecho; conecta oscilações a eventos.
- Gestor (pessoa jurídica) vem do FNET/cadastro → enriquece o raio-x do administrador do M7.

### Fase 3 — Outras classes
- **Ações**: DFP/ITR da CVM (demonstrações), Formulário de Referência (histórico de diretoria/CEO — permite o recurso "geriu a empresa X no período Y, veja o desempenho no período", sempre factual, sem imputar má-fé); mesmas regras de red flag adaptadas (diluição, payout, governança).
- **ETFs**: composição, taxa, tracking error.
- **Renda fixa/CDB**: alerta de concentração acima do teto do FGC (R$ 250 mil por CPF por instituição), saúde do emissor via IF.data (Banco Central).

### Ideias registradas (sem prioridade definida)
- Checklist buy-and-hold com critérios públicos (estilo Investidor10, mas com fonte por critério).
- Comparação com pares do mesmo segmento e vs média do segmento.
- Rentabilidade vs CDI/IPCA/IFIX.
- Tabela de proventos com histórico completo.
- FAQ por ativo (gerada das próprias métricas).

## Distribuição / site
- v1 site: **GitHub Pages + GitHub Actions** (grátis, sem servidor, repo público já dá tudo). Limites confortáveis: 1 GB de site, ~100 GB/mês de banda.
- Quando precisar de busca server-side, login ou dados por usuário: migrar para Cloudflare Pages (estático, grátis, mais banda) ou FastAPI num host pequeno — o núcleo Python já foi desenhado para isso.
