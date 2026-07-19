from datetime import date

from scout.coleta import b3fundos


def _lista_fake(tipo: str) -> list[dict]:
    if tipo == "ETF":
        return [
            {"id": 9253, "acronym": "BMMT", "fundName": "B-INDEX MOMENTO FUNDO DE ÍNDICE", "tradingName": "B INDEX MOME"},
            {"id": 1234, "acronym": "BOVA", "fundName": "ISHARES IBOVESPA FUNDO DE ÍNDICE", "tradingName": "ISHARES BOVA"},
        ]
    if tipo == "ETF-RF":
        return [
            {"id": 5678, "acronym": "IMAB", "fundName": "IT NOW IMA-B FUNDO DE ÍNDICE RF", "tradingName": "IT NOW IMAB"},
        ]
    if tipo == "ETF-Cripto":
        return [
            {"id": 9012, "acronym": "HASH", "fundName": "HASHDEX NASDAQ CRYPTO INDEX FUNDO DE ÍNDICE", "tradingName": "HASHDEX NCI"},
        ]
    return []


_DETALHES = {
    9253: {"tradingCode": "BMMT11", "cnpj": "48.643.091/0001-00"},
    1234: {"tradingCode": "BOVA11", "cnpj": "10.406.511/0001-61"},
    5678: {"tradingCode": "IMAB11", "cnpj": "30.360.294/0001-56"},
    9012: {"tradingCode": "HASH11", "cnpj": "40.101.777/0001-72"},
}


def test_atualizar_etfs_grava_ticker_cnpj_e_tipo(con, monkeypatch):
    chamadas_detalhe = []

    def _detalhar_fake(id_fnet, radical, tipo):
        chamadas_detalhe.append(id_fnet)
        return _DETALHES[id_fnet]

    monkeypatch.setattr(b3fundos, "listar", _lista_fake)
    monkeypatch.setattr(b3fundos, "detalhar", _detalhar_fake)
    monkeypatch.setattr(b3fundos.time, "sleep", lambda s: None)

    mensagem = b3fundos.atualizar_etfs(con, hoje=date(2026, 7, 19))
    assert "4 no total" in mensagem
    linhas = {
        linha["ticker"]: linha
        for linha in con.execute("SELECT * FROM etfs").fetchall()
    }
    assert linhas["BOVA11"]["cnpj"] == "10406511000161"
    assert linhas["BOVA11"]["tipo_b3"] == "ETF"
    assert linhas["IMAB11"]["tipo_b3"] == "ETF-RF"
    assert linhas["HASH11"]["tipo_b3"] == "ETF-Cripto"
    assert linhas["BMMT11"]["radical"] == "BMMT"

    # mesma semana: não consulta a rede de novo
    chamadas_detalhe.clear()
    assert b3fundos.atualizar_etfs(con, hoje=date(2026, 7, 20)) is None
    assert chamadas_detalhe == []

    # semana seguinte: refresh, mas detalhe só de quem for NOVO
    assert b3fundos.atualizar_etfs(con, hoje=date(2026, 7, 27)) is not None
    assert chamadas_detalhe == []


