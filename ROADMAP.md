# Roadmap

Cada etapa é pensada para gerar valor sozinha — e virar conteúdo (post/vídeo) ao ser concluída.

## Fase 1 — Fundação (MVP CLI, foco em FIIs)

- [ ] **Coletor CVM** — baixar e cachear os informes mensais/trimestrais de FIIs dos dados abertos da CVM (histórico completo de um fundo a partir do ticker/CNPJ)
- [ ] **Indicadores** — série histórica calculada: evolução de PL, VP/cota, receita, distribuições, número de cotas (diluição por emissões), P/VP com cotação
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
