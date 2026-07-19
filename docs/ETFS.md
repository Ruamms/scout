# ETFs — dossiê de entendimento (base do roadmap)

Registrado em 19/07/2026, antes de escrever qualquer código. Princípio do produto
mantido: **fatos com fonte, nunca recomendação** — e para ETF o fato mais valioso
é justamente "as regras do brinquedo", que quase nenhum investidor conhece.

## O que é (e por que confunde)

ETF (Exchange Traded Fund / "Fundo de Índice", tipo `FIIM` no registro CVM) é um
fundo que replica um índice e negocia em bolsa como uma ação. **212 em
funcionamento** no Brasil hoje. A confusão nasce porque o MESMO formato embala
coisas de comportamento completamente diferente:

| Tipo (índice subjacente) | Exemplos | Comportamento |
|---|---|---|
| Ações Brasil | BOVA11, SMAL11, DIVD11 | variação alta, segue a bolsa |
| Ações internacionais | IVVB11, NASD11 | variação da bolsa lá fora + CÂMBIO embutido |
| Renda fixa | IMAB11, IRFM11, LFTS11, B5P211 | variação baixa; rendimento "invisível" (a cota engorda, nada cai na conta) |
| Cripto | HASH11, QBTC11, BITH11 | volatilidade extrema; custódia via fundo |
| FII-índice | XFIX11 | "FII de FIIs" via índice |
| Híbridos/temáticos | ABTC11 (BTC + renda fixa) | regras próprias caso a caso |

## As peculiaridades que MUDAM o produto

**1. Distribuição de rendimentos.** A maioria dos ETFs brasileiros **reinveste
automaticamente** (total return): não existe "dividendo pingando na conta" — a
calculadora "Uma cota por mês" NÃO SE APLICA e exibi-la seria enganoso. Uma
geração nova (2024+) passou a **distribuir renda**; e há casos que fazem os dois.
→ A página precisa DETECTAR e DIZER o regime de cada fundo; calculadoras por regime.

**2. Tributação (informativa, com fonte — nunca conselho).**
- ETF de ações: 15% sobre o ganho na venda e **NÃO tem a isenção de R$ 20 mil/mês
  das ações** — a pegadinha nº 1 do investidor iniciante.
- ETF de renda fixa (Lei 13.043/2014): IR pelo **prazo médio de repactuação da
  carteira** — ≤180 dias: 25% · 181–720 dias: 20% · **>720 dias: 15% FIXO**
  (não importa quanto tempo VOCÊ segura; importa o prazo da carteira do fundo).
  **Sem come-cotas** e **SEM IOF** (nem nos primeiros 30 dias — diferente de
  CDB/Tesouro). IR retido na fonte só na venda. É o combo que faz o formato
  brilhar para curto e longo prazo ao mesmo tempo.
- ETF de cripto: 15% sem isenção (cripto direto tem isenção até R$ 35 mil/mês —
  pegadinha nº 2).

**3. Métricas próprias (não existem no mundo FII).**
- **Taxa de administração**: comparável entre ETFs do MESMO índice — taxa alta
  no mesmo índice é fato objetivo.
- **Prêmio/desconto**: preço em bolsa vs cota patrimonial (a CVM publica a cota
  diária no informe de fundos 555) — descolamento persistente é alerta.
- **Tracking difference**: quanto o fundo entrega vs o índice que promete seguir.
- **PL pequeno**: risco real de deslistagem/encerramento.
- **Liquidez/volume** e presença de formador de mercado.

## Por que cada tipo existe — e a pegadinha de cada um

Comprar os ativos direto costuma ser mais barato em taxa; o ETF existe quando o
formato entrega algo que a compra direta não entrega. A página de cada tipo deve
contar OS DOIS lados:

**Ações Brasil** — o sentido: 1 cota ≈ a cesta inteira (BOVA11 a ~R$ 170 expõe a
80+ empresas; montar isso na mão custaria dezenas de milhares de reais e
rebalanceamento manual eterno). Uma ação cai, as outras seguram. A pegadinha:
os dividendos das ações — **isentos** quando recebidos direto — são reinvestidos
dentro do fundo e viram ganho de capital **tributado em 15%** na venda. O ETF
converte renda isenta em ganho tributável (pegadinha nº 3).

**Dividendos (IDIV e afins)** — o sentido: suaviza a renda (um paga menos, outro
paga mais). A pegadinha: idem acima — se o ETF não for da geração distribuidora,
a "renda" nunca chega na sua conta.

**Ações Internacionais** — o sentido: exposição ao exterior sem abrir conta lá
fora, sem remessa, sem spread de câmbio físico, e no IR brasileiro. A pegadinha:
**dupla exposição** — você carrega o índice E o dólar; o S&P pode subir e a cota
cair (real valorizou). Volatilidade que o iniciante não espera.

