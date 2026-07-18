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
}
