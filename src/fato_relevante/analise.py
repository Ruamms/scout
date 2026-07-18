"""Monta o RaioX de um ativo a partir do cache local (sem internet).

Os indicadores vêm dos informes mensais da CVM e das cotações em cache;
o motor de red flags roda sobre as mesmas séries e devolve alertas com
evidência e fonte.
"""

from __future__ import annotations

import dataclasses
import sqlite3

from . import armazenamento, formato, redflags, series
from .modelos import IndicadorLinha, RaioX
from .redflags.contexto import Contexto

# regra disparada -> linha de indicador que ganha o ⚠
_INDICADOR_DA_REGRA = {
    "distribuicao": "DY mensal",
    "diluicao": "Nº de cotas",
    "vp_queda": "VP/cota",
    "cotistas": "Cotistas",
    "pvp_faixa": "P/VP",
}


Serie = list[tuple[str, float]]


@dataclasses.dataclass(frozen=True)
class DadosGraficos:
    """Séries brutas para o relatório HTML (gráficos SVG)."""

    cotacao: Serie
    vp_ajustado: Serie
    pvp: Serie
    pvp_media: float | None
    dy_por_ano: Serie
    dy_por_mes: Serie  # últimos 36 meses
    pl_por_ano: Serie
    pl_por_mes: Serie
    # janela ("12 meses"/"5 anos"/"máximo") -> [(nome da série, pontos % acumulado)]
    rentabilidade: dict[str, list[tuple[str, Serie]]]


@dataclasses.dataclass(frozen=True)
class AnaliseCompleta:
    raiox: RaioX
    graficos: DadosGraficos


def montar_completo(con: sqlite3.Connection, ticker: str) -> AnaliseCompleta | None:
    raiox = montar_raio_x(con, ticker)
    if raiox is None:
        return None
    fundo = armazenamento.resolver_fundo(con, raiox.ticker)
    serie = armazenamento.serie_complemento(con, fundo.cnpj)
    cotacoes = armazenamento.serie_cotacoes(con, raiox.ticker)
    vp_ajustada = series.serie_vp_ajustada(serie)
    indices = {
        nome: armazenamento.serie_indice(con, nome) for nome in ("CDI", "IPCA")
    }
    return AnaliseCompleta(
        raiox=raiox, graficos=_dados_graficos(serie, cotacoes, vp_ajustada, indices)
    )


def _dados_graficos(
    serie: list[sqlite3.Row],
    cotacoes: list[sqlite3.Row],
    vp_ajustada: dict[str, float],
    indices: dict[str, dict[str, float]] | None = None,
) -> DadosGraficos:
    indices = indices or {}
    cotacao = [
        (linha["competencia"], linha["fechamento"])
        for linha in cotacoes
        if linha["fechamento"]
    ]
    ajustado = [
        (linha["competencia"], linha["fechamento_ajustado"])
        for linha in cotacoes
        if linha["fechamento_ajustado"]
    ]
    pvp = [
        (competencia, fechamento / vp_ajustada[competencia])
        for competencia, fechamento in cotacao
        if vp_ajustada.get(competencia)
    ]
    pvp_media = sum(v for _, v in pvp) / len(pvp) if pvp else None

    dy_por_ano: dict[str, float] = {}
    pl_por_ano: dict[str, float] = {}
    dy_por_mes: list[tuple[str, float]] = []
    pl_por_mes: list[tuple[str, float]] = []
    for linha in serie:
        ano = linha["competencia"][:4]
        if series.dy_valido(linha["dy_mes"]):
            dy_por_ano[ano] = dy_por_ano.get(ano, 0.0) + linha["dy_mes"] * 100
            dy_por_mes.append((linha["competencia"], linha["dy_mes"] * 100))
        if linha["patrimonio_liquido"] is not None:
            pl_por_ano[ano] = linha["patrimonio_liquido"]  # último mês do ano vence
            pl_por_mes.append((linha["competencia"], linha["patrimonio_liquido"]))

    ano_parcial = serie[-1]["competencia"][:4] if serie else ""
    rotulo = lambda ano: f"{ano}*" if ano == ano_parcial else ano  # noqa: E731

    return DadosGraficos(
        cotacao=cotacao,
        vp_ajustado=sorted(vp_ajustada.items()),
        pvp=pvp,
        pvp_media=pvp_media,
        dy_por_ano=[(rotulo(ano), valor) for ano, valor in sorted(dy_por_ano.items())],
        dy_por_mes=dy_por_mes[-36:],
        pl_por_ano=[(rotulo(ano), valor) for ano, valor in sorted(pl_por_ano.items())],
        pl_por_mes=pl_por_mes,
        rentabilidade=_rentabilidades(ajustado, indices),
    )


