# Ações — dossiê de planejamento (Fase 4)

Registrado em 20/07/2026, ANTES de qualquer código — mesmo método dos ETFs:
entender → mapear fontes → roadmap → só então implementar. **Nada aqui está
implementado**; é o material de decisão para quando a vertical começar.

## Por que Ações é a vertical mais difícil (e mais valiosa)

FIIs e ETFs são fundos: a CVM padroniza os informes e o "produto" é
comparável. Ação é uma EMPRESA: balanço com dezenas de linhas, setores com
métricas próprias (banco não tem EBITDA; seguradora tem sinistralidade),
eventos societários complexos. O risco de virar "mais um site de múltiplos"
é alto — o diferencial do Scout tem que continuar sendo o mesmo: **ler os
documentos que ninguém lê e transformar em fato com fonte**.

## Onde o Scout pode ser único (tese do produto)

1. **Formulário de Referência (FRE) lido por IA** — o documento mais rico e
   menos lido do mercado: histórico da DIRETORIA e conselho (o "golpe comum"
   que o dono do produto citou desde o dia 1: rastrear pessoas que passaram
   por empresas problemáticas), processos judiciais relevantes, transações
   com partes relacionadas, remuneração da administração. Ninguém oferece
   isso de graça em linguagem de leigo.
2. **Parecer do auditor nas DFs** — já temos o classificador determinístico
   (NBC TA); nas empresas ele é AINDA mais valioso (ressalva em cia aberta é
   evento grave). Reuso direto do `parecer.py`.
3. **Fatos relevantes e comunicados por IA** — pipeline pronto (Ollama local),
   muda só a fonte (empresas usam o sistema IPE/RAD da CVM, não o FNET).
4. **Red flags societárias auditáveis** — diluição por emissões, recompra vs
   emissão, dividendos insustentáveis vs lucro/caixa, auditor trocado com
   frequência, atraso na entrega de DFs, republicação de balanço.

## Resultado dos probes do A1 (20/07/2026 — fontes VALIDADAS com dados reais)

- **Modelo emissor→papéis implementado** (`coleta/empresas.py`, 1ª parte do A1):
  95 emissores do IBrX-100, 129 papéis, 0 sem match; `codeCVM` é a chave que
  liga a B3 aos datasets CIA_ABERTA da CVM; cadastro CVM casou 100% por CNPJ
  (setor, situação e AUDITOR para todos).
- **DFP/ITR são leves** (12,7/9,9 MB por ano zipado) e trazem MAIS que o
  esperado: `dfp_cia_aberta_parecer_AAAA.csv` tem o PARECER DO AUDITOR em
  texto estruturado (A3 sem PDF!) e `composicao_capital` tem o nº de ações.
- **FRE em dados abertos** cobre: conselho/diretoria (`administrador_membro_
  conselho_fiscal`), transações com partes relacionadas, posição acionária,
  remuneração, auditor, relações familiares. NÃO cobre processos judiciais
  (seção 4.3+ só no PDF/IA — nuance do A5).
- **IPE 2026 ainda não publicado** (último zip é 2025) — fatos relevantes do
  ano corrente precisarão de outra rota no A5 (investigar frente RAD/CVM).
- **Eventos societários e proventos**: `listedCompaniesProxy/
  GetListedSupplementCompany({issuingCompany})` → `stockDividends` (label
  DESDOBRAMENTO/BONIFICACAO com factor = % de ações novas; GRUPAMENTO com
  factor = razão direta <1, ex. AMER 100:1 = 0,01), `cashDividends` (rate +
  lastDatePrior = data ex + paymentDate + label DIVIDENDO/JRS CAP PROPRIO) e
  nº de ações ON/PN. `GetListedCashDividends({tradingName})` pagina o
  histórico completo.