def test_extrair_carteiras_e_verificador():
    import io
    import zipfile

    from scout.coleta import cda

    csv_cda = (
        "TP_FUNDO_CLASSE;CNPJ_FUNDO_CLASSE;DENOM_SOCIAL;DT_COMPTC;VL_PATRIM_LIQ;TP_APLIC;TP_ATIVO;VL_MERC_POS_FINAL\n"
        # BOVA-like: 90% ações, 10% RF
        "FIIM;10.406.511/0001-61;ISHARES;2026-05-31;1000000;Ações;Ação ordinária;900000\n"
        "FIIM;10.406.511/0001-61;ISHARES;2026-05-31;1000000;Títulos Públicos;;100000\n"
        # 'renda fixa' que virou 60% ações: divergente
        "FIIM;31.024.153/0001-00;IT NOW;2026-05-31;500000;Ações;Ação ordinária;300000\n"
        "FIIM;31.024.153/0001-00;IT NOW;2026-05-31;500000;Títulos Públicos;;200000\n"
        # valores a receber são ignorados no denominador
        "FIIM;10.406.511/0001-61;ISHARES;2026-05-31;1000000;Valores a receber;;50000\n"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("cda_fie_202605.csv", csv_cda.encode("latin-1"))
        zf.writestr("cda_fie_CONFID_202605.csv", b"")

    cnpjs = {"10406511000161", "31024153000100"}
    composicao, pls, competencia = cda.extrair_carteiras(buffer.getvalue(), cnpjs)
    assert competencia == "2026-05"
    assert composicao["10406511000161"]["Ações"] == 90.0
    assert composicao["31024153000100"]["Renda Fixa"] == 40.0
    assert pls["10406511000161"] == 1000000

    classificacoes = {
        "10406511000161": {"ticker": "BOVA11", "classificacao_scout": "Ações Brasil"},
        "31024153000100": {"ticker": "IMAB11", "classificacao_scout": "Renda Fixa"},
    }
    divergencias = cda.verificar(composicao, classificacoes)
    assert [d["ticker"] for d in divergencias] == ["IMAB11"]
    assert divergencias[0]["tipo"] == "divergência"
    assert "Renda Fixa em 40%" in divergencias[0]["motivo"]
    assert "Ações 60%" in divergencias[0]["carteira"]

    # fundo novo em captação (100% RF) e exposição via cotas: atenção, não erro
    especiais = cda.verificar(
        {
            "1": {"Renda Fixa": 100.0},
            "2": {"Cotas de Fundos": 100.0},
        },
        {
            "1": {"ticker": "NOVO11", "classificacao_scout": "Cripto"},
            "2": {"ticker": "FOFX11", "classificacao_scout": "Ações Internacionais"},
        },
    )
    assert {d["ticker"]: d["tipo"] for d in especiais} == {"NOVO11": "atenção", "FOFX11": "atenção"}
    assert "captação" in especiais[0]["motivo"] or "captação" in especiais[1]["motivo"]


def _semear_etf(con):
    from scout import armazenamento

    con.execute(
        "INSERT INTO etfs (cnpj, ticker, radical, id_fnet, tipo_b3, denominacao) "
        "VALUES ('10406511000161', 'BOVA11', 'BOVA', 1, 'ETF', 'ISHARES IBOVESPA FUNDO DE ÍNDICE')"
    )
    candles = [(f"2025-{m:02d}", 100.0 + m, 100.0 + m) for m in range(1, 13)]
    candles += [("2026-01", 169.12, 169.12)]
    armazenamento.gravar_cotacoes(con, "BOVA11", candles, 169.12, "2026-06-30", "2026-07-19T07:00:00")
    con.execute("INSERT INTO etf_carteira VALUES ('10406511000161', '2026-06', 'Ações', 93.0)")
    con.execute("INSERT INTO etf_carteira VALUES ('10406511000161', '2026-06', 'Renda Fixa', 7.0)")
    con.execute("INSERT INTO etf_pl VALUES ('10406511000161', '2026-06', 1500000000)")
    con.commit()


def test_pagina_etf_com_carteirinha_de_regras(con):
    from datetime import datetime

    from scout.relatorio import etf_html

    _semear_etf(con)
    classificacoes = {
        "10406511000161": {"classificacao_scout": "Ações Brasil", "observacoes": "", "gestor": "BLACKROCK"}
    }
    dados = etf_html.montar_dados_etf(con, "bova11", classificacoes)
    assert dados is not None
    assert dados["classe"] == "Ações Brasil"
    pagina = etf_html.gerar(dados, agora=datetime(2026, 7, 19, 7, 0))
    assert "BOVA11" in pagina
    # carteirinha de regras do tipo: a pegadinha da isenção está lá
    assert "SEM a isenção de R$ 20 mil/mês" in pagina
    assert "REINVESTIDOS dentro do fundo" in pagina
    # cards e composição
    assert "R$ 169,12" in pagina
    assert "R$ 1,5B" in pagina
    assert "93,00%" in pagina
    assert "fechamento oficial" in pagina
    # não é recomendação, nunca
    assert "não é recomendação" in pagina

    # ticker que não é ETF -> None
    assert etf_html.montar_dados_etf(con, "HGLG11", classificacoes) is None


def test_site_publica_etfs(con, tmp_path):
    from scout.relatorio import site

    from conftest import montar_zip_universo
    from scout.coleta import cvm

    cvm.carregar_zip(con, montar_zip_universo(), "inf_mensal_fii_2026.zip")
    _semear_etf(con)
    site.gerar(con, tmp_path / "site", com_cotacoes=False)
    assert (tmp_path / "site" / "BOVA11.html").exists()
    listagem = (tmp_path / "site" / "etfs.html").read_text(encoding="utf-8")
    assert 'href="BOVA11.html"' in listagem
    assert "function filtraClasse" in listagem
    indice = (tmp_path / "site" / "index.html").read_text(encoding="utf-8")
    assert 'href="etfs.html"' in indice


def test_cotahist_codbdi_14_entra_como_etf(con):
    from tests.test_cotacoes import _linha_cotahist, _zip_cotahist

    conteudo = _zip_cotahist(
        [
            _linha_cotahist("20260630", "TSTE11", 10000, codbdi="12"),
            _linha_cotahist("20260630", "BOVA11", 16912, codbdi="14"),
            _linha_cotahist("20260630", "PETR4", 3000, codbdi="02"),
        ]
    )
    from scout.coleta import b3

    pregoes = b3.extrair_pregoes(conteudo)
    assert set(pregoes) == {"TSTE11", "BOVA11"}
    assert pregoes["BOVA11"] == [("2026-06-30", 169.12)]