**Renda Fixa** — o sentido: liquidez de bolsa (D+2) para uma carteira de títulos
que individualmente travariam até o vencimento; sem IOF; sem come-cotas;
carteira >720 dias = IR fixo de 15%. A pegadinha: **marcação a mercado** — juro
sobe, IMAB11 cai; "renda fixa" que oscila assusta quem veio da poupança. E o
rendimento é invisível (cota engorda; nada pinga na conta até vender).

**Cripto** — o sentido: exposição sem carteira própria, sem seed phrase, sem
exchange, e com IR simplificado (a corretora reporta). A pegadinha: taxa de
administração alta para o padrão ETF, e **perde a isenção de R$ 35 mil/mês**
que a cripto direta tem.

**Commodities (ouro etc.)** — o sentido: ouro sem barra física ou contrato
futuro. A pegadinha: mesma conversão de regime tributário, taxa, e tracking.

**Misto/Híbrido** — o sentido: alocação pronta em um papel só. A pegadinha: a
proporção interna muda o comportamento inteiro — 70/30 renda fixa/cripto é OUTRO
produto que 30/70. Por isso a classificação dinâmica (abaixo).

## Fontes mapeadas (investigação de 19/07/2026)

| Dado | Fonte | Status |
|---|---|---|
| Cadastro, gestora, admin | `registro_fundo_classe.zip` (Tipo_Fundo=FIIM) | **JÁ BAIXAMOS** (infra do Scout) |
| Preço em bolsa (ações/cripto/FII-índice) | COTAHIST codbdi **14** | infra pronta (`coleta/b3.py`, só alargar o filtro) |
| Preço de ETF de **renda fixa** | **NÃO está no COTAHIST** (negociação em ambiente próprio da B3) | fonte a investigar — milestone dedicado |
| Cota patrimonial diária, PL, cotistas | informe diário de fundos 555 (CVM `FI/DOC/INF_DIARIO`), ETFs incluídos | validar volumetria no E1 |
| Índice de referência, taxa de adm | cadastro/B3 fundos listados | investigar no E1 |
| Proventos dos ETFs distribuidores | B3 (corporate actions) | investigar no E6 |
| Relatórios para IA | ETF **não usa o FNET** (isso é de estruturados) | fase 2 do ETF |

## Decisões de produto (validadas com o dono do produto em 19/07/2026)

1. **Página de ETF é DIFERENTE da página de FII** — sem imóveis/vacância/DY
   mensal; com regime de distribuição, tributação do tipo, prêmio/desconto,
   taxa, tracking. O topo ganha a "carteirinha de regras" do tipo: 3-4 linhas
   didáticas dizendo como AQUELE tipo se comporta (distribui? como é tributado?
   onde o rendimento aparece?).
2. **Home multi-classe com mega-menu**: o site ganha uma home nova com um resumo
   de indicadores POR CLASSE (FIIs, ETFs) e um menu superior interativo estilo
   mega-menu (referência visual: Investidor10), com as opções de cada classe
   (todos os fundos, rankings, comparador, calculadoras). Viável no GitHub Pages:
   menu é HTML/CSS/JS puro, nenhuma limitação técnica — a única restrição do
   Pages é não ter servidor, e menu não precisa de servidor.
3. **Classificação por tipo é curadoria assistida por planilha**:
   `dados/classificacao_etfs.csv` (no repo) — linhas = 212 ETFs do registro CVM,
   colunas = classificação sugerida pela heurística de nome/índice, sinais
   mistos, e `classificacao_final` (humana). Sites de mercado servem como
   CONFERÊNCIA visual durante a revisão (não copiamos os rótulos deles para o
   produto — taxonomia própria). Nomenclatura adotada (linguagem de leigo):
   **Ações Brasil · Ações Internacionais · Renda Fixa · Renda Fixa
   Internacional · Cripto · Commodities · FIIs (índice) · Misto/Híbrido**.
   "Renda Fixa Internacional" nasceu na revisão de 19/07/2026 (T-Bills dos EUA:
   renda fixa que oscila com o dólar — pegadinha própria). Para o Misto/Híbrido,
   a classificação é DINÂMICA: exibir a composição real por classe ("Renda Fixa
   70% · Cripto 30%") no selo/hover, calculada da carteira oficial (CDA/CVM,
   arquivo `cda_fie` — validado: 182 ETFs cobertos). O VERIFICADOR mensal
   (`coleta/cda.py`) compara carteira real vs curadoria e aponta divergências.
4. **Renda fixa entra desde o início** mesmo sem preço de bolsa (ver E4): o
   informe diário da CVM publica o VALOR DA COTA de cada ETF todo dia útil; para
   ETF de renda fixa o preço de tela gruda nesse valor (o formador de mercado
   arbitra qualquer descolamento). Exibimos esse valor oficial rotulado como
   "valor da cota (patrimonial)" com aviso de que não é o preço de negociação —
   informação honesta hoje em vez de página nenhuma até resolver a fonte.
5. Selo/red flags de ETF têm **regras próprias** (as de FII não fazem sentido).