def _rentabilidades(
    ajustado: list[tuple[str, float]],
    indices: dict[str, dict[str, float]],
) -> dict[str, list[tuple[str, list[tuple[str, float]]]]]:
    """Retorno % acumulado do fundo (com proventos) vs índices, por janela."""
    janelas = {"12 meses": 13, "5 anos": 61, "máximo": None}
    resultado: dict[str, list] = {}
    for nome_janela, tamanho in janelas.items():
        recorte = ajustado[-tamanho:] if tamanho else ajustado
        if len(recorte) < 3 or (tamanho and len(ajustado) < tamanho):
            continue
        series_janela = [("Fundo", _acumulado_fundo(recorte))]
        competencias = [competencia for competencia, _ in recorte]
        for nome_indice, valores in indices.items():
            acumulado = _acumulado_indice(valores, competencias)
            if len(acumulado) >= 3:
                series_janela.append((nome_indice, acumulado))
        resultado[nome_janela] = series_janela
    return resultado


def _acumulado_fundo(pontos: list[tuple[str, float]]) -> list[tuple[str, float]]:
    base = pontos[0][1]
    return [(competencia, 100 * (valor / base - 1)) for competencia, valor in pontos]


def _acumulado_indice(
    valores: dict[str, float], competencias: list[str]
) -> list[tuple[str, float]]:
    """Acumula o índice mensal sobre as competências do fundo (base 0 na 1ª)."""
    acumulado = [(competencias[0], 0.0)]
    fator = 1.0
    for competencia in competencias[1:]:
        if competencia not in valores:
            break  # índice ainda não publicado para o mês (IPCA atrasa ~1 mês)
        fator *= 1 + valores[competencia] / 100
        acumulado.append((competencia, 100 * (fator - 1)))
    return acumulado


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
    preco = meta_cotacao["preco_atual"] if meta_cotacao else None
    vp_ajustada = series.serie_vp_ajustada(serie)

    contexto = Contexto(
        serie=serie,
        vp_ajustada=vp_ajustada,
        cotacoes=cotacoes,
        preco_atual=preco,
    )
    resultado = redflags.avaliar(contexto)

    notas = []
    if not cotacoes:
        notas.append("sem cotação de bolsa para este ticker")
    if resultado.nao_avaliadas:
        notas.append(
            "não avaliadas por falta de histórico ou dado: "
            + "; ".join(resultado.nao_avaliadas)
        )

    indicadores = _montar_indicadores(serie, cotacoes, preco, vp_ajustada)
    indicadores = _marcar_alertas(indicadores, resultado.flags)

    atual = serie[-1]
    return RaioX(
        ticker=ticker,
        nome=fundo.nome,
        cnpj=fundo.cnpj,
        classificacao=fundo.segmento,
        gestao=fundo.tipo_gestao,
        dados_ate=formato.competencia_br(atual["competencia"]),
        cotacao_em=formato.dia_br(meta_cotacao["cotado_em"]) if meta_cotacao else "",
        indicadores=indicadores,
        red_flags=resultado.flags,
        sem_alerta=resultado.aprovadas,
        notas=notas,
        selo=redflags.selo(resultado),
        red_flags_avaliadas=True,
        exemplo=False,
    )


def _marcar_alertas(indicadores: list[IndicadorLinha], flags) -> list[IndicadorLinha]:
    nomes_com_alerta = {
        _INDICADOR_DA_REGRA[flag.codigo]
        for flag in flags
        if flag.codigo in _INDICADOR_DA_REGRA
    }
    return [
        dataclasses.replace(linha, alerta=True) if linha.nome in nomes_com_alerta else linha
        for linha in indicadores
    ]


