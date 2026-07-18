"""Cálculos sobre as séries mensais (informes CVM e cotações).

Funções puras compartilhadas entre a montagem de indicadores e o motor
de red flags.
"""

from __future__ import annotations


def ticker_do_isin(isin: str | None) -> str:
    """BRHGLGCTF004 -> HGLG11 (convenção da B3 para cotas de FII)."""
    if not isin or len(isin) < 6 or not isin.startswith("BR"):
        return ""
    return f"{isin[2:6]}11"


def competencia_menos_meses(competencia: str, meses: int) -> str:
    ano, mes = int(competencia[:4]), int(competencia[5:7])
    total = ano * 12 + (mes - 1) - meses
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def valor_em(serie: list, campo: str, competencia: str):
    for linha in serie:
        if linha["competencia"] == competencia:
            return linha[campo]
    return None


def variacao_pct(serie: list, campo: str, meses: int) -> float | None:
    """Variação % do campo entre a última competência e `meses` atrás."""
    if not serie:
        return None
    atual = serie[-1][campo]
    alvo = competencia_menos_meses(serie[-1]["competencia"], meses)
    base = valor_em(serie, campo, alvo)
    if atual is None or base in (None, 0):
        return None
    return 100 * (atual - base) / abs(base)


def dy_valido(valor: float | None) -> bool:
    """Filtra lixo auto-declarado (há DY negativo e até de 8,6 bilhões % na base)."""
    return valor is not None and 0 <= valor <= 0.10


def dy_acumulado(serie: list, meses: int = 12) -> float | None:
    """Soma (fração) dos DYs válidos das últimas `meses` competências."""
    validos = [linha["dy_mes"] for linha in serie[-meses:] if dy_valido(linha["dy_mes"])]
    if not validos:
        return None
    return sum(validos)


def serie_vp_ajustada(serie: list) -> dict[str, float]:
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


def variacao_vp_ajustado(vp_ajustada: dict[str, float], meses: int) -> float | None:
    """Variação % do VP/cota ajustado entre a última competência e `meses` atrás."""
    if not vp_ajustada:
        return None
    competencias = sorted(vp_ajustada)
    atual = vp_ajustada[competencias[-1]]
    base = vp_ajustada.get(competencia_menos_meses(competencias[-1], meses))
    if base in (None, 0):
        return None
    return 100 * (atual - base) / abs(base)
