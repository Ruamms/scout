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
CREATE TABLE IF NOT EXISTS dfp_meta (
    cod_cvm               TEXT NOT NULL,
    ano                   INTEGER NOT NULL,
    dt_receb              TEXT,     -- quando a DFP foi entregue à CVM
    versao                INTEGER,  -- >1 = balanço reapresentado/republicado
    acoes_total           REAL,     -- capital integralizado (composicao_capital)
    acoes_tesouro         REAL,
    parecer_tipo          TEXT,     -- classificação da própria CVM (TP_RELAT_AUD)
    parecer_continuidade  INTEGER,  -- incerteza de continuidade operacional no texto
    parecer_trecho        TEXT,
    PRIMARY KEY (cod_cvm, ano)
);
CREATE TABLE IF NOT EXISTS auditores (
    cod_cvm TEXT NOT NULL,
    auditor TEXT NOT NULL,
    inicio  TEXT,   -- Data_Inicio_Atuacao_Auditor (FCA)
    fim     TEXT,
    PRIMARY KEY (cod_cvm, auditor, inicio)
);
CREATE TABLE IF NOT EXISTS administradores (
    cod_cvm          TEXT NOT NULL,
    nome             TEXT NOT NULL,
    orgao            TEXT,   -- conselho de administração / diretoria / fiscal
    cargo            TEXT,
    profissao        TEXT,
    controlador      INTEGER, -- eleito pelo controlador?
    primeiro_mandato TEXT,    -- desde quando está na casa
    mandatos         REAL,    -- nº de mandatos consecutivos
    presenca         REAL,    -- % de participação nas reuniões
    experiencia      TEXT,    -- resumo profissional declarado no FRE
    referencia       TEXT,    -- Data_Referencia do FRE
    PRIMARY KEY (cod_cvm, nome, cargo)
);
CREATE TABLE IF NOT EXISTS partes_relacionadas (
    cod_cvm   TEXT NOT NULL,
    parte     TEXT NOT NULL,
    relacao   TEXT,
    objeto    TEXT,
    montante  REAL,
    saldo     TEXT,
    juros     TEXT,
    data      TEXT,   -- Data_Transacao
    referencia TEXT,
    PRIMARY KEY (cod_cvm, parte, data, objeto)
);
CREATE TABLE IF NOT EXISTS informes_ativo (
    cnpj        TEXT NOT NULL,
    competencia TEXT NOT NULL,  -- AAAA-MM
    tijolo      REAL,           -- R$ em imóveis/direitos reais (tijolo)
    papel       REAL,           -- R$ em CRI/LCI/recebíveis imobiliários (papel)
    fof         REAL,           -- R$ em cotas de outros fundos: FII/FIP/FI (fundo de fundos)
    outros      REAL,           -- caixa, títulos públicos, ações etc. (não decidem o tipo)
    total       REAL,           -- soma tijolo+papel+fof+outros
    PRIMARY KEY (cnpj, competencia)
);
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
    taxa_adm_mes           REAL,  -- % de despesa com taxa de administração no mês (fração do PL)
    PRIMARY KEY (cnpj, competencia)
);
CREATE TABLE IF NOT EXISTS etfs (
    cnpj          TEXT PRIMARY KEY,  -- só dígitos
    ticker        TEXT,              -- código de negociação (BOVA11)
    radical       TEXT,              -- idCEM na B3 (BOVA)
    id_fnet       INTEGER,
    tipo_b3       TEXT,              -- 'ETF' (renda variável) | 'ETF-RF' (renda fixa)
    denominacao   TEXT,
    nome_pregao   TEXT,
    atualizado_em TEXT,
    listado       INTEGER DEFAULT 1  -- 0 = sumiu da listagem da B3 (deslistado)
);
CREATE TABLE IF NOT EXISTS etf_proventos (
    cnpj           TEXT NOT NULL,
    id_doc         INTEGER NOT NULL,  -- documento estruturado no FNET
    ticker         TEXT,
    data_base      TEXT,              -- AAAA-MM-DD
    valor          REAL,              -- R$ por cota
    data_pagamento TEXT,
    isento         INTEGER,           -- rendimento de ETF NÃO costuma ser isento
    PRIMARY KEY (cnpj, id_doc)
);
CREATE TABLE IF NOT EXISTS etf_posicoes (
    cnpj         TEXT NOT NULL,
    competencia  TEXT NOT NULL,
    item         INTEGER NOT NULL,  -- posição no top 10 (0 = maior)
    codigo       TEXT,              -- ticker do ativo quando o CDA informa (ações)
    nome         TEXT,
    cnpj_emissor TEXT,              -- para casar cotas de fundos com a nossa base
    pct          REAL,
    quantidade   REAL,              -- QT_POS_FINAL do CDA (para reprecificar a preço de hoje)
    grupo        TEXT,              -- tipo do ativo (Ações/Renda Fixa/Exterior/Cotas de Fundos)
    PRIMARY KEY (cnpj, competencia, item)
);
CREATE TABLE IF NOT EXISTS etf_carteira (
    cnpj        TEXT NOT NULL,
    competencia TEXT NOT NULL,  -- AAAA-MM do CDA
    grupo       TEXT NOT NULL,  -- Renda Fixa | Ações | Exterior | Cotas de Fundos
    pct         REAL,
    PRIMARY KEY (cnpj, competencia, grupo)
);
CREATE TABLE IF NOT EXISTS etf_pl (
    cnpj        TEXT NOT NULL,
    competencia TEXT NOT NULL,
    pl          REAL,
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
    volume      REAL,           -- volume financeiro somado no mês (R$)
    pregoes     INTEGER,        -- dias com negócio no mês
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
CREATE TABLE IF NOT EXISTS empresas (
    cod_cvm           TEXT PRIMARY KEY,  -- chave que casa B3 <-> datasets CIA_ABERTA da CVM
    cnpj              TEXT,              -- só dígitos
    radical           TEXT,              -- issuingCompany na B3 (PETR)
    nome              TEXT,              -- razão social
    nome_pregao       TEXT,
    setor_b3          TEXT,              -- classificação em 3 níveis da B3
    setor_cvm         TEXT,              -- SETOR_ATIV do cadastro CVM
    situacao          TEXT,              -- SIT no cadastro CVM (ATIVO/CANCELADA/SUSPENSO)
    auditor           TEXT,              -- AUDITOR no cadastro CVM
    segmento_listagem TEXT,              -- Novo Mercado, N2, N1...
    no_ibrx100        INTEGER,           -- 1 = escopo v1
    acoes_on          REAL,              -- ações ordinárias em circulação (B3)
    acoes_pn          REAL,              -- ações preferenciais em circulação (B3)
    acoes_total       REAL,              -- total de ações (base do market cap / LPA / VPA)
    atualizado_em     TEXT
);
CREATE TABLE IF NOT EXISTS papeis (
    ticker  TEXT PRIMARY KEY,  -- PETR4
    cod_cvm TEXT NOT NULL,
    isin    TEXT,
    tipo    TEXT               -- ON | PN | PNA | PNB | UNT
);
CREATE TABLE IF NOT EXISTS fundamentos (
    cod_cvm            TEXT NOT NULL,
    ano                INTEGER NOT NULL,  -- exercício (DT_FIM_EXERC)
    receita            REAL,   -- em reais (escala já aplicada)
    resultado_bruto    REAL,
    ebit               REAL,   -- só comercial; nulo em instituição financeira
    lucro_liquido      REAL,
    ativo_total        REAL,
    patrimonio_liquido REAL,
    caixa              REAL,   -- caixa + aplicações financeiras
    divida_bruta       REAL,   -- empréstimos e financiamentos (circ + não circ)
    da                 REAL,   -- depreciação/amortização (DFC) — base do EBITDA
    setor_financeiro   INTEGER DEFAULT 0,  -- 1 = DRE de intermediação (banco/seguradora)
    PRIMARY KEY (cod_cvm, ano)
);
CREATE TABLE IF NOT EXISTS acao_eventos (
    ticker TEXT NOT NULL,
    data   TEXT NOT NULL,  -- lastDatePrior (último dia "com"), AAAA-MM-DD
    label  TEXT NOT NULL,  -- DESDOBRAMENTO | GRUPAMENTO | BONIFICACAO
    fator  REAL NOT NULL,  -- multiplicador da QUANTIDADE de ações (2.0 = dobrou)
    PRIMARY KEY (ticker, data, label)
);
CREATE TABLE IF NOT EXISTS acao_proventos (
    ticker   TEXT NOT NULL,
    data_com TEXT NOT NULL,  -- último dia "com" direito (lastDatePrior)
    label    TEXT NOT NULL,  -- DIVIDENDO | JRS CAP PROPRIO...
    valor    REAL NOT NULL,  -- R$ por ação, base NOMINAL da época
    PRIMARY KEY (ticker, data_com, label, valor)
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
    if "cotacoes_b3" in tabelas:
        colunas_b3 = {linha[1] for linha in con.execute("PRAGMA table_info(cotacoes_b3)")}
        if "volume" not in colunas_b3:
            con.execute("ALTER TABLE cotacoes_b3 ADD COLUMN volume REAL")
            con.execute("ALTER TABLE cotacoes_b3 ADD COLUMN pregoes INTEGER")
            con.commit()
    if "etfs" in tabelas:
        colunas_etfs = {linha[1] for linha in con.execute("PRAGMA table_info(etfs)")}
        if "listado" not in colunas_etfs:
            con.execute("ALTER TABLE etfs ADD COLUMN listado INTEGER DEFAULT 1")
            con.commit()
    if "informes_complemento" in tabelas:
        colunas_compl = {linha[1] for linha in con.execute("PRAGMA table_info(informes_complemento)")}
        if "taxa_adm_mes" not in colunas_compl:
            con.execute("ALTER TABLE informes_complemento ADD COLUMN taxa_adm_mes REAL")
            # recarrega os mensais para preencher a taxa de administração histórica
            con.execute("DELETE FROM cargas WHERE arquivo LIKE 'inf_mensal%'")
            con.commit()
    if "etf_posicoes" in tabelas:
        colunas_pos = {linha[1] for linha in con.execute("PRAGMA table_info(etf_posicoes)")}
        # CDA v3: carteira COMPLETA (todas as posições) + quantidade + grupo (tipo
        # do ativo, para reprecificar a preço de hoje). Reprocessa o CDA p/ preencher.
        # CDA v4: vencimento — títulos públicos são identificados por CD_SELIC +
        # DT_VENC (chave que casa com o PU diário da ANBIMA no precos.py).
        faltantes = {"quantidade": "REAL", "grupo": "TEXT", "vencimento": "TEXT"}.items()
        novas = [(col, tipo) for col, tipo in faltantes if col not in colunas_pos]
        if novas:
            for col, tipo in novas:
                con.execute(f"ALTER TABLE etf_posicoes ADD COLUMN {col} {tipo}")
            con.execute("DELETE FROM cargas WHERE arquivo LIKE 'cda_fi_%'")
            con.commit()
    if "empresas" in tabelas:
        colunas_emp = {linha[1] for linha in con.execute("PRAGMA table_info(empresas)")}
        faltantes_emp = [c for c in ("acoes_on", "acoes_pn", "acoes_total") if c not in colunas_emp]
        if faltantes_emp:
            for col in faltantes_emp:
                con.execute(f"ALTER TABLE empresas ADD COLUMN {col} REAL")
            # re-sincroniza as empresas na B3 para preencher as ações em circulação
            con.execute("DELETE FROM cargas WHERE arquivo = 'EMPRESAS_B3'")
            con.commit()
    if "fundamentos" in tabelas:
        colunas_fund = {linha[1] for linha in con.execute("PRAGMA table_info(fundamentos)")}
        if "da" not in colunas_fund:
            con.execute("ALTER TABLE fundamentos ADD COLUMN da REAL")
            # re-baixa a DFP para preencher o D&A (base do EBITDA)
            con.execute("DELETE FROM cargas WHERE arquivo LIKE 'DFP_%'")
            con.commit()
    if "cargas" in tabelas:
        marcador_cda = con.execute(
            "SELECT 1 FROM cargas WHERE arquivo = 'CDA_V2_POSICOES'"
        ).fetchone()
        if marcador_cda is None:
            # CDA v2: passamos a extrair também as principais posições
            con.execute("DELETE FROM cargas WHERE arquivo LIKE 'cda_fi_%'")
            con.execute(
                "INSERT INTO cargas (arquivo, carregado_em) VALUES ('CDA_V2_POSICOES', datetime('now'))"
            )
            con.commit()
        marcador = con.execute(
            "SELECT 1 FROM cargas WHERE arquivo = 'COTAHIST_V3_ETFS_VOLUME'"
        ).fetchone()
        if marcador is None:
            # COTAHIST v3: os arquivos passaram a incluir ETFs (codbdi 14) e o
            # volume financeiro; bases carregadas antes disso precisam rebaixar
            con.execute(
                "DELETE FROM cargas WHERE arquivo LIKE 'COTAHIST_A%' OR arquivo LIKE 'COTAHIST_M%'"
                " OR arquivo = 'COTAHIST_V2_ETFS'"
            )
            con.execute(
                "INSERT INTO cargas (arquivo, carregado_em) VALUES ('COTAHIST_V3_ETFS_VOLUME', datetime('now'))"
            )
            con.commit()
        marcador_v4 = con.execute(
            "SELECT 1 FROM cargas WHERE arquivo = 'COTAHIST_V4_ACOES'"
        ).fetchone()
        if marcador_v4 is None:
            # COTAHIST v4: entra o codbdi 02 (ações do lote padrão); bases
            # carregadas antes precisam rebaixar os arquivos (uma vez só)
            con.execute(
                "DELETE FROM cargas WHERE arquivo LIKE 'COTAHIST_A%' OR arquivo LIKE 'COTAHIST_M%'"
            )
            con.execute(
                "INSERT INTO cargas (arquivo, carregado_em) VALUES ('COTAHIST_V4_ACOES', datetime('now'))"
            )
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


def _ativos_ultimos(con: sqlite3.Connection) -> list[sqlite3.Row]:
    """Composição (tijolo/papel/fof) da competência mais recente de cada FII."""
    return con.execute(
        """
        WITH ultimo AS (
            SELECT cnpj, MAX(competencia) AS competencia
              FROM informes_ativo GROUP BY cnpj
        )
        SELECT a.cnpj, a.tijolo, a.papel, a.fof, a.total, a.competencia
          FROM informes_ativo a
          JOIN ultimo u ON u.cnpj = a.cnpj AND u.competencia = a.competencia
        """
    ).fetchall()


def tipos_fii(con: sqlite3.Connection) -> dict[str, str]:
    """{cnpj: tipo} derivado da composição mais recente. Fundos sem ativo_passivo
    (ou sem base imobiliária) ficam de fora."""
    from . import tipo_fii as _tipo

    saida: dict[str, str] = {}
    for linha in _ativos_ultimos(con):
        tipo = _tipo.classificar(linha["tijolo"] or 0, linha["papel"] or 0, linha["fof"] or 0)
        if tipo:
            saida[linha["cnpj"]] = tipo
    return saida


def composicao_ativo(con: sqlite3.Connection, cnpj: str) -> sqlite3.Row | None:
    """Composição do ativo (última competência) de um FII, para o selo/tipo."""
    return con.execute(
        """
        SELECT * FROM informes_ativo
         WHERE cnpj = ?
         ORDER BY competencia DESC
         LIMIT 1
        """,
        (cnpj,),
    ).fetchone()


def etf_por_ticker(con: sqlite3.Connection, ticker: str) -> sqlite3.Row | None:
    return con.execute(
        "SELECT * FROM etfs WHERE ticker = ?", (ticker.strip().upper(),)
    ).fetchone()


def etfs_listados(con: sqlite3.Connection) -> list[sqlite3.Row]:
    """ETFs com código de negociação E ainda listados na B3 (deslistado não
    negocia mais — sai do site e do lote de leitura)."""
    return con.execute(
        "SELECT * FROM etfs WHERE ticker IS NOT NULL AND ticker <> ''"
        " AND (listado IS NULL OR listado = 1) ORDER BY ticker"
    ).fetchall()


def empresa_por_ticker(con: sqlite3.Connection, ticker: str) -> sqlite3.Row | None:
    """Empresa dona do papel (PETR4 -> Petrobras)."""
    return con.execute(
        """
        SELECT e.*, p.ticker AS ticker_consultado, p.tipo AS tipo_papel
          FROM papeis p JOIN empresas e ON e.cod_cvm = p.cod_cvm
         WHERE p.ticker = ?
        """,
        (ticker.strip().upper(),),
    ).fetchone()


def empresas_listadas(con: sqlite3.Connection, so_ibrx: bool = True) -> list[sqlite3.Row]:
    """Empresas do escopo (v1 = IBrX-100), para o site e o lote."""
    filtro = "WHERE no_ibrx100 = 1" if so_ibrx else ""
    return con.execute(f"SELECT * FROM empresas {filtro} ORDER BY radical").fetchall()


def papeis_da_empresa(con: sqlite3.Connection, cod_cvm: str) -> list[sqlite3.Row]:
    return con.execute(
        "SELECT * FROM papeis WHERE cod_cvm = ? ORDER BY ticker", (cod_cvm,)
    ).fetchall()


def fundamentos_da_empresa(con: sqlite3.Connection, cod_cvm: str) -> list[sqlite3.Row]:
    """Série anual de balanços da empresa (mais antigo → mais recente)."""
    return con.execute(
        "SELECT * FROM fundamentos WHERE cod_cvm = ? ORDER BY ano", (cod_cvm,)
    ).fetchall()


def dfp_meta_da_empresa(con: sqlite3.Connection, cod_cvm: str) -> list[sqlite3.Row]:
    """Metadados societários da DFP por ano (entrega, versão, capital, parecer)."""
    return con.execute(
        "SELECT * FROM dfp_meta WHERE cod_cvm = ? ORDER BY ano", (cod_cvm,)
    ).fetchall()


def auditores_da_empresa(con: sqlite3.Connection, cod_cvm: str) -> list[sqlite3.Row]:
    return con.execute(
        "SELECT * FROM auditores WHERE cod_cvm = ? ORDER BY inicio", (cod_cvm,)
    ).fetchall()


def proventos_por_ano(con: sqlite3.Connection, ticker: str) -> dict[int, float]:
    """{ano: R$/ação} somado pela data-com — base da regra 'proventos em prejuízo'."""
    return {
        int(linha[0]): float(linha[1])
        for linha in con.execute(
            "SELECT substr(data_com, 1, 4), SUM(valor) FROM acao_proventos"
            " WHERE ticker = ? GROUP BY substr(data_com, 1, 4)",
            (ticker.strip().upper(),),
        )
        if str(linha[0]).isdigit()
    }


def proventos_12m(con: sqlite3.Connection, ticker: str, hoje) -> float:
    """Soma dos proventos (R$/ação) com data-com nos últimos 365 dias — base do
    dividend yield. Zero (não None) quando o papel não pagou nada no período."""
    from datetime import timedelta

    corte = (hoje - timedelta(days=365)).isoformat()
    linha = con.execute(
        "SELECT COALESCE(SUM(valor), 0) FROM acao_proventos WHERE ticker = ? AND data_com >= ?",
        (ticker.strip().upper(), corte),
    ).fetchone()
    return float(linha[0]) if linha else 0.0


def liquidez_recente(con: sqlite3.Connection, ticker: str, meses: int = 3) -> float | None:
    """Volume financeiro médio POR PREGÃO nos últimos meses fechados (R$/dia)."""
    linhas = con.execute(
        """
        SELECT volume, pregoes FROM cotacoes_b3
         WHERE ticker = ? AND volume IS NOT NULL AND pregoes > 0
         ORDER BY competencia DESC LIMIT ?
        """,
        (ticker.strip().upper(), meses),
    ).fetchall()
    if not linhas:
        return None
    total_volume = sum(linha["volume"] for linha in linhas)
    total_pregoes = sum(linha["pregoes"] for linha in linhas)
    return total_volume / total_pregoes if total_pregoes else None


def etf_posicoes_atuais(con: sqlite3.Connection, cnpj: str) -> list[sqlite3.Row]:
    return con.execute(
        "SELECT * FROM etf_posicoes WHERE cnpj = ? ORDER BY item",
        (cnpj,),
    ).fetchall()


def ticker_fii_por_cnpj(con: sqlite3.Connection, cnpj_digitos: str) -> str | None:
    """Ticker de FII a partir do CNPJ (via ISIN do informe mais recente)."""
    if not cnpj_digitos:
        return None
    linha = con.execute(
        """
        SELECT isin FROM informes_gerais
         WHERE REPLACE(REPLACE(REPLACE(cnpj, '.', ''), '/', ''), '-', '') = ?
           AND isin IS NOT NULL
         ORDER BY competencia DESC LIMIT 1
        """,
        (cnpj_digitos,),
    ).fetchone()
    if linha is None:
        return None
    from . import series

    return series.ticker_do_isin(linha["isin"]) or None


def proventos_do_etf(con: sqlite3.Connection, cnpj: str, limite: int = 13) -> list[sqlite3.Row]:
    """Últimos proventos anunciados (mais recente primeiro)."""
    return con.execute(
        """
        SELECT * FROM etf_proventos
         WHERE cnpj = ?
         ORDER BY data_base DESC
         LIMIT ?
        """,
        (cnpj, limite),
    ).fetchall()


def etf_carteira_atual(con: sqlite3.Connection, cnpj: str) -> list[sqlite3.Row]:
    return con.execute(
        """
        SELECT grupo, pct, competencia FROM etf_carteira
         WHERE cnpj = ?
           AND competencia = (SELECT MAX(competencia) FROM etf_carteira WHERE cnpj = ?)
         ORDER BY pct DESC
        """,
        (cnpj, cnpj),
    ).fetchall()


def etf_pl_atual(con: sqlite3.Connection, cnpj: str) -> sqlite3.Row | None:
    return con.execute(
        """
        SELECT pl, competencia FROM etf_pl
         WHERE cnpj = ?
         ORDER BY competencia DESC LIMIT 1
        """,
        (cnpj,),
    ).fetchone()


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
