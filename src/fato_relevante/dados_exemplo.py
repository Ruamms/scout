"""Dados fictícios para desenvolver e demonstrar a tela.

Serão substituídos pelo pipeline real (coleta CVM -> indicadores ->
red flags) nos próximos milestones. Todo ``RaioX`` produzido aqui sai
com ``exemplo=True``, o que faz o renderizador exibir um aviso.
"""

from __future__ import annotations

from .modelos import IndicadorLinha, RaioX, RedFlag, Severidade


def raio_x_exemplo(ticker: str) -> RaioX:
    return RaioX(
        ticker=ticker,
        nome="FUNDO EXEMPLO FII",
        cnpj="00.000.000/0001-00",
        classificacao="Shoppings",
        gestao="Ativa",
        dados_ate="05/2026",
        indicadores=[
            IndicadorLinha("Cotação", "10,68", "+7,6%", "—"),
            IndicadorLinha("VP/cota", "10,08", "-1,2%", "média 10,40"),
            IndicadorLinha("P/VP", "1,06", "—", "média 0,94"),
            IndicadorLinha("Rendimento/cota", "0,20", "0,86", "—"),
            IndicadorLinha("Nº de cotas", "46,3M", "+12%", "+12% em 24m", alerta=True),
            IndicadorLinha("Vacância", "12,4%", "+1,1 p.p.", "média 10,9%"),
        ],
        red_flags=[
            RedFlag(
                severidade=Severidade.ALTA,
                titulo="Distribuição acima do resultado gerado",
                fato=(
                    "Distribuiu R$ 9,0M no período com FFO de R$ 1,7M — "
                    "o rendimento pode estar saindo do caixa/patrimônio."
                ),
                evidencia="rendimento distribuído 9.042.530 > FFO 1.712.790 (5,3x)",
                fonte="informes mensais CVM 01–05/2026",
            ),
            RedFlag(
                severidade=Severidade.MEDIA,
                titulo="Emissão de cotas sem crescimento proporcional",
                fato="Número de cotas cresceu 12% em 24 meses; resultado por cota caiu 8%.",
                evidencia="cotas 41,3M -> 46,3M; FFO/cota 0,045 -> 0,041",
                fonte="informe trimestral CVM 1T/2026",
            ),
        ],
        sem_alerta=[
            "P/VP dentro da faixa histórica",
            "rendimentos pagos sem interrupção nos últimos 12 meses",
        ],
        exemplo=True,
    )
