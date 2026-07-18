"""Monta o RaioX de um ativo a partir do cache local (sem internet).

Nesta fase os indicadores vêm dos informes mensais da CVM. Cotação de
mercado (e portanto P/VP) e o motor de red flags entram nos próximos
milestones.
"""

from __future__ import annotations

import sqlite3

from . import armazenamento
from .modelos import IndicadorLinha, RaioX

_NOTAS_FASE_ATUAL = [
    "motor de red flags entra no milestone 4",
]


def montar_raio_x(con: sqlite3.Connection, ticker: str) -> RaioX | None:
    ticker = ticker.strip().upper()
    fundo = armazenamento.resolver_fundo(con, ticker)
    if fundo is None:
        return None
    serie = armazenamento.serie_complemento(con, fundo.cnpj)
    if not serie:
        return None
    cotacoes = armazenamento.serie_cotacoes(con, ticker)
    meta_cotacao = armazenamento.cotacao_meta(con, ticker)
    atual = serie[-1]
    notas = list(_NOTAS_FASE_ATUAL)
    if not cotacoes:
        notas.insert(0, "sem cotação de bolsa para este ticker")
    return RaioX(
        ticker=ticker,
        nome=fundo.nome,
        cnpj=fundo.cnpj,
        classificacao=fundo.segmento,
        gestao=fundo.tipo_gestao,
        dados_ate=_competencia_br(atual["competencia"]),
        cotacao_em=_dia_br(meta_cotacao["cotado_em"]) if meta_cotacao else "",
        indicadores=_montar_indicadores(serie, cotacoes, meta_cotacao),
        red_flags=[],
        sem_alerta=[],
        notas=notas,
        red_flags_avaliadas=False,
        exemplo=False,
    )


def _montar_indicadores(
    serie: list[sqlite3.Row],
    cotacoes: list[sqlite3.Row],
    meta_cotacao: sqlite3.Row | None,
) -> list[IndicadorLinha]:
    atual = serie[-1]
    primeira = serie[0]["competencia"]
    vp_ajustada = _serie_vp_ajustada(serie)
    linhas = []

    preco = meta_cotacao["preco_atual"] if meta_cotacao else None
    if preco is not None and cotacoes:
        linhas.append(
            IndicadorLinha(
                "Cotação",
                f"R$ {_decimal(preco)}",
                _oscilacao_12m(cotacoes, preco),
                _oscilacao_no_ano(cotacoes, preco),
            )
        )
        vp = atual["vp_cota"]
        if vp:
            linhas.append(
                IndicadorLinha(
                    "P/VP",
                    _decimal(preco / vp),
                    "—",
                    _media_pvp(cotacoes, vp_ajustada),
                )
            )

    pl = atual["patrimonio_liquido"]
    if pl is not None:
        linhas.append(
            IndicadorLinha(
                "Patrimônio líquido",
                _moeda_compacta(pl),
                _variacao_12m(serie, "patrimonio_liquido"),
                f"desde {_competencia_br(primeira)}",
            )
        )

    vp = atual["vp_cota"]
    if vp is not None:
        linhas.append(
            IndicadorLinha(
                "VP/cota",
                _decimal(vp),
                _variacao_12m(serie, "vp_cota"),
                _media_vp_ajustada(vp_ajustada),
            )
        )

    cotas = atual["cotas_emitidas"]
    if cotas is not None:
        linhas.append(
            IndicadorLinha(
                "Nº de cotas",
                _compacto(cotas),
                _variacao_12m(serie, "cotas_emitidas"),
                "—",
            )
        )

    ativo = atual["valor_ativo"]
    if ativo is not None:
        linhas.append(
            IndicadorLinha(
                "Valor do ativo",
                _moeda_compacta(ativo),
                _variacao_12m(serie, "valor_ativo"),
                "—",
            )
        )

    dy = atual["dy_mes"]
    if dy is not None:
        linhas.append(
            IndicadorLinha(
                "DY mensal",
                _percentual(dy * 100),
                _dy_acumulado_12m(serie),
                _media_dy(serie),
            )
        )

    cotistas = atual["cotistas"]
    if cotistas is not None:
        linhas.append(
            IndicadorLinha(
                "Cotistas",
                _compacto(cotistas),
                _variacao_12m(serie, "cotistas"),
                "—",
            )
        )

    return linhas


# --- cotações e P/VP --------------------------------------------------------


def _oscilacao_12m(cotacoes: list[sqlite3.Row], preco_atual: float) -> str:
    alvo = _competencia_menos_meses(cotacoes[-1]["competencia"], 12)
    base = next((c["fechamento"] for c in cotacoes if c["competencia"] == alvo), None)
    if not base:
        return "—"
    return _percentual(100 * (preco_atual - base) / base, sinal=True)


