# Roadmap

Cada etapa é pensada para gerar valor sozinha — e virar conteúdo (post/vídeo) ao ser concluída.

## Fase 1 — Fundação (MVP CLI, foco em FIIs)

- [x] **Coletor CVM** — informes mensais de FII (2016+) baixados para SQLite local (`~/.fato-relevante`), com ticker→CNPJ resolvido pelo ISIN e normalização dos dois vocabulários de coluna (pré e pós Resolução CVM 175)
- [x] **Indicadores** — cotação de mercado (Yahoo Finance, candles mensais desde 2011, sem chave), oscilações 12m e no ano, P/VP atual e média histórica, PL, VP/cota (média ajustada por desdobramento), nº de cotas, valor do ativo, DY mensal (fração→%, com filtro de lixo auto-declarado), cotistas
  - sincronização de cotação é preguiçosa (1x/dia por ticker) e degrada com aviso quando offline
  - pendente para depois: rendimento em R$ por cota, receita (informe trimestral)
- [ ] **Motor de red flags** — regras auditáveis com evidência, ex.: distribuição acima do resultado gerado, diluição relevante sem crescimento de resultado, vacância fora da curva do segmento
- [ ] **Relatório de saída** — raio-x do ativo em Markdown/HTML apresentável (bom de ler e bom de filmar)

## Fase 2 — Camada qualitativa

- [ ] **Coletor FNET** — localizar e baixar o último relatório gerencial e fatos relevantes do fundo
- [ ] **LLM local (Ollama)** — extração de fatos dos relatórios: resumo com citação do trecho-fonte, conectado aos indicadores da Fase 1
- [ ] **Oscilações com contexto** — cruzar variações de cotação com fatos/eventos do período

## Fase 3 — Expansão

- [ ] **Ações** — adaptar coletor e indicadores para demonstrações de companhias abertas (DFP/ITR da CVM)
- [ ] **Comparação entre ativos** — mesmo raio-x lado a lado
- [ ] **API/site** — expor o núcleo via FastAPI; coleta agendada; front

## Princípios que não mudam

- Todo número sai de código determinístico e testável; IA só interpreta texto.
- Toda afirmação tem fonte.
- Fatos e alertas — nunca recomendação de compra ou venda.
