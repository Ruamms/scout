"""Cache local de dados oficiais em SQLite.

O banco fica em ``~/.fato-relevante/fato.db`` (ou no diretório apontado
pela variável de ambiente ``FATO_DATA_DIR``). Toda análise lê daqui;
nenhuma análise consulta a internet.
"""

from __future__ import annotations

import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cargas (
    arquivo      TEXT PRIMARY KEY,
    carregado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS informes_gerais (
    cnpj           TEXT NOT NULL,
    competencia    TEXT NOT NULL,  -- AAAA-MM
    nome           TEXT,
    segmento       TEXT,
    tipo_gestao    TEXT,
    isin           TEXT,
    cotas_emitidas REAL,
    PRIMARY KEY (cnpj, competencia)
);
CREATE INDEX IF NOT EXISTS idx_gerais_isin ON informes_gerais (isin);
CREATE TABLE IF NOT EXISTS cotacoes (
    ticker               TEXT NOT NULL,
    competencia          TEXT NOT NULL,  -- AAAA-MM
    fechamento           REAL,
    fechamento_ajustado  REAL,
    PRIMARY KEY (ticker, competencia)
);
CREATE TABLE IF NOT EXISTS cotacoes_meta (
    ticker        TEXT PRIMARY KEY,
    preco_atual   REAL,
    cotado_em     TEXT,  -- data do último pregão (AAAA-MM-DD)
    atualizado_em TEXT   -- data da última sincronização local (AAAA-MM-DD)
);
CREATE TABLE IF NOT EXISTS indices (
    serie       TEXT NOT NULL,  -- CDI, IPCA...
    competencia TEXT NOT NULL,  -- AAAA-MM
    valor       REAL,           -- % no mês
    PRIMARY KEY (serie, competencia)
);
CREATE TABLE IF NOT EXISTS indices_meta (
    serie         TEXT PRIMARY KEY,
    atualizado_em TEXT
);
CREATE TABLE IF NOT EXISTS informes_complemento (
    cnpj                   TEXT NOT NULL,
    competencia            TEXT NOT NULL,  -- AAAA-MM
    valor_ativo            REAL,
    patrimonio_liquido     REAL,
    cotas_emitidas         REAL,
    vp_cota                REAL,
    rentab_patrimonial_mes REAL,
    dy_mes                 REAL,
    amortizacao_mes        REAL,
    cotistas               REAL,
    PRIMARY KEY (cnpj, competencia)
);
"""


def diretorio_dados() -> Path:
    padrao = Path.home() / ".fato-relevante"
    return Path(os.environ.get("FATO_DATA_DIR") or padrao)


def conectar(diretorio: Path | None = None) -> sqlite3.Connection:
    destino = Path(diretorio) if diretorio else diretorio_dados()
    destino.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(destino / "fato.db")
    con.row_factory = sqlite3.Row
    con.executescript(_SCHEMA)
    return con


def base_vazia(con: sqlite3.Connection) -> bool:
    return con.execute("SELECT COUNT(*) FROM cargas").fetchone()[0] == 0


@dataclass(frozen=True)
class Fundo:
    cnpj: str
    nome: str
    segmento: str
    tipo_gestao: str


def resolver_fundo(con: sqlite3.Connection, ticker: str) -> Fundo | None:
    """Resolve um ticker (ex.: ADSH11) para o fundo correspondente.

    A CVM não publica o código de negociação, mas publica o ISIN — e o
    ISIN embute o radical do ticker: ADSH11 -> BRADSH... . É esse o
    vínculo usado aqui.
    """
    radical = re.match(r"([A-Za-z]{4})", ticker.strip())
    if not radical:
        return None
    padrao = f"BR{radical.group(1).upper()}%"
    linha = con.execute(
        """
        SELECT cnpj
          FROM informes_gerais
         WHERE isin LIKE ?
         ORDER BY competencia DESC
         LIMIT 1
        """,
        (padrao,),
    ).fetchone()
    if linha is None:
        return None
    cnpj = linha["cnpj"]
    dados = con.execute(
        """
        SELECT MAX(nome)        AS nome,
               MAX(segmento)    AS segmento,
               MAX(tipo_gestao) AS tipo_gestao
          FROM informes_gerais
         WHERE cnpj = ?
        """,
        (cnpj,),
    ).fetchone()
    return Fundo(
        cnpj=cnpj,
        nome=dados["nome"] or "",
        segmento=dados["segmento"] or "—",
        tipo_gestao=dados["tipo_gestao"] or "—",
    )


def serie_complemento(con: sqlite3.Connection, cnpj: str) -> list[sqlite3.Row]:
    return con.execute(
        "SELECT * FROM informes_complemento WHERE cnpj = ? ORDER BY competencia",
        (cnpj,),
    ).fetchall()


def gravar_cotacoes(
    con: sqlite3.Connection,
    ticker: str,
    candles: list[tuple[str, float, float]],
    preco_atual: float,
    cotado_em: str,
    atualizado_em: str,
) -> None:
    con.executemany(
        """
        INSERT OR REPLACE INTO cotacoes (ticker, competencia, fechamento, fechamento_ajustado)
        VALUES (?, ?, ?, ?)
        """,
        [(ticker, competencia, fechamento, ajustado) for competencia, fechamento, ajustado in candles],
    )
    con.execute(
        """
        INSERT OR REPLACE INTO cotacoes_meta (ticker, preco_atual, cotado_em, atualizado_em)
        VALUES (?, ?, ?, ?)
        """,
        (ticker, preco_atual, cotado_em, atualizado_em),
    )
    con.commit()


def serie_cotacoes(con: sqlite3.Connection, ticker: str) -> list[sqlite3.Row]:
    return con.execute(
        "SELECT * FROM cotacoes WHERE ticker = ? ORDER BY competencia",
        (ticker,),
    ).fetchall()


def cotacao_meta(con: sqlite3.Connection, ticker: str) -> sqlite3.Row | None:
    return con.execute(
        "SELECT * FROM cotacoes_meta WHERE ticker = ?", (ticker,)
    ).fetchone()


def gravar_indice(
    con: sqlite3.Connection,
    serie: str,
    valores: list[tuple[str, float]],
    atualizado_em: str,
) -> None:
    con.executemany(
        "INSERT OR REPLACE INTO indices (serie, competencia, valor) VALUES (?, ?, ?)",
        [(serie, competencia, valor) for competencia, valor in valores],
    )
    con.execute(
        "INSERT OR REPLACE INTO indices_meta (serie, atualizado_em) VALUES (?, ?)",
        (serie, atualizado_em),
    )
    con.commit()


def serie_indice(con: sqlite3.Connection, serie: str) -> dict[str, float]:
    return {
        linha["competencia"]: linha["valor"]
        for linha in con.execute(
            "SELECT competencia, valor FROM indices WHERE serie = ? ORDER BY competencia",
            (serie,),
        )
        if linha["valor"] is not None
    }


def indice_meta(con: sqlite3.Connection, serie: str) -> sqlite3.Row | None:
    return con.execute(
        "SELECT * FROM indices_meta WHERE serie = ?", (serie,)
    ).fetchone()
