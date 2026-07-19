"""Cache local de dados oficiais em SQLite.

O banco fica em ``~/.scout/scout.db`` (ou no diretório apontado
pela variável de ambiente ``SCOUT_DATA_DIR``). Toda análise lê daqui;
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
    cnpj               TEXT NOT NULL,
    competencia        TEXT NOT NULL,  -- AAAA-MM
    nome               TEXT,
    segmento           TEXT,
    tipo_gestao        TEXT,
    isin               TEXT,
    cotas_emitidas     REAL,
    administrador      TEXT,
    cnpj_administrador TEXT,
    PRIMARY KEY (cnpj, competencia)
);
CREATE INDEX IF NOT EXISTS idx_gerais_admin ON informes_gerais (cnpj_administrador);
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
CREATE TABLE IF NOT EXISTS imoveis (
    cnpj          TEXT NOT NULL,
    competencia   TEXT NOT NULL,  -- AAAA-MM do trimestre
    nome          TEXT NOT NULL,
    endereco      TEXT,
    area          REAL,
    vacancia      REAL,  -- fração (0.12 = 12%)
    inadimplencia REAL,  -- fração
    pct_receita   REAL,  -- percentual (0-100), escala da própria CVM
    PRIMARY KEY (cnpj, competencia, nome)
);
CREATE TABLE IF NOT EXISTS resultados_trimestrais (
    cnpj                   TEXT NOT NULL,
    competencia            TEXT NOT NULL,  -- AAAA-MM do trimestre
    resultado_financeiro   REAL,  -- R$ no trimestre
    rendimentos_declarados REAL,  -- R$ no trimestre
    lucro_contabil         REAL,
    resultado_acumulado    REAL,  -- resultado financeiro líquido ACUMULADO (reserva)
    PRIMARY KEY (cnpj, competencia)
);
CREATE TABLE IF NOT EXISTS documentos (
    cnpj         TEXT NOT NULL,
    id_fnet      INTEGER NOT NULL,
    tipo         TEXT,
    categoria    TEXT,
    data_entrega TEXT,
    arquivo      TEXT,   -- caminho local do PDF baixado
    PRIMARY KEY (cnpj, id_fnet)
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
CREATE TABLE IF NOT EXISTS setores_inquilinos (
    cnpj            TEXT NOT NULL,
    competencia     TEXT NOT NULL,  -- AAAA-MM do trimestre
    item            INTEGER NOT NULL,  -- posição no arquivo (imóvel+setor repetem)
    imovel          TEXT,
    setor           TEXT,
    pct_receita_fii REAL,           -- fração (1.0 = 100%)
    PRIMARY KEY (cnpj, competencia, item)
);
CREATE TABLE IF NOT EXISTS cotacoes_b3 (
    ticker      TEXT NOT NULL,
    competencia TEXT NOT NULL,  -- AAAA-MM
    fechamento  REAL,           -- último fechamento NOMINAL do mês (COTAHIST)
    dia         TEXT,           -- data do pregão usado (AAAA-MM-DD)
    PRIMARY KEY (ticker, competencia)
);
CREATE TABLE IF NOT EXISTS cadastro (
    cnpj               TEXT PRIMARY KEY,  -- só dígitos (formato do registro CVM)
    denominacao        TEXT,
    situacao           TEXT,
    administrador      TEXT,
    cnpj_administrador TEXT,
    gestor             TEXT,
    cnpj_gestor        TEXT,              -- CPF ou CNPJ da gestora, só dígitos
    tipo_pessoa_gestor TEXT
);
CREATE TABLE IF NOT EXISTS cadastro_meta (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    atualizado_em TEXT
);
"""


def so_digitos(texto: str | None) -> str:
    return "".join(c for c in texto or "" if c.isdigit())


def diretorio_dados() -> Path:
    configurado = os.environ.get("SCOUT_DATA_DIR") or os.environ.get("FATO_DATA_DIR")
    if configurado:
        return Path(configurado)
    novo = Path.home() / ".scout"
    legado = Path.home() / ".fato-relevante"  # era Fato Relevante (rebrand 07/2026)
    if legado.exists() and not novo.exists():
        try:
            legado.rename(novo)
        except OSError:
            return legado  # em uso por outro processo: segue no lugar antigo
    return novo


