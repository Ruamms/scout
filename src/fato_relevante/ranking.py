"""Varredura da base inteira: resumo + red flags de todos os fundos.

Alimenta o `fato ranking` e a comparação com pares do segmento. Tudo em
poucas consultas agrupadas (uma passada por tabela) — a base toda é
avaliada em segundos.

Ranking é fato ordenado com critério explícito — nunca recomendação: o
critério aparece sempre no cabeçalho da saída.
"""

from __future__ import annotations

import dataclasses
import sqlite3

from . import redflags, series
from .modelos import Selo
from .redflags.contexto import Contexto


@dataclasses.dataclass(frozen=True)
class FundoResumo:
    cnpj: str
    ticker: str
    nome: str
    segmento: str
    dy_12m: float | None   # % acumulado 12 meses
    pvp: float | None      # só quando há cotação em cache
    cotacao: float | None
    pl: float | None
    cotistas: float | None
    meses: int
    flags: int             # alertas disparados (sem regras de cotação)
    selo: Selo
    motivos: tuple[str, ...] = ()  # títulos dos alertas disparados


# critério -> (descrição exibida, campo, maior é melhor?)
CRITERIOS = {
    "dy": ("maior DY acumulado 12 meses", "dy_12m", True),
    "pvp": ("menor P/VP — só fundos com cotação em cache", "pvp", False),
    "pl": ("maior patrimônio líquido", "pl", True),
    "cotistas": ("maior número de cotistas", "cotistas", True),
    "cotacao": ("menor preço da cota — só fundos com cotação em cache", "cotacao", False),
}


@dataclasses.dataclass(frozen=True)
class Ranking:
    criterio: str
    descricao: str
    filtros: str
    total_avaliado: int
    linhas: list[FundoResumo]


def montar(
    con: sqlite3.Connection,
    por: str = "dy",
    top: int = 10,
    sem_alertas: bool = False,
    segmento: str | None = None,
    apenas_negociaveis: bool = True,
) -> Ranking:
    if por not in CRITERIOS:
        raise ValueError(f"critério desconhecido: {por} (use {', '.join(CRITERIOS)})")
    descricao, campo, decrescente = CRITERIOS[por]
    fundos = varrer(con)
    total = len(fundos)
    filtros = []
    if apenas_negociaveis:
        fundos = [f for f in fundos if f.ticker]
        filtros.append("apenas fundos com ticker (negociáveis em bolsa)")
    if segmento:
        fundos = [f for f in fundos if segmento.lower() in f.segmento.lower()]
        filtros.append(f"segmento contém '{segmento}'")
    if sem_alertas:
        fundos = [f for f in fundos if f.selo.nivel in ("sem_alertas", "leves")]
        filtros.append("sem alertas de atenção ou graves (selo verde ou amarelo)")
    candidatos = [f for f in fundos if getattr(f, campo) is not None]
    candidatos.sort(key=lambda f: getattr(f, campo), reverse=decrescente)
    return Ranking(
        criterio=por,
        descricao=descricao,
        filtros="; ".join(filtros),
        total_avaliado=total,
        linhas=candidatos[:top],
    )


def varrer(con: sqlite3.Connection, cnpjs: set[str] | None = None) -> list[FundoResumo]:
    """Resumo + red flags de todos os fundos com informe recente."""
    gerais = _gerais_por_cnpj(con)
    complementos = _agrupar(con, "SELECT * FROM informes_complemento ORDER BY cnpj, competencia")
    imoveis = _imoveis_ultima_competencia(con)
    resultados = _agrupar(con, "SELECT * FROM resultados_trimestrais ORDER BY cnpj, competencia")
    precos = {
        linha["ticker"]: linha["preco_atual"]
        for linha in con.execute("SELECT ticker, preco_atual FROM cotacoes_meta")
    }
    corte = _corte_atividade(complementos)

    resumos = []
    for cnpj, serie in complementos.items():
        if cnpjs is not None and cnpj not in cnpjs:
            continue
        if serie[-1]["competencia"] < corte:
            continue  # fundo sem informe recente (encerrado/inativo)
        geral = gerais.get(cnpj)
        ticker = series.ticker_do_isin(geral["isin"]) if geral else ""
        atual = serie[-1]
        preco = precos.get(ticker)
        dy = series.dy_acumulado(serie, 12)
        contexto = Contexto(
            serie=serie,
            vp_ajustada=series.serie_vp_ajustada(serie),
            imoveis_atuais=imoveis.get(cnpj, []),
            resultados=resultados.get(cnpj, []),
        )
        resultado = redflags.avaliar(contexto)
        resumos.append(
            FundoResumo(
                cnpj=cnpj,
                ticker=ticker,
                nome=(geral["nome"] if geral else None) or cnpj,
                segmento=(geral["segmento"] if geral else None) or "—",
                dy_12m=dy * 100 if dy is not None and len(serie) >= 12 else None,
                pvp=preco / atual["vp_cota"] if preco and atual["vp_cota"] else None,
                cotacao=preco,
                pl=atual["patrimonio_liquido"],
                cotistas=atual["cotistas"],
                meses=len(serie),
                flags=len(resultado.flags),
                selo=redflags.selo(resultado),
                motivos=tuple(flag.titulo for flag in resultado.flags),
            )
        )
    return resumos


def _gerais_por_cnpj(con: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    return {
        linha["cnpj"]: linha
        for linha in con.execute(
            """
            WITH ultimo AS (
                SELECT cnpj, MAX(competencia) AS competencia FROM informes_gerais GROUP BY cnpj
            )
            SELECT g.* FROM informes_gerais g
            JOIN ultimo u ON u.cnpj = g.cnpj AND u.competencia = g.competencia
            """
        )
    }


def _agrupar(con: sqlite3.Connection, sql: str) -> dict[str, list[sqlite3.Row]]:
    grupos: dict[str, list[sqlite3.Row]] = {}
    for linha in con.execute(sql):
        grupos.setdefault(linha["cnpj"], []).append(linha)
    return grupos


def _imoveis_ultima_competencia(con: sqlite3.Connection) -> dict[str, list[sqlite3.Row]]:
    grupos: dict[str, list[sqlite3.Row]] = {}
    for linha in con.execute(
        """
        WITH ultimo AS (SELECT cnpj, MAX(competencia) AS competencia FROM imoveis GROUP BY cnpj)
        SELECT i.* FROM imoveis i
        JOIN ultimo u ON u.cnpj = i.cnpj AND u.competencia = i.competencia
        ORDER BY i.cnpj, i.pct_receita DESC
        """
    ):
        grupos.setdefault(linha["cnpj"], []).append(linha)
    return grupos


def _corte_atividade(complementos: dict[str, list]) -> str:
    """Competência mínima para o fundo contar como ativo (máx global - 2 meses)."""
    if not complementos:
        return ""
    maxima = max(serie[-1]["competencia"] for serie in complementos.values())
    return series.competencia_menos_meses(maxima, 2)