def _montar_indicadores(
    serie: list[sqlite3.Row],
    cotacoes: list[sqlite3.Row],
    preco: float | None,
    vp_ajustada: dict[str, float],
) -> list[IndicadorLinha]:
    atual = serie[-1]
    primeira = serie[0]["competencia"]
    linhas = []

    if preco is not None and cotacoes:
        linhas.append(
            IndicadorLinha(
                "Cotação",
                f"R$ {formato.decimal(preco)}",
                _oscilacao_12m(cotacoes, preco),
                _oscilacao_no_ano(cotacoes, preco),
            )
        )
        vp = atual["vp_cota"]
        if vp:
            linhas.append(
                IndicadorLinha(
                    "P/VP",
                    formato.decimal(preco / vp),
                    "—",
                    _media_pvp(cotacoes, vp_ajustada),
                )
            )

    pl = atual["patrimonio_liquido"]
    if pl is not None:
        linhas.append(
            IndicadorLinha(
                "Patrimônio líquido",
                formato.moeda_compacta(pl),
                _variacao_12m(serie, "patrimonio_liquido"),
                f"desde {formato.competencia_br(primeira)}",
            )
        )

    vp = atual["vp_cota"]
    if vp is not None:
        linhas.append(
            IndicadorLinha(
                "VP/cota",
                formato.decimal(vp),
                _variacao_12m(serie, "vp_cota"),
                _media_vp_ajustada(vp_ajustada),
            )
        )

    cotas = atual["cotas_emitidas"]
    if cotas is not None:
        linhas.append(
            IndicadorLinha(
                "Nº de cotas",
                formato.compacto(cotas),
                _variacao_12m(serie, "cotas_emitidas"),
                "—",
            )
        )

    ativo = atual["valor_ativo"]
    if ativo is not None:
        linhas.append(
            IndicadorLinha(
                "Valor do ativo",
                formato.moeda_compacta(ativo),
                _variacao_12m(serie, "valor_ativo"),
                "—",
            )
        )

    dy = atual["dy_mes"]
    if dy is not None:
        linhas.append(
            IndicadorLinha(
                "DY mensal",
                formato.percentual(dy * 100),
                _dy_acumulado_12m(serie),
                _media_dy(serie),
            )
        )

    cotistas = atual["cotistas"]
    if cotistas is not None:
        linhas.append(
            IndicadorLinha(
                "Cotistas",
                formato.compacto(cotistas),
                _variacao_12m(serie, "cotistas"),
                "—",
            )
        )

    return linhas


# --- células formatadas ------------------------------------------------------


def _variacao_12m(serie: list[sqlite3.Row], campo: str) -> str:
    variacao = series.variacao_pct(serie, campo, 12)
    if variacao is None:
        return "—"
    return formato.percentual(variacao, sinal=True)


def _oscilacao_12m(cotacoes: list[sqlite3.Row], preco_atual: float) -> str:
    alvo = series.competencia_menos_meses(cotacoes[-1]["competencia"], 12)
    base = series.valor_em(cotacoes, "fechamento", alvo)
    if not base:
        return "—"
    return formato.percentual(100 * (preco_atual - base) / base, sinal=True)


def _oscilacao_no_ano(cotacoes: list[sqlite3.Row], preco_atual: float) -> str:
    dezembro = f"{int(cotacoes[-1]['competencia'][:4]) - 1}-12"
    base = series.valor_em(cotacoes, "fechamento", dezembro)
    if not base:
        return "—"
    return f"{formato.percentual(100 * (preco_atual - base) / base, sinal=True)} no ano"


def _media_pvp(cotacoes: list[sqlite3.Row], vp_ajustada: dict[str, float]) -> str:
    razoes = [
        candle["fechamento"] / vp_ajustada[candle["competencia"]]
        for candle in cotacoes
        if candle["fechamento"] and vp_ajustada.get(candle["competencia"])
    ]
    if not razoes:
        return "—"
    return f"média {formato.decimal(sum(razoes) / len(razoes))}"


def _media_vp_ajustada(vp_ajustada: dict[str, float]) -> str:
    if not vp_ajustada:
        return "—"
    valores = list(vp_ajustada.values())
    return f"média {formato.decimal(sum(valores) / len(valores))}"


def _dy_acumulado_12m(serie: list[sqlite3.Row]) -> str:
    acumulado = series.dy_acumulado(serie, 12)
    if acumulado is None:
        return "—"
    return f"{formato.percentual(acumulado * 100)} 12m"


def _media_dy(serie: list[sqlite3.Row]) -> str:
    validos = [linha["dy_mes"] for linha in serie if series.dy_valido(linha["dy_mes"])]
    if not validos:
        return "—"
    return f"média {formato.percentual(sum(validos) / len(validos) * 100)}"