def conectar(diretorio: Path | None = None) -> sqlite3.Connection:
    destino = Path(diretorio) if diretorio else diretorio_dados()
    destino.mkdir(parents=True, exist_ok=True)
    banco_legado = destino / "fato.db"
    banco = destino / "scout.db"
    if banco_legado.exists() and not banco.exists():
        banco_legado.rename(banco)
    con = sqlite3.connect(banco)
    con.row_factory = sqlite3.Row
    _migrar(con)
    con.executescript(_SCHEMA)
    return con


def _migrar(con: sqlite3.Connection) -> None:
    """Ajusta bases criadas por versões antigas do schema."""
    tabelas = {linha[0] for linha in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "informes_gerais" not in tabelas:
        return
    colunas = {linha[1] for linha in con.execute("PRAGMA table_info(informes_gerais)")}
    if "administrador" not in colunas:
        con.execute("ALTER TABLE informes_gerais ADD COLUMN administrador TEXT")
        con.execute("ALTER TABLE informes_gerais ADD COLUMN cnpj_administrador TEXT")
        # força a recarga dos informes mensais para preencher o administrador histórico
        con.execute("DELETE FROM cargas WHERE arquivo LIKE 'inf_mensal%'")
        con.commit()
    if "resultados_trimestrais" in tabelas:
        colunas_resultados = {
            linha[1] for linha in con.execute("PRAGMA table_info(resultados_trimestrais)")
        }
        if "resultado_acumulado" not in colunas_resultados:
            con.execute("ALTER TABLE resultados_trimestrais ADD COLUMN resultado_acumulado REAL")
            # recarga dos trimestrais para preencher o acumulado histórico
            con.execute("DELETE FROM cargas WHERE arquivo LIKE 'inf_trimestral%'")
            con.commit()


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


def gravar_cadastro(con: sqlite3.Connection, linhas: list[tuple], atualizado_em: str) -> int:
    """Cadastro CVM (registro de fundos): gestora e administrador por CNPJ.
    `linhas` = (cnpj_digitos, denominacao, situacao, administrador,
    cnpj_administrador, gestor, cnpj_gestor_digitos, tipo_pessoa_gestor)."""
    con.executemany(
        """
        INSERT OR REPLACE INTO cadastro
            (cnpj, denominacao, situacao, administrador, cnpj_administrador,
             gestor, cnpj_gestor, tipo_pessoa_gestor)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        linhas,
    )
    con.execute(
        "INSERT OR REPLACE INTO cadastro_meta (id, atualizado_em) VALUES (1, ?)",
        (atualizado_em,),
    )
    con.commit()
    return len(linhas)


def cadastro_meta(con: sqlite3.Connection) -> sqlite3.Row | None:
    return con.execute("SELECT * FROM cadastro_meta WHERE id = 1").fetchone()


def cadastro_do_fundo(con: sqlite3.Connection, cnpj: str) -> sqlite3.Row | None:
    return con.execute(
        "SELECT * FROM cadastro WHERE cnpj = ?", (so_digitos(cnpj),)
    ).fetchone()


def fundos_do_gestor(
    con: sqlite3.Connection, cnpj_gestor: str, excluir_cnpj: str
) -> list[sqlite3.Row]:
    """Outros fundos da mesma gestora (cadastro CVM), com os dados do informe
    mais recente — mesma forma de fundos_do_administrador."""
    return con.execute(
        """
        WITH ultimo AS (
            SELECT cnpj, MAX(competencia) AS competencia
              FROM informes_gerais
             GROUP BY cnpj
        )
        SELECT g.cnpj,
               g.nome,
               g.segmento,
               g.isin,
               (SELECT MIN(competencia) FROM informes_gerais i WHERE i.cnpj = g.cnpj) AS inicio,
               g.competencia AS fim
          FROM informes_gerais g
          JOIN ultimo u ON u.cnpj = g.cnpj AND u.competencia = g.competencia
          JOIN cadastro c
            ON c.cnpj = REPLACE(REPLACE(REPLACE(g.cnpj, '.', ''), '/', ''), '-', '')
         WHERE c.cnpj_gestor = ?
           AND c.cnpj <> ?
         ORDER BY inicio
        """,
        (so_digitos(cnpj_gestor), so_digitos(excluir_cnpj)),
    ).fetchall()


def administrador_do_fundo(con: sqlite3.Connection, cnpj: str) -> sqlite3.Row | None:
    """Administrador mais recente informado pelo fundo."""
    return con.execute(
        """
        SELECT administrador, cnpj_administrador
          FROM informes_gerais
         WHERE cnpj = ? AND administrador IS NOT NULL
         ORDER BY competencia DESC
         LIMIT 1
        """,
        (cnpj,),
    ).fetchone()


def fundos_do_administrador(
    con: sqlite3.Connection, cnpj_administrador: str, excluir_cnpj: str
) -> list[sqlite3.Row]:
    """Outros fundos cujo informe mais recente aponta o mesmo administrador."""
    return con.execute(
        """
        WITH ultimo AS (
            SELECT cnpj, MAX(competencia) AS competencia
              FROM informes_gerais
             GROUP BY cnpj
        )
        SELECT g.cnpj,
               g.nome,
               g.segmento,
               g.isin,
               (SELECT MIN(competencia) FROM informes_gerais i WHERE i.cnpj = g.cnpj) AS inicio,
               g.competencia AS fim
          FROM informes_gerais g
          JOIN ultimo u ON u.cnpj = g.cnpj AND u.competencia = g.competencia
         WHERE g.cnpj_administrador = ?
           AND g.cnpj <> ?
         ORDER BY inicio
        """,
        (cnpj_administrador, excluir_cnpj),
    ).fetchall()


def gravar_documento(
    con: sqlite3.Connection,
    cnpj: str,
    id_fnet: int,
    tipo: str,
    categoria: str,
    data_entrega: str,
    arquivo: str,
) -> None:
    con.execute(
        """
        INSERT OR REPLACE INTO documentos
            (cnpj, id_fnet, tipo, categoria, data_entrega, arquivo)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (cnpj, id_fnet, tipo, categoria, data_entrega, arquivo),
    )
    con.commit()


def documento(con: sqlite3.Connection, cnpj: str, id_fnet: int) -> sqlite3.Row | None:
    return con.execute(
        "SELECT * FROM documentos WHERE cnpj = ? AND id_fnet = ?", (cnpj, id_fnet)
    ).fetchone()


def serie_imoveis(con: sqlite3.Connection, cnpj: str) -> list[sqlite3.Row]:
    return con.execute(
        "SELECT * FROM imoveis WHERE cnpj = ? ORDER BY competencia, nome", (cnpj,)
    ).fetchall()


def imoveis_atuais(con: sqlite3.Connection, cnpj: str) -> list[sqlite3.Row]:
    return con.execute(
        """
        SELECT * FROM imoveis
         WHERE cnpj = ?
           AND competencia = (SELECT MAX(competencia) FROM imoveis WHERE cnpj = ?)
         ORDER BY pct_receita DESC, area DESC
        """,
        (cnpj, cnpj),
    ).fetchall()


def setores_atuais(con: sqlite3.Connection, cnpj: str) -> list[sqlite3.Row]:
    """% da receita do FII por setor de inquilino, no trimestre mais recente."""
    return con.execute(
        """
        SELECT setor, SUM(pct_receita_fii) AS pct
          FROM setores_inquilinos
         WHERE cnpj = ?
           AND competencia = (SELECT MAX(competencia) FROM setores_inquilinos WHERE cnpj = ?)
           AND pct_receita_fii > 0
         GROUP BY setor
         ORDER BY pct DESC
        """,
        (cnpj, cnpj),
    ).fetchall()


def serie_resultados(con: sqlite3.Connection, cnpj: str) -> list[sqlite3.Row]:
    return con.execute(
        "SELECT * FROM resultados_trimestrais WHERE cnpj = ? ORDER BY competencia",
        (cnpj,),
    ).fetchall()


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
