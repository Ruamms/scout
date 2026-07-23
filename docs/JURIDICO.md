# Análise de risco jurídico — função por função

**Data:** 23/07/2026 · **Escopo:** todas as classes (FIIs, ETFs, ações, bancos/CDB) e toda função publicada.
**Aviso importante:** este documento é um MAPA DE RISCOS feito por engenharia, não parecer jurídico.
As mitigações aplicadas reduzem exposição, mas a recomendação permanente é validar com advogado
(direito de mercado de capitais + LGPD) antes de qualquer divulgação ampla ou monetização.

## 1. Regulatório CVM — o risco central do projeto

**Risco:** a Resolução CVM 20/2021 exige credenciamento de quem elabora "relatórios de análise"
(textos, estudos ou análises sobre valores mobiliários específicos que possam AUXILIAR ou INFLUENCIAR
decisão de investimento). A Resolução CVM 19/2021 regula consultoria de valores mobiliários
(recomendação personalizada). Selos, red flags e rankings falam de ativos específicos — a linha é cinzenta.

**Posição do projeto (mitigações implementadas):**
- Nenhuma recomendação de compra/venda/manutenção, nunca; nenhum preço-alvo NOSSO (as calculadoras
  Graham/Bazin/Gordon computam fórmulas PÚBLICAS com premissas digitadas PELO USUÁRIO, opt-in,
  com aviso antes do botão — ferramenta aritmética, não análise).
- Selo = síntese MECÂNICA de regras determinísticas publicadas em código aberto, sobre dados oficiais —
  natureza de "screener"/organizador de dados públicos (mesma família de Fundamentus/StatusInvest),
  não de relatório opinativo.
- "Não é recomendação de investimento" em todas as páginas, rodapés e comparadores ("sem vencedor").
- Rankings rotulados "fatos ordenados com critério explícito — não recomendação".
- A leitura por IA extrai fatos COM CITAÇÃO do documento oficial; proibida de gerar número novo ou opinião.

**Pendências recomendadas:** consulta formal a advogado de mercado de capitais sobre o enquadramento
dos selos (é o ponto de maior incerteza); se um dia houver monetização por indicação de corretora,
o enquadramento muda (agente autônomo/influenciador — Res. CVM 178 e ofícios sobre finfluencers).

## 2. Responsabilidade civil — difamação/dano à imagem (todas as classes)

**Risco:** um emissor (banco, fundo, empresa) com "Alerta grave" pode alegar dano à reputação.
Bancos são o caso mais sensível (alerta pode ser lido como "vai quebrar" e virar corrida).

**Mitigações implementadas:**
- Toda flag carrega FATO + EVIDÊNCIA NUMÉRICA + FONTE NOMINAL (documento público específico:
  IF.data/BCB com relatório e trimestre; DFP/ITR/FRE/CVM com ano; informe CVM com competência).
  A verdade factual documentada é a defesa clássica contra difamação.
- Redação factual, sem juízo: "Basileia de X% em T" e não "banco ruim/arriscado/insolvente".
  A flag nova de balanço declara EXPLICITAMENTE que é fato de composição, não acusação, e cita a
  explicação alternativa legítima (modelos de pagamento). Decisão deliberada: NUNCA nomear casos de
  fraude (ex.: Banco Master) na página de outro emissor — comparar banco vivo a fraude é o risco máximo.
- Selo com precedência mecânica e descrição do critério no tooltip; critérios públicos no GitHub.
- Canal de correção em TODAS as páginas (botão reportar) — direito de resposta espontâneo; erros de
  fonte ou processamento são corrigíveis e o histórico fica no Git.
- "Sem dado = não avaliada", nunca acusação por ausência.

**Pendências recomendadas:** processo escrito de resposta a contestação de emissor (SLA de correção);
considerar aviso nas páginas de selo grave explicitando "síntese mecânica de regras públicas".
FEITO em 23/07/2026: página pública de metodologia + aviso legal linkada em todo o site.

## 3. LGPD — dados pessoais (ações: "Quem manda na empresa")

**O que tratamos:** nome, cargo, órgão, experiência declarada e CPF de administradores de companhias
abertas, extraídos do FRE (documento público OBRIGATÓRIO publicado pela CVM em dados abertos).

**Análise:** ainda que públicos, são dados pessoais — o tratamento precisa de base legal (art. 7º LGPD).
Enquadramento defensável: legítimo interesse (IX) e/ou execução de política pública de transparência
do mercado (o dado é publicado pela CVM por força de regulação para exatamente este fim — informar
o público investidor). Princípios aplicados:
- **Minimização:** o CPF NUNCA é exibido nem exportado — é só chave interna de cruzamento (há teste
  automatizado garantindo que nenhum CPF aparece em página gerada).
