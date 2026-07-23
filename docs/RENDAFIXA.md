# Renda Fixa bancária (CDB/LCI/LCA) — dossiê de planejamento (Fase 5)

Registrado em 23/07/2026, ANTES de qualquer código — mesmo método de ETFs e
Ações: entender → mapear fontes (com probes reais) → roadmap → só então
implementar. **Nada aqui está implementado.**

## Por que Renda Fixa é diferente das outras verticais

CDB/LCI/LCA não são ativos listados: são produtos BILATERAIS de bancos,
vendidos por corretoras, sem página pública por instrumento. Não existe "página
do CDB X". O ativo analisável é o **BANCO EMISSOR** — e o risco que o
investidor de renda fixa carrega sem saber é exatamente o que os documentos
oficiais do BCB mostram: saúde de quem emitiu o papel.

## Tese do produto (onde o Scout é único)

O padrão clássico que machuca o investidor: **banco em dificuldade paga
130–150% do CDI para captar** (o CDB "imperdível" da corretora), o investidor
olha só a taxa e o selo do FGC, e ignora que (a) o FGC cobre até R$ 250 mil
por CPF **por conglomerado** (e teto global de R$ 1 milhão renovável a cada
4 anos), (b) a liquidação leva meses SEM correção nesse meio-tempo, e (c) os
sinais de estresse do emissor eram públicos no IF.data trimestres antes.

O Scout pode ser o único lugar gratuito que mostra, em linguagem de leigo:
1. **Página por BANCO emissor** — Basileia, lucro, carteira, inadimplência,
   crescimento de captação — com red flags auditáveis (a régua de banco que
   NÃO aplicamos em ações agora se aplica: Basileia é a métrica-mãe).
2. **Red flags de emissor**: Basileia perto do mínimo regulatório, prejuízo
   recorrente, captação crescendo muito acima da carteira (o "aspirador de
   CDB"), inadimplência fora da curva do porte.
3. **Carteirinha de regras da classe**: FGC por CPF+conglomerado (não por
   corretora!), teto global de R$ 1 mi/4 anos, IR regressivo, IOF <30 dias,
   LCI/LCA isentas, liquidez vs vencimento.
4. **Calculadoras opt-in (padrão Gordon)**: equivalência CDB %CDI × LCI/LCA
   isenta (gross-up por prazo/IR) e "quanto do meu valor está coberto pelo
   FGC" (por conglomerado).

O que o Scout NÃO vai fazer: comparar taxas de corretoras (não há fonte
pública consolidada de taxas de captação por banco; taxa de prateleira é
dado comercial) nem recomendar emissor.

## Fontes mapeadas (probes de 23/07/2026)

| Dado | Fonte | Status do probe |
|---|---|---|
| Balanço/Basileia/DRE por IF | **IF.data (BCB)** — olinda `IFDATA/versao/v1/odata` | `ListaDeRelatorio()` OK: relatórios 1–10 (Resumo, Ativo, Passivo, DRE, **Informações de Capital**, Segmentação, carteira por indexador/nível/região). `IfDataCadastro`/`IfDataValores` responderam **HTTP 500** em todos os períodos testados (202412/202503/202512/202603) apesar da assinatura correta (`$metadata` confirmado: AnoMes/TipoInstituicao/Relatorio) — reprobar; plano B: **CSVs trimestrais do portal IF.data** (download manual/automatizável) |
| Cadastro de IFs + conglomerados | IF.data cadastro (mesmo serviço) ou UNICAD/lista de instituições BCB | mesmo 500 do olinda; o CSV do portal traz conglomerado prudencial — **é a chave do FGC** (cobertura é por conglomerado, não por banco) |
| Associados do FGC | fgc.org.br (lista de associadas) | não probado (HTML institucional); lista muda pouco — candidata a curadoria versionada com fonte, como taxas de ETF |
| CDI (comparações/calculadora) | SGS 4391 (**já temos** na base) | OK — em produção desde a Fase 1 |
| Taxa de captação por banco | — | **não existe fonte pública consolidada** (achado do probe); fora do escopo |

## Decisões de produto propostas (validar com o dono)

1. **A unidade é o CONGLOMERADO prudencial** (ex.: "Banco Master" e suas
   caixas contam juntos no FGC) — página por conglomerado, com as instituições
   dentro listadas.
2. **Escopo v1**: bancos que emitem CDB para varejo (tipo b1/b2 no IF.data,
   ~150 instituições) — não seguradoras/cooperativas num primeiro momento.
3. **Selo de emissor SÓ depois de benchmark retroativo** (mesma regra do A3):
   os casos reais são conhecidos — BRK, Portocred, Neon DTVM?, e o clássico
   **Banco Neon/Banco Máxima/BRK Financeira** liquidados pelo BCB; se o motor
   não acenderia NELES trimestres antes, não está pronto.
4. **Sem comparação de taxas**: fato sobre o emissor, nunca "vale a pena".
5. As calculadoras seguem o padrão opt-in da Gordon (aviso antes do botão,
   premissas do usuário, sem veredito).

## Roadmap proposto (R1–R4)

- **R1 — Fundação de dados**: destravar o IF.data (olinda re-probe ou CSVs do
  portal); tabelas `bancos` (conglomerado, instituições, segmento b1/b2) e
  `bancos_tri` (Basileia, PL, lucro, captação, carteira, inadimplência por
  trimestre); lista do FGC como curadoria versionada.
- **R2 — Red flags de emissor + benchmark retroativo** (gate do dono para o
  selo, como no A3): Basileia < mínimo+colchão, prejuízo em N dos últimos M
  trimestres, captação/carteira desproporcional, inadimplência fora da curva.
- **R3 — Página do emissor + carteirinha da classe** (design novo): cards
  (Basileia, lucro, carteira, captação), série trimestral, regras do FGC/IR
  para leigo, red flags com evidência e fonte.
- **R4 — Calculadoras**: equivalência CDB × LCI/LCA (gross-up) e cobertura
  FGC por conglomerado; classe nova no menu/home/busca.

## Riscos conhecidos

- **IF.data instável** (500 no probe): pode exigir a rota CSV do portal, que
  é trimestral e com layout próprio — mapear no R1 antes de qualquer schema.
- Régua de banco é técnica (Basileia, RWA): a página precisa EXPLICAR cada
  métrica em linguagem de leigo ou vira ruído.
- Nome de fantasia ≠ conglomerado (o investidor conhece "banco X" da
  corretora; o FGC olha o conglomerado) — o mapeamento é parte do produto.
- Liquidações são raras: o benchmark retroativo tem poucos casos — validar
  também contra os que NÃO quebraram (falso-positivo custa credibilidade).
