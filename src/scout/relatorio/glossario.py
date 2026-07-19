"""Glossário em linguagem simples para o relatório HTML.

Cada termo técnico exibido na página ganha um "?" com a explicação para
quem está começando — sem dumbing down para quem já sabe.
"""

TERMOS = {
    "Cotação": (
        "O preço da cota na bolsa agora — quanto custa comprar uma \"fatia\" do fundo. "
        "Sobe e desce conforme oferta e procura, como uma ação."
    ),
    "P/VP": (
        "Preço dividido pelo Valor Patrimonial da cota. Em 1,00 você paga exatamente o que "
        "o patrimônio vale; abaixo de 1,00 paga com desconto; acima, paga um prêmio. "
        "Nem desconto é sempre barganha, nem prêmio é sempre exagero — é um ponto de partida."
    ),
    "VP/cota": (
        "Valor Patrimonial por cota: tudo o que o fundo possui, menos as dívidas, dividido "
        "pelo número de cotas. É o \"valor de tabela\" da cota, calculado pelo administrador."
    ),
    "Patrimônio líquido": (
        "Tudo o que o fundo possui (imóveis, aplicações, dinheiro em caixa) menos o que ele "
        "deve. É o tamanho real do fundo."
    ),
    "Nº de cotas": (
        "Em quantas \"fatias\" o fundo está dividido. Quando o fundo emite cotas novas para "
        "captar dinheiro, esse número cresce — e a sua fatia fica proporcionalmente menor "
        "se você não participar da emissão."
    ),
    "Valor do ativo": (
        "A soma de tudo o que o fundo possui, sem descontar as dívidas. A diferença entre "
        "este valor e o patrimônio líquido indica quanto o fundo deve."
    ),
    "DY mensal": (
        "Dividend Yield mensal: quanto o fundo pagou de rendimento no mês, em percentual do "
        "valor da cota. 0,66% significa R$ 0,66 de rendimento para cada R$ 100 investidos."
    ),
    "Cotistas": (
        "Quantas pessoas e instituições investem no fundo. Base pequena significa menos "
        "liquidez; abaixo de 100 cotistas o fundo pode perder a isenção de imposto de renda "
        "dos rendimentos."
    ),
    "Red flags": (
        "Alertas automáticos baseados em regras públicas e auditáveis: cada um mostra o "
        "fato, a conta que o disparou e a fonte oficial do dado. Alertas apontam o que "
        "merece investigação — não são recomendação de compra ou venda."
    ),
    "Cotação × VP/cota": (
        "Compara o preço na bolsa (o que o mercado paga) com o valor patrimonial da cota "
        "(o que o fundo vale \"na tabela\") ao longo do tempo. Quando as linhas se afastam, "
        "o mercado está pagando bem mais — ou bem menos — do que o patrimônio vale."
    ),
    "P/VP histórico": (
        "O P/VP mês a mês, com a média do próprio fundo. Mostra se o preço atual está caro "
        "ou barato em relação ao que ESTE fundo costumou custar — não em relação aos outros."
    ),
    "Rentabilidade acumulada (com proventos) × CDI × IPCA": (
        "Quanto o investimento rendeu no período, somando a variação do preço E os "
        "rendimentos pagos. CDI é a referência da renda fixa; IPCA é a inflação — render "
        "menos que o IPCA significa perder poder de compra."
    ),
    "Dividend yield (%)": (
        "Quanto o fundo pagou de rendimento em relação ao valor da cota, por ano ou por "
        "mês. Constância costuma importar mais que picos isolados."
    ),
    "Patrimônio líquido (gráfico)": (
        "A evolução do tamanho do fundo. Crescimento por emissão de cotas não é a mesma "
        "coisa que crescimento por valorização — confira o número de cotas junto."
    ),
    "Pares do segmento": (
        "Os maiores fundos que atuam no mesmo segmento deste, com a média do segmento na "
        "última linha. Comparar com pares dá contexto: um DY alto pode ser normal no "
        "segmento — ou um ponto fora da curva que merece investigação."
    ),
    "Administrador": (
        "A instituição responsável legal pelo fundo (contrata gestora, presta contas à "
        "CVM). Ver os outros fundos da mesma casa ajuda a formar opinião sobre o "
        "histórico de quem toca este — muitos fundos com alerta é um padrão que merece "
        "atenção."
    ),
    "Vacância": (
        "Percentual da área dos imóveis que está vazia, sem inquilino. Área vaga não gera "
        "aluguel — e o fundo ainda paga condomínio e IPTU dela. Ponderada pela área de "
        "cada imóvel."
    ),
    "Imóveis": (
        "Os imóveis do fundo, do informe trimestral oficial. \"% da receita\" mostra o peso "
        "de cada imóvel no aluguel total — um imóvel dominante é risco de concentração. "
        "Inadimplência é aluguel devido e não pago pelos inquilinos daquele imóvel."
    ),
    "Vacância (%)": (
        "A evolução da área vaga ao longo do tempo. Vacância subindo trimestre após "
        "trimestre importa mais do que um número alto isolado."
    ),
    "Leitura por IA": (
        "Um modelo de inteligência artificial rodando localmente (sem nuvem) leu o "
        "relatório oficial do fundo e extraiu os fatos, citando os trechos. A IA não "
        "calcula números nem dá opinião — e o documento original está sempre a um "
        "clique para conferência."
    ),
    "Calculadoras": (
        "Simulações matemáticas com os números deste fundo já preenchidos. Não tem botão "
        "de calcular: edite qualquer campo e os resultados se atualizam na hora. São "
        "contas, não previsões — rendimento passado não garante o futuro."
    ),
    "E se eu tivesse investido?": (
        "Diferente de uma projeção, aqui a conta usa o que de fato aconteceu: a "
        "rentabilidade real do fundo (com os rendimentos pagos) e os índices oficiais do "
        "mesmo período. Serve para comparar, não para prever."
    ),
    "Uma cota por mês": (
        "O marco em que o investimento \"gira sozinho\": com essa quantidade de cotas, os "
        "rendimentos de um mês pagam uma cota nova. A partir daí o reinvestimento acelera "
        "sem dinheiro novo do bolso."
    ),
    "Projeção de aportes": (
        "Juros compostos na prática: aporte inicial + aportes mensais rendendo à taxa "
        "definida. Reinvestir os rendimentos é o que faz a curva dobrar no longo prazo."
    ),
    "Oscilações com contexto": (
        "Os meses em que a cota subiu ou caiu mais de 10%, lado a lado com o que aconteceu "
        "no mesmo período (emissão de cotas, mudança no rendimento, fato relevante). "
        "Atenção: estar no mesmo mês não prova que uma coisa causou a outra — é um ponto "
        "de partida para investigar, não uma explicação pronta."
    ),
}

