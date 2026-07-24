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
- **Selo de 4 níveis** com enquadramento "viável para estudo" — principal produto, atrás de paywall; critérios não são públicos.
- Simuladores (bola de neve, rentabilidade), comparador, votação da comunidade.
- Disclaimer no rodapé posicionando o site como informativo, sem sugestão de compra/venda.
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
- [ ] **M8 — Ranking / pesquisa avançada**: `scout ranking` varre a base inteira (motor de red flags roda para todos os fundos — é só SQLite + aritmética) e responde consultas como "10 fundos sem alertas com maior DY 12m", "10 sem alertas com menor P/VP", "10 com maior PL"; filtros combináveis (`--sem-alertas`, `--segmento`, `--top N`, `--por dy|pvp|pl|cotistas`). Rankings que dependem de cotação usam os tickers com cotação em cache (o site do M9 terá todas). Ranking é fato ordenado com critério explícito — não é recomendação, e o critério aparece no cabeçalho da saída.
- [ ] **M9 — Site estático**: GitHub Actions roda o coletor 1x/dia, gera a página HTML de todos os FIIs + páginas de ranking e publica no GitHub Pages (grátis). Página índice com busca simples client-side. Pré-requisito: revisar fonte de cotações (ver revisão de propriedade intelectual).

### Selo-síntese (decisão de design)
Inspirado no selo da AUVP, mas com duas diferenças de princípio: os critérios são públicos (é literalmente o resultado do motor de red flags) e o texto é factual:
- **Sem alertas** (verde) — todas as regras avaliadas, nenhuma disparou
- **Alertas leves** (amarelo) — só alertas de severidade baixa
- **Atenção** (laranja) — algum alerta de severidade média
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

### Raio-x do imóvel — camada de risco geográfico (pós-M6, incremental)
Todo alerta de imóvel segue o padrão do produto: fato + fonte + data, e **nunca aparece sozinho — sempre pareado com o desfecho observado** (vacância/inadimplência real do imóvel), como argumento ou contra-argumento: "apesar do histórico de enchentes no município, a vacância do imóvel está abaixo da média do segmento" / "vacância alta, possivelmente ligada a fator estrutural do município (população de 40 mil hab.)".

1. **Já no M6 (sem fonte nova)**: concentração de receita por imóvel e por inquilino (risco monoinquilino), vacância e inadimplência individuais.
2. **Desastres naturais por município** — S2iD/Atlas Digital de Desastres (decretos oficiais de emergência/calamidade por município, com tipo e data); cruzar com o endereço do imóvel do informe trimestral. Ex.: "município com N decretos por enchente desde 2016".
3. **Mercado local restrito** — população do município (IBGE) × % da receita do fundo no imóvel.
4. **Idade/retrofit/sinistros do imóvel** — não existe estruturado; é extraído dos relatórios gerenciais e fatos relevantes pela camada de IA (Fase 2), sempre com citação do trecho.
5. **Criminalidade** — explorar com MUITA cautela e prioridade baixa: apenas agregado municipal de fonte oficial (Atlas da Violência/IPEA), citado como estatística com ano; nunca rotular área ("perigosa"). Risco reputacional/jurídico alto; só entra se agregar valor claro.

### Comparador de instituições financeiras (ideia futura, pós-v1)
Tela para ajudar o leigo a decidir onde abrir conta, começando **apenas por bancos S1** (segmentação oficial do BCB, Res. 4.553 — os maiores e mais supervisionados):
- Tarifas por serviço (transferência, manutenção mensal, custódia...) — fonte oficial: dados abertos de tarifas bancárias do Banco Central (API Olinda), por instituição e serviço.
- Prazo de liquidação/disponibilidade do dinheiro (D+0 vs D+2 — escopo exato a definir: resgate, transferência ou repasse de corretora).
- Qualquer taxa recorrente, sempre com valor, fonte e data da coleta.
- Mesmo princípio do resto do produto: tabela de fatos comparáveis, sem "melhor banco" — o critério de ordenação é do usuário.

### Ideias registradas (sem prioridade definida)
- Checklist buy-and-hold com critérios públicos (estilo Investidor10, mas com fonte por critério).
- Comparação com pares do mesmo segmento e vs média do segmento.
- Rentabilidade vs CDI/IPCA/IFIX.
- Tabela de proventos com histórico completo.
- FAQ por ativo (gerada das próprias métricas).

## Revisão de propriedade intelectual (18/07/2026)

Auditoria do que usamos das referências (Investidor10, AUVP) e das fontes:

- **O que é livre**: ideias e funcionalidades (gráficos, toggles ano/mês, comparação com benchmarks, checklist, ranking) não são protegidas por copyright — só a expressão delas. Todo o nosso código, textos, CSS e visual são originais.
- **O que evitamos de propósito**: nomes dos selos da AUVP (nossos níveis têm nomes e critérios próprios; "Requer atenção" foi renomeado para "Atenção" por coincidir com rótulo deles); textos e thresholds do checklist do Investidor10 (quando implementarmos, critérios e redação próprios); qualquer asset (ícone, imagem, trecho de página) das referências — nada foi copiado para o repo.
- **Citação de concorrentes**: mencionar Investidor10/AUVP em documentação de análise é uso nominativo legítimo; não usar as marcas deles na interface do produto.
- **Dados**: CVM e Banco Central são dados públicos oficiais (uso livre). ~~Yahoo Finance é o ponto de atenção~~ — **RESOLVIDO em 19/07/2026**: as cotações migraram para a Série Histórica oficial da B3 (COTAHIST): fechamento D-1, um arquivo cobre a base inteira, ajustes de desdobramento/proventos calculados por código auditável. O Yahoo saiu do projeto; não há mais dependência de API não-oficial.
- **Nossa marca**: o produto nasceu como "Fato Relevante" (termo genérico de mercado) e foi **renomeado para "Scout" em 18/07/2026** — motivos: o nome antigo nomeava o objeto que o produto lê (ambíguo em conversa e impossível de rankear em busca, que devolve os comunicados reais), e "Scout" funciona como marca-empresa para além de FIIs. Pendência do rebrand (só se o projeto um dia deixar de ser puramente educacional): busca no INPI e domínio próprio (scout.com.br está tomado).

## Natureza do projeto (decisão de 23/07/2026)

O Scout é um **projeto particular, de cunho educacional** — um estudo aberto de desenvolvimento de
software sobre dados públicos do mercado. **Sem fins comerciais**: sem anúncios, sem doações, sem
venda de nada. A infraestrutura é gratuita (GitHub Pages) e o custo é zero por desenho. Estratégias
antigas de sustentação financeira foram descartadas e removidas deste documento.

## Distribuição / site
- v1 site: **GitHub Pages + GitHub Actions** (grátis, sem servidor, repo público já dá tudo). Limites confortáveis: 1 GB de site, ~100 GB/mês de banda.
- Quando precisar de busca server-side, login ou dados por usuário: migrar para Cloudflare Pages (estático, grátis, mais banda) ou FastAPI num host pequeno — o núcleo Python já foi desenhado para isso.