- **Finalidade:** exibimos exatamente o que o FRE publica (cargo/experiência), com a fonte citada.
- **Transparência:** página de metodologia declara o tratamento e o canal de contato do titular.

**Pendências recomendadas:** avaliar com advogado a necessidade de RIPD (relatório de impacto);
definir e-mail/registro de encarregado (DPO) se o projeto crescer; atender pedido de titular
(remoção do site não remove da CVM — explicar isso na resposta padrão).

## 4. Fontes de dados — termos de uso e propriedade

- **CVM, BCB (IF.data/SGS), ANBIMA (mercado secundário público), FNET/B3 (documentos):** dados
  abertos/públicos, uso ok com atribuição (feita em todas as páginas).
- **B3 COTAHIST (série histórica) e APIs do site da B3 (fundsListedProxy, cotação RF, eventos):**
  arquivos e endpoints públicos, MAS a B3 licencia market data comercialmente. Exibimos apenas
  FECHAMENTO OFICIAL D-1 (nunca tempo real, decisão registrada na VISAO) — o risco é baixo,
  porém a redistribuição pública de dados da B3 é o ponto mais sensível desta seção.
  **Recomendado:** consulta aos termos de market data da B3 antes de monetizar; se necessário,
  migrar exibição de preço para "variação %" (fato derivado) ou licenciar.
- **Rendimentos/proventos (FNET, avisos estruturados):** documentos públicos de divulgação obrigatória.
- Nenhum conteúdo de terceiros protegido (textos de relatórios gerenciais são LIDOS pela IA, que
  produz resumo próprio com citação curta — uso de trecho curto com finalidade informativa).

## 5. Calculadoras e conteúdo tributário

Gross-up CDB×LCI/LCA, cobertura FGC, Graham, Bazin, Gordon: aritmética de fórmulas públicas com
premissas do usuário, opt-in, aviso antes do botão, sem veredito. Tabelas de IR citadas com fonte
legal (IR regressivo, isenção FII/ações R$ 20 mil — Lei 14.754/2023 etc.). Não é consultoria
tributária — o texto informa a REGRA GERAL com fonte, nunca o caso concreto do leitor.

**Regra do FGC:** citamos a Res. CMN 4.222 (R$ 250 mil/CPF/conglomerado, teto R$ 1 mi/4 anos) e
derivamos a adesão da natureza da instituição (obrigatória por lei). O texto NÃO garante cobertura
de caso concreto ("a liquidação leva meses"; quem paga e decide é o FGC).

## 6. IA local (leituras de documentos)

Risco: resumo errado sobre fato relevante pode induzir decisão. Mitigações: prompt restrito a
extração com citação; link para TODOS os originais; aviso visível de que "pode conter erros de
leitura"; aviso de idade da leitura (>40 dias); nunca gera números novos (teste garante padrão).

## 7. Analytics e privacidade do visitante

GoatCounter sem cookies, dados agregados e anônimos, termo de busca sanitizado a [A-Z0-9] (texto
livre descartado). Sem banner porque não há cookie nem identificação — nota de transparência na
página de apoio. Baixo risco.

## 8. Marca e nome

"Scout" é palavra comum e há produtos homônimos em outras categorias. Antes de divulgação ampla:
busca no INPI e avaliação de registro (classe 36/42). Risco atual baixo (projeto pessoal, sem marca
de terceiro copiada), mas barato de resolver cedo.

## 9. Repositório público (GitHub)

O ROADMAP/dossiês citam casos reais (Banco Master, Americanas, IRB, Oi) como BENCHMARK de regras.
Regra de redação: fatos públicos noticiados/oficiais (liquidação extrajudicial decretada, opinião
adversa de auditor) com termos neutros — evitar "golpe/fraude" como afirmação própria; se citar,
atribuir ("segundo o BCB/imprensa, investigado por..."). Revisado em 23/07/2026: nenhum termo
acusatório nos textos publicados do site; documentos internos usam linguagem factual.

## Resumo das ações aplicadas em 23/07/2026

1. Flag de banco aprovada publicada com fonte nominal (relatório + trimestre) e redação "fato, não acusação".
2. Link "confira na fonte oficial (IF.data)" nas páginas de banco.
3. Página pública `metodologia.html` (metodologia + aviso legal + LGPD + canal de correção) linkada
   no menu de todo o site.
4. Varredura de linguagem: nenhum termo acusatório/recomendatório nos textos do site; disclaimers
   presentes em todas as classes.

## Checklist para o dono (fora do código)

- [ ] Consulta a advogado (mercado de capitais): enquadramento dos selos ante a Res. CVM 20/2021.
- [ ] Consulta LGPD: base legal formal + resposta padrão a titulares (administradores de cias).
- [ ] Termos de market data da B3 (antes de monetizar).
- [ ] Busca de marca no INPI.
- [ ] Definir e-mail de contato público (correções e titulares LGPD).