# Jargão de mercado que aparece nos relatórios gerenciais (e, portanto, nas
# leituras por IA). Definições determinísticas nossas — nunca do modelo.
# O termo vira um sublinhado pontilhado com a explicação no hover.
JARGAO = {
    "CRI": (
        "Certificado de Recebíveis Imobiliários: um \"empréstimo imobiliário empacotado\". "
        "O fundo empresta dinheiro para projetos/empresas do setor e recebe juros. "
        "É o principal ativo dos FIIs \"de papel\"."
    ),
    "CDI": (
        "Taxa de referência dos juros no Brasil, que anda colada na Selic. "
        "\"CDI + 2%\" significa render a taxa básica da economia mais 2% ao ano."
    ),
    "LCI": (
        "Letra de Crédito Imobiliário: título emitido por banco, lastreado em crédito "
        "imobiliário. Costuma ser a parte mais conservadora da carteira."
    ),
    "LCA": (
        "Letra de Crédito do Agronegócio: título de banco lastreado em crédito do agro, "
        "parente da LCI."
    ),
    "Selic": (
        "A taxa básica de juros da economia, definida pelo Banco Central. Quando sobe, "
        "fundos atrelados a juros rendem mais; quando cai, rendem menos."
    ),
    "IPCA": (
        "O índice oficial de inflação do Brasil. \"IPCA + 6%\" = rende a inflação mais "
        "6% ao ano — protege o poder de compra."
    ),
    "IGP-M": (
        "Índice de inflação muito usado em contratos de aluguel. Mais volátil que o IPCA "
        "por sofrer influência do dólar e de preços no atacado."
    ),
    "ABL": (
        "Área Bruta Locável: os metros quadrados que o fundo tem disponíveis para alugar. "
        "É a \"capacidade produtiva\" de um fundo de tijolo."
    ),
    "cap rate": (
        "Renda anual do imóvel dividida pelo seu valor. Um cap rate de 8% significa que o "
        "imóvel gera 8% do próprio valor em aluguel por ano."
    ),
    "high grade": (
        "Carteira de crédito com devedores mais sólidos e garantias fortes: menos risco, "
        "juros menores."
    ),
    "high yield": (
        "Carteira de crédito com juros maiores em troca de mais risco de calote. "
        "O oposto de high grade."
    ),
    "pro-soluto": (
        "Crédito em que, entregue a garantia combinada, o vendedor não pode cobrar do "
        "devedor o que faltar. Na prática: risco maior para quem compra esse crédito."
    ),
    "pró-soluto": (
        "Crédito em que, entregue a garantia combinada, o vendedor não pode cobrar do "
        "devedor o que faltar. Na prática: risco maior para quem compra esse crédito."
    ),
    "FoF": (
        "Fund of Funds — fundo que investe em cotas de outros FIIs em vez de comprar "
        "imóveis ou títulos diretamente."
    ),
    "duration": (
        "Prazo médio (em anos) para o dinheiro investido nos títulos voltar. Quanto maior, "
        "mais sensível a carteira é a mudanças de juros."
    ),
    "spread": (
        "A \"gordura\" de juros acima do índice de referência. Num CRI que paga CDI + 3%, "
        "o spread é os 3%."
    ),
}