- **COTAHIST codbdi 02**: 372 tickers/mês (units tipo TAEE11/SANB11 inclusas).
  ATENÇÃO (decisão de desenho): NÃO usar a detecção de desdobramento por
  salto de preço dos FIIs em ação — queda de 50% num mês viraria split falso.
  Ajuste de ação = eventos REAIS do endpoint acima; até lá, ações ficam fora
  do `recalcular_derivadas`.

## Fontes mapeadas (probadas em 20/07/2026)

| Dado | Fonte | Observação |
|---|---|---|
| Cotações | **COTAHIST (já temos!)** — codbdi 02 (lote padrão) | mesma infra; ações têm MUITO mais tickers (PETR3/PETR4/units) — 1 empresa = N papéis, precisa de modelo emissor→papéis |
| Cadastro de cias | CVM dados abertos `CIA_ABERTA/CAD` | CNPJ, setor, situação, auditor |
| DFP/ITR (balanços) | CVM `CIA_ABERTA/DOC/DFP` e `/ITR` (CSV anuais) | demonstrações padronizadas em dados estruturados — dá para calcular indicadores SEM parsear PDF |
| Formulário de Referência | CVM `CIA_ABERTA/DOC/FRE` | estruturado em blocos (diretoria! processos! partes relacionadas!) |
| Fatos relevantes/comunicados | CVM IPE (`CIA_ABERTA/DOC/IPE`) — índice com URL de download | equivalente do FNET para empresas |
| Proventos (dividendos/JCP) | ITR/DFP (proventos declarados) + B3 corporate actions | investigar a melhor no A1 |
| Eventos societários (splits) | B3 / IPE | ajuste de preço igual ao dos ETFs (algoritmo pronto) |

## Decisões de produto propostas (validar com o dono)

1. **Modelo emissor→papéis**: a página é da EMPRESA (PETR) com abas/cards por
   papel (PETR3 ON, PETR4 PN) — não uma página por ticker. Comparador compara
   empresas.
2. **Setorização com métricas por setor** em fases: v1 = métricas universais
   (receita, lucro, margem, dívida, ROE, payout, P/L, P/VP, DY); bancos e
   seguradoras entram DEPOIS com réguas próprias (senão as red flags mentem).
3. **Escopo v1**: empresas do IBrX-100 (100 mais líquidas) antes da base
   inteira (~400 cias) — qualidade > cobertura no início.
4. **Selo de ação**: só nasce quando as red flags societárias estiverem
   validadas com casos reais conhecidos (Americanas, IRB, Oi como benchmarks
   retroativos — se o motor não pegaria esses, não está pronto).

## Roadmap proposto (A1–A6)

- **A1 — Fundação**: probes das fontes (CAD/DFP/ITR/FRE/IPE), modelo
  emissor→papéis, cotações codbdi 02 + proventos/ajustes, cadastro com setor
- **A2 — Indicadores fundamentais**: DFP/ITR estruturados → receita, lucro,
  margens, dívida líquida/EBITDA, ROE, série histórica; P/L, P/VP, DY com o
  preço oficial
- **A3 — Red flags societárias + parecer do auditor**: as 6 candidatas acima,
  benchmarkadas contra os casos conhecidos; selo só depois do benchmark
- **A4 — Página da empresa**: carteirinha de regras da classe (tributação de
  ações: isenção de R$ 20 mil/mês, JCP tributado, day trade ≠ swing),
  indicadores, papéis, red flags
- **A5 — FRE + IPE por IA**: diretoria/conselho com histórico, processos,
  partes relacionadas; fatos relevantes no pipeline local
- **A6 — Site**: classe nova no menu/home/busca/comparador (comparar
  EMPRESAS do mesmo setor)

## Riscos conhecidos

- Volume: DFP/ITR/FRE são datasets grandes (centenas de MB/ano) — filtrar por
  escopo v1 desde o download.
- Métrica errada em setor errado = red flag mentirosa (mitigado pela decisão 2).
- Units e classes de ação confundem leigos — a página precisa EXPLICAR
  ON vs PN vs unit na carteirinha (é exatamente o nosso estilo).