def _oscilacao_no_ano(cotacoes: list[sqlite3.Row], preco_atual: float) -> str:
    dezembro = f"{int(cotacoes[-1]['competencia'][:4]) - 1}-12"
    base = next((c["fechamento"] for c in cotacoes if c["competencia"] == dezembro), None)
    if not base:
        return "—"
    return f"{_percentual(100 * (preco_atual - base) / base, sinal=True)} no ano"


def _media_pvp(cotacoes: list[sqlite3.Row], vp_ajustada: dict[str, float]) -> str:
    razoes = [
        c["fechamento"] / vp_ajustada[c["competencia"]]
        for c in cotacoes
        if c["fechamento"] and vp_ajustada.get(c["competencia"])
    ]
    if not razoes:
        return "—"
    return f"média {_decimal(sum(razoes) / len(razoes))}"


def _media_vp_ajustada(vp_ajustada: dict[str, float]) -> str:
    if not vp_ajustada:
        return "—"
    valores = list(vp_ajustada.values())
    return f"média {_decimal(sum(valores) / len(valores))}"


def _serie_vp_ajustada(serie: list[sqlite3.Row]) -> dict[str, float]:
    """VP/cota com desdobramentos neutralizados (na base de cotas atual).

    A CVM publica o VP/cota da época; um desdobramento 10:1 faz o valor
    despencar 90% de um mês para o outro sem perda patrimonial nenhuma.
    Saltos além de 2,5x para qualquer lado são tratados como evento de
    cotas (desdobramento/grupamento) e neutralizados, para que médias e
    comparações históricas façam sentido.
    """
    bruta = [
        (linha["competencia"], linha["vp_cota"])
        for linha in serie
        if linha["vp_cota"]
    ]
    ajustada: dict[str, float] = {}
    fator = 1.0
    vp_posterior = None
    for competencia, vp in reversed(bruta):
        if vp_posterior is not None:
            razao = vp / vp_posterior
            if razao >= 2.5 or razao <= 0.4:
                fator *= vp_posterior / vp
        ajustada[competencia] = vp * fator
        vp_posterior = vp
    return ajustada


# --- séries -----------------------------------------------------------------


def _valor_12m_atras(serie: list[sqlite3.Row], campo: str) -> float | None:
    alvo = _competencia_menos_meses(serie[-1]["competencia"], 12)
    for linha in serie:
        if linha["competencia"] == alvo:
            return linha[campo]
    return None


def _variacao_12m(serie: list[sqlite3.Row], campo: str) -> str:
    atual = serie[-1][campo]
    anterior = _valor_12m_atras(serie, campo)
    if atual is None or anterior in (None, 0):
        return "—"
    return _percentual(100 * (atual - anterior) / abs(anterior), sinal=True)


def _media_historica(serie: list[sqlite3.Row], campo: str, prefixo: str = "") -> str:
    valores = [linha[campo] for linha in serie if linha[campo] is not None]
    if not valores:
        return "—"
    return prefixo + _decimal(sum(valores) / len(valores))


def _dy_valido(valor: float | None) -> bool:
    """Filtra lixo auto-declarado (há DY negativo e até de 8,6 bilhões % na base)."""
    return valor is not None and 0 <= valor <= 0.10


def _dy_acumulado_12m(serie: list[sqlite3.Row]) -> str:
    ultimos = [linha["dy_mes"] for linha in serie[-12:] if _dy_valido(linha["dy_mes"])]
    if not ultimos:
        return "—"
    return f"{_percentual(sum(ultimos) * 100)} 12m"


def _media_dy(serie: list[sqlite3.Row]) -> str:
    validos = [linha["dy_mes"] for linha in serie if _dy_valido(linha["dy_mes"])]
    if not validos:
        return "—"
    return f"média {_percentual(sum(validos) / len(validos) * 100)}"


def _competencia_menos_meses(competencia: str, meses: int) -> str:
    ano, mes = int(competencia[:4]), int(competencia[5:7])
    total = ano * 12 + (mes - 1) - meses
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def _competencia_br(competencia: str) -> str:
    return f"{competencia[5:7]}/{competencia[:4]}"


def _dia_br(data_iso: str | None) -> str:
    if not data_iso or len(data_iso) < 10:
        return ""
    return f"{data_iso[8:10]}/{data_iso[5:7]}/{data_iso[:4]}"


# --- formatação pt-BR -------------------------------------------------------


def _decimal(valor: float, casas: int = 2) -> str:
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "\0").replace(".", ",").replace("\0", ".")


def _percentual(valor: float, sinal: bool = False) -> str:
    prefixo = "+" if sinal and valor > 0 else ""
    return f"{prefixo}{_decimal(valor)}%"


def _compacto(valor: float) -> str:
    for limite, sufixo in ((1e9, "B"), (1e6, "M"), (1e3, "mil")):
        if abs(valor) >= limite:
            return f"{_decimal(valor / limite, 1)}{sufixo}"
    return _decimal(valor, 0)


def _moeda_compacta(valor: float) -> str:
    return f"R$ {_compacto(valor)}"
