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


def test_posicoes_do_etf_com_cross_link(con, zip_cvm):
    from datetime import datetime

    from scout.coleta import cvm
    from scout.relatorio import etf_html

    cvm.carregar_zip(con, zip_cvm(True), "inf_mensal_fii_2026.zip")  # TSTE11 (FII) na base
    _semear_etf(con)
    con.executemany(
        "INSERT INTO etf_posicoes (cnpj, competencia, item, codigo, nome, cnpj_emissor, pct) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            ("10406511000161", "2026-06", 0, "PETR4", "PETROBRAS PN", "", 8.5),
            ("10406511000161", "2026-06", 1, "", "FUNDO TESTE FII", "11111111000111", 4.2),
        ],
    )
    con.commit()
    classificacoes = {"10406511000161": {"classificacao_scout": "Ações Brasil", "observacoes": ""}}
    dados = etf_html.montar_dados_etf(con, "BOVA11", classificacoes)
    posicoes = dados["posicoes"]
    assert posicoes[0]["codigo"] == "PETR4" and posicoes[0]["classe_alvo"] == "Ação"
    # a posição em FII foi resolvida pelo CNPJ do emissor -> ticker + classe
    assert posicoes[1]["ticker_alvo"] == "TSTE11" and posicoes[1]["classe_alvo"] == "FII"

    pagina = etf_html.gerar(
        dados, agora=datetime(2026, 7, 20, 0, 0), publicados={"TSTE11", "BOVA11"}
    )
    assert "Principais posições" in pagina
    assert 'href="TSTE11.html"' in pagina  # o cross-link do usuário
    assert "PETR4" in pagina

    # com o mapa de selos, a coluna "alerta" mostra o selo da página do alvo
    from scout import redflags

    selo_ok = redflags.selo(redflags.Resultado(aprovadas=["regra"] * 5))
    pagina = etf_html.gerar(
        dados,
        agora=datetime(2026, 7, 20, 0, 0),
        publicados={"TSTE11", "PETR4"},
        selos={"TSTE11": selo_ok, "PETR4": selo_ok},
    )
    assert "<th>alerta</th>" in pagina
    assert 'href="PETR4.html"' in pagina  # ação publicada também vira link
    assert pagina.count("ponto-posicao") >= 2  # selo nas duas posições cobertas
    assert "ainda não cobrimos" in pagina  # nota explica o "—"


def test_extrair_carteira_completa_com_quantidade():
    import io
    import zipfile

    from scout.coleta import cda

    cab = ("TP_FUNDO_CLASSE;CNPJ_FUNDO_CLASSE;DENOM_SOCIAL;DT_COMPTC;VL_PATRIM_LIQ;"
           "TP_APLIC;TP_ATIVO;VL_MERC_POS_FINAL;CD_ATIVO;QT_POS_FINAL\n")
    # 12 ações -> a carteira completa deve trazer TODAS (não só o top 10)
    linhas = "".join(
        f"FIIM;10.406.511/0001-61;ISHARES;2026-06-30;120000;Ações;Ação;{12000 - i * 100};ACAO{i:02d};{1000 + i}\n"
        for i in range(12)
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("cda_fie_202606.csv", (cab + linhas).encode("latin-1"))

    _comp, _pls, competencia, posicoes = cda.extrair_carteiras(buffer.getvalue(), {"10406511000161"})
    carteira = posicoes["10406511000161"]
    assert competencia == "2026-06"
    assert len(carteira) == 12  # TODAS, sem o corte antigo de 10
    assert carteira[0]["codigo"] == "ACAO00"  # maior valor primeiro
    assert carteira[0]["quantidade"] == 1000.0  # QT_POS_FINAL capturado
    assert all("pct" in p for p in carteira)


def test_pagina_etf_mostra_carteira_completa_e_nota_datada(con):
    from datetime import datetime

    from scout.relatorio import etf_html

    _semear_etf(con)
    con.executemany(
        "INSERT INTO etf_posicoes (cnpj, competencia, item, codigo, nome, cnpj_emissor, pct, quantidade) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            ("10406511000161", "2026-06", i, f"ACAO{i:02d}", f"EMPRESA {i}", "", 20.0 - i, 1000 + i)
            for i in range(12)
        ],
    )
    con.commit()
    dados = etf_html.montar_dados_etf(con, "BOVA11", {"10406511000161": {"classificacao_scout": "Ações Brasil"}})
    assert len(dados["posicoes"]) == 12
    pagina = etf_html.gerar(dados, agora=datetime(2026, 7, 20, 11, 0))
    # o expansível traz só os que faltam (11º em diante), sem repetir o top 10
    assert "Ver os outros 2 ativos (12 no total)" in pagina
    assert pagina.count("ACAO00") == 1  # 1ª posição só aparece no top, não é repetida
    assert "ACAO11" in pagina  # os ativos restantes aparecem no expansível
    assert "posição informada à CVM" in pagina and "pode estar diferente" in pagina  # nota datada
    assert "06/2026" in pagina  # a competência da carteira


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
    composicao, pls, competencia, top_posicoes = cda.extrair_carteiras(buffer.getvalue(), cnpjs)
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


def test_flags_de_etf_pl_liquidez_e_selo():
    from scout import etf_flags, redflags

    # ETF saudável: tudo aprovado
    saudavel = {
        "pl": {"pl": 500_000_000, "competencia": "2026-06"},
        "liquidez": 5_000_000.0,
        "cotacao": [("x", 1.0)] * 24,
        "carteira": [{"grupo": "Ações", "pct": 95.0}],
        "divergencia_classe": None,
        "situacao_cvm": "Em Funcionamento Normal",
    }
    resultado = etf_flags.avaliar(saudavel)
    assert resultado.flags == []
    assert len(resultado.aprovadas) == 6
    assert redflags.selo(resultado).nivel == "sem_alertas"

    # PL inviável + sem liquidez + novo + carteira fechada
    problema = {
        "pl": {"pl": 10_000_000, "competencia": "2026-06"},
        "liquidez": 20_000.0,
        "cotacao": [("x", 1.0)] * 5,
        "carteira": [],
        "divergencia_classe": None,
    }
    resultado = etf_flags.avaliar(problema)
    codigos = {flag.codigo for flag in resultado.flags}
    assert codigos == {"etf_pl_inviavel", "etf_liquidez", "etf_novo", "etf_carteira_fechada"}
    assert redflags.selo(resultado).nivel == "grave"

    # dados ausentes viram "não avaliada", nunca aprovação silenciosa
    # (inclui a situação cadastral dos ETFs fora do registro FII/FIIM)
    vazio = {"pl": None, "liquidez": None, "cotacao": [], "carteira": []}
    resultado = etf_flags.avaliar(vazio)
    assert len(resultado.nao_avaliadas) == 4

    # divergência de classe (do verificador CDA) vira flag leve
    divergente = dict(saudavel, divergencia_classe="Ações em 40% (esperado ≥ 70%)")
    resultado = etf_flags.avaliar(divergente)
    assert [flag.codigo for flag in resultado.flags] == ["etf_classe_divergente"]


def test_verificador_pega_classe_contra_segmento_b3():
    from scout.coleta import cda

    # caso AUPO11 real: segmento oficial ETF-RF com classe Scout de ações
    apontamentos = cda.verificar(
        {},
        {
            "1": {"ticker": "AUPO11", "classificacao_scout": "Ações Brasil", "segmento_b3": "ETF-RF"},
            "2": {"ticker": "IMAB11", "classificacao_scout": "Renda Fixa", "segmento_b3": "ETF-RF"},
            "3": {"ticker": "HASH11", "classificacao_scout": "Cripto", "segmento_b3": "ETF-Cripto"},
        },
    )
    assert [a["ticker"] for a in apontamentos] == ["AUPO11"]
    assert apontamentos[0]["tipo"] == "divergência"
    assert "incompatível" in apontamentos[0]["motivo"]


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
    # glossário: todo card tem o "?" com explicação para leigos
    assert 'class="ajuda"' in pagina
    assert "tamanho real do fundo" in pagina  # verbete do Patrimônio líquido
    # selo + red flags de ETF na página (PL 1,5B ok; liquidez sem dado = não avaliada)
    assert dados["selo"] is not None
    assert "Red flags" in pagina
    assert "não avaliada: liquidez" in pagina
    assert "piso de viabilidade" in pagina  # aprovada do PL

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
    pagina_etf = (tmp_path / "site" / "BOVA11.html").read_text(encoding="utf-8")
    # no site, a página de ETF tem menu E a busca VIVA do topo (mesma da home)
    assert "FIIs ▾" in pagina_etf
    assert 'id="ir-ticker"' in pagina_etf
    assert "buscaTopo" in pagina_etf and "busca.json" in pagina_etf
    # o índice compartilhado da busca existe e cobre as duas classes
    import json

    ativos = json.loads((tmp_path / "site" / "busca.json").read_text(encoding="utf-8"))
    tickers = {a["t"] for a in ativos}
    assert "BOVA11" in tickers and "ALFA11" in tickers
    listagem = (tmp_path / "site" / "etfs.html").read_text(encoding="utf-8")
    assert 'href="BOVA11.html"' in listagem
    assert "function filtraClasse" in listagem
    indice = (tmp_path / "site" / "index.html").read_text(encoding="utf-8")
    assert 'href="etfs.html"' in indice


def test_cotacao_rf_upsert_diario_idempotente(con, monkeypatch):
    from datetime import date

    from scout.coleta import b3rf

    con.execute(
        "INSERT INTO etfs (cnpj, ticker, radical, id_fnet, tipo_b3, denominacao) "
        "VALUES ('31024153000100', 'IMAB11', 'IMAB', 5678, 'ETF-RF', 'IT NOW IMA-B')"
    )
    con.commit()
    respostas = {"dia": "2026-07-17", "preco": 113.82, "volume": 102000.0}
    monkeypatch.setattr(
        b3rf, "buscar", lambda ticker: (respostas["dia"], respostas["preco"], respostas["volume"])
    )
    monkeypatch.setattr(b3rf.time, "sleep", lambda s: None)

    assert b3rf.atualizar_diaria(con, hoje=date(2026, 7, 17)) is not None
    linha = con.execute(
        "SELECT * FROM cotacoes_b3 WHERE ticker='IMAB11' AND competencia='2026-07'"
    ).fetchone()
    assert (linha["fechamento"], linha["volume"], linha["pregoes"]) == (113.82, 102000.0, 1)
    # série derivada e preço atual aparecem para a página
    from scout import armazenamento

    meta = armazenamento.cotacao_meta(con, "IMAB11")
    assert meta["preco_atual"] == 113.82

    # mesmo dia de novo (rodada repetida): freshness segura, nada muda
    assert b3rf.atualizar_diaria(con, hoje=date(2026, 7, 17)) is None

    # dia seguinte: acumula volume e pregões, fechamento vira o novo
    respostas.update({"dia": "2026-07-18", "preco": 114.10, "volume": 98000.0})
    assert b3rf.atualizar_diaria(con, hoje=date(2026, 7, 18)) is not None
    linha = con.execute(
        "SELECT * FROM cotacoes_b3 WHERE ticker='IMAB11' AND competencia='2026-07'"
    ).fetchone()
    assert (linha["fechamento"], linha["volume"], linha["pregoes"]) == (114.10, 200000.0, 2)

    # fim de semana: a fonte repete o pregão de sexta -> upsert ignora
    assert b3rf.atualizar_diaria(con, hoje=date(2026, 7, 19)) is not None
    linha = con.execute(
        "SELECT * FROM cotacoes_b3 WHERE ticker='IMAB11' AND competencia='2026-07'"
    ).fetchone()
    assert linha["pregoes"] == 2


_XML_PROVENTO = b"""<?xml version="1.0" encoding="UTF-8"?>
<DadosEconomicoFinanceiros>
  <InformeRendimentos>
    <Provento>
      <CodNegociacao>NDIV11</CodNegociacao>
      <Rendimento>
        <DataBase>2026-07-07</DataBase>
        <ValorProvento>0.3895801</ValorProvento>
        <DataPagamento>2026-07-14</DataPagamento>
        <RendimentoIsentoIR>N\xc3\xa3o</RendimentoIsentoIR>
      </Rendimento>
    </Provento>
  </InformeRendimentos>
</DadosEconomicoFinanceiros>"""


def test_proventos_de_etf_extrai_e_grava(con, monkeypatch):
    from datetime import date

    from scout.coleta import etf_renda

    proventos = etf_renda.extrair_proventos(_XML_PROVENTO)
    assert proventos == [
        {
            "ticker": "NDIV11",
            "data_base": "2026-07-07",
            "valor": 0.3895801,
            "data_pagamento": "2026-07-14",
            "isento": False,
        }
    ]

    con.execute(
        "INSERT INTO etfs (cnpj, ticker, radical, id_fnet, tipo_b3, denominacao) "
        "VALUES ('52116337000162', 'NDIV11', 'NDIV', 10677, 'ETF', 'NU RENDA IBOV SMART DIVIDENDOS')"
    )
    con.commit()
    docs = [
        {"id": 1240950, "tipo": "Proventos em dinheiro", "categoria": "Aviso aos Cotistas - Estruturado", "data_entrega": "07/07/2026 12:42"},
        {"id": 999, "tipo": "Informe Diário", "categoria": "Informes Periódicos", "data_entrega": "17/07/2026 10:00"},
    ]
    monkeypatch.setattr(
        etf_renda.fnet, "listar", lambda cnpj, quantidade=40, timeout=60, tentativas=3: docs
    )
    monkeypatch.setattr(etf_renda.fnet, "baixar", lambda id_doc, timeout=180, tentativas=3: _XML_PROVENTO)

    mensagem = etf_renda.atualizar_proventos(con, hoje=date(2026, 7, 19))
    assert "1 avisos novos" in mensagem and "1 ETFs distribuem" in mensagem
    from scout import armazenamento

    ultimos = armazenamento.proventos_do_etf(con, "52116337000162")
    assert ultimos[0]["valor"] == 0.3895801
    assert ultimos[0]["isento"] == 0

    # mesmo dia: não vai à rede de novo (1x/dia)
    assert etf_renda.atualizar_proventos(con, hoje=date(2026, 7, 19)) is None
    # dia seguinte: roda de novo, mas só baixa o que ainda não tem (incremental)
    assert etf_renda.atualizar_proventos(con, hoje=date(2026, 7, 20)) is not None


def test_proventos_repete_busca_do_fnet_que_oscilou(con, monkeypatch):
    """O FNET pendura de forma intermitente; a busca que falha na 1ª volta na
    2ª passada — sem isso, distribuidores somem por azar de timing."""
    from scout.coleta import etf_renda

    con.execute(
        "INSERT INTO etfs (cnpj, ticker, radical, id_fnet, tipo_b3) "
        "VALUES ('52116337000162', 'NDIV11', 'NDIV', 10677, 'ETF')"
    )
    con.commit()
    docs = [{"id": 1240950, "tipo": "Proventos em dinheiro", "categoria": "", "data_entrega": ""}]
    chamadas = {"n": 0}

    def _listar(cnpj, quantidade=40, timeout=60, tentativas=3):
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            raise TimeoutError("FNET oscilou")  # 1ª chamada pendura
        return docs

    monkeypatch.setattr(etf_renda.fnet, "listar", _listar)
    monkeypatch.setattr(etf_renda.fnet, "baixar", lambda id_doc, timeout=180, tentativas=3: _XML_PROVENTO)

    mensagem = etf_renda.atualizar_proventos(con, hoje=date(2026, 7, 19))
    assert chamadas["n"] == 2  # 1ª falhou -> 2ª passada recuperou
    assert "1 avisos novos" in mensagem


def test_pagina_etf_distribuidor_mostra_renda(con):
    from datetime import datetime

    from scout.relatorio import etf_html

    _semear_etf(con)
    con.execute(
        "INSERT INTO etf_proventos (cnpj, id_doc, ticker, data_base, valor, data_pagamento, isento) "
        "VALUES ('10406511000161', 1, 'BOVA11', '2026-07-07', 0.39, '2026-07-14', 0)"
    )
    con.commit()
    classificacoes = {"10406511000161": {"classificacao_scout": "Ações Brasil", "observacoes": ""}}
    dados = etf_html.montar_dados_etf(con, "BOVA11", classificacoes)
    pagina = etf_html.gerar(dados, agora=datetime(2026, 7, 19, 11, 0))
    assert "Distribui renda" in pagina
    assert "R$ 0,39/cota" in pagina
    assert "geração DISTRIBUIDORA" in pagina
    assert "não é isento de IR" in pagina


def test_lote_ia_inclui_etfs_pelo_fluxo_sem_relatorio(con, zip_cvm, tmp_path, monkeypatch):
    import json as _json

    from typer.testing import CliRunner

    from scout import cli as modulo_cli
    from scout import ia as modulo_ia
    from scout.cli import app
    from scout.coleta import cvm
    from scout.coleta import fnet as modulo_fnet
    from tests.test_fnet_ia import _pdf_minimo

    cvm.carregar_zip(con, zip_cvm(True), "inf_mensal_fii_2026.zip")
    _semear_etf(con)  # BOVA11 na tabela etfs
    monkeypatch.setenv("SCOUT_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(modulo_cli, "_preparar_ia", lambda modelo: "teste:1b")

    docs_por_cnpj = {
        # FII TSTE11: sem nada (sai rápido)
        "11.111.111/0001-11": [],
        # ETF BOVA11: uma assembleia recente para a IA ler
        "10406511000161": [
            {"id": 777, "tipo": "AGE", "categoria": "Assembleia", "data_entrega": "10/07/2026 10:00"},
        ],
    }
    monkeypatch.setattr(
        modulo_fnet,
        "listar",
        lambda cnpj, quantidade=30, timeout=60, tentativas=3: docs_por_cnpj.get(cnpj, []),
    )
    caminho_pdf = tmp_path / "doc.pdf"
    caminho_pdf.write_bytes(_pdf_minimo("Ata de assembleia do ETF " * 30))
    monkeypatch.setattr(
        modulo_fnet,
        "_garantir_documento",
        lambda con_, cnpj, doc, destino, timeout=180, tentativas=3: caminho_pdf,
    )
    monkeypatch.setattr(
        modulo_ia,
        "analisar_comunicados",
        lambda itens, ctx, modelo=None, ao_progresso=None: "assembleia lida",
    )
    pasta = tmp_path / "leituras"
    resultado = CliRunner().invoke(app, ["ia-lote", "--destino", str(pasta)])
    assert resultado.exit_code == 0, resultado.output
    leitura = _json.loads((pasta / "BOVA11.json").read_text(encoding="utf-8"))
    assert leitura["sem_relatorio"] is True
    assert leitura["comunicados"]["texto"] == "assembleia lida"
    assert leitura["comunicados"]["rotulos"] == ["Assembleia AGE"]


def test_cotahist_codbdi_14_entra_como_etf(con):
    from tests.test_cotacoes import _linha_cotahist, _zip_cotahist

    conteudo = _zip_cotahist(
        [
            _linha_cotahist("20260630", "TSTE11", 10000, codbdi="12"),
            _linha_cotahist("20260630", "BOVA11", 16912, codbdi="14"),
            _linha_cotahist("20260630", "PETR4", 3000, codbdi="02"),
            _linha_cotahist("20260630", "PETR1", 100, codbdi="02"),  # direito: fora
            _linha_cotahist("20260630", "XYZW3", 500, codbdi="96"),  # fracionário: fora
        ]
    )
    from scout.coleta import b3

    pregoes = b3.extrair_pregoes(conteudo)
    # desde a fase de Ações, o codbdi 02 (PETR4) também entra
    assert set(pregoes) == {"TSTE11", "BOVA11", "PETR4"}
    assert pregoes["BOVA11"] == [("2026-06-30", 169.12, 0.0)]


# --- deslistagem e situação cadastral (aprovado em 20/07/2026) ------------------


def test_etf_que_some_da_listagem_vira_deslistado(con, monkeypatch):
    from scout import armazenamento

    monkeypatch.setattr(b3fundos, "listar", _lista_fake)
    monkeypatch.setattr(b3fundos, "detalhar", lambda i, r, t: _DETALHES[i])
    monkeypatch.setattr(b3fundos.time, "sleep", lambda s: None)
    b3fundos.atualizar_etfs(con, hoje=date(2026, 7, 19))
    # linha de curadoria manual (sem id_fnet, tipo XFIX11): nunca é mexida
    con.execute(
        "INSERT INTO etfs (cnpj, ticker, radical, id_fnet, tipo_b3) "
        "VALUES ('99999999000199', 'XFIX11', 'XFIX', NULL, 'ETF')"
    )
    con.commit()
    assert len(armazenamento.etfs_listados(con)) == 5

    # semana seguinte: HASH sumiu da listagem da B3 (deslistado)
    def _lista_sem_hash(tipo):
        return [] if tipo == "ETF-Cripto" else _lista_fake(tipo)

    monkeypatch.setattr(b3fundos, "listar", _lista_sem_hash)
    mensagem = b3fundos.atualizar_etfs(con, hoje=date(2026, 7, 27))
    assert "1 saíram da listagem" in mensagem
    tickers = {etf["ticker"] for etf in armazenamento.etfs_listados(con)}
    assert "HASH11" not in tickers  # fora do site e do lote
    assert "XFIX11" in tickers      # curadoria manual intocada
    linha = con.execute("SELECT listado FROM etfs WHERE ticker = 'HASH11'").fetchone()
    assert linha[0] == 0

    # se voltar à listagem, volta ao site
    monkeypatch.setattr(b3fundos, "listar", _lista_fake)
    b3fundos.atualizar_etfs(con, hoje=date(2026, 8, 3))
    assert con.execute("SELECT listado FROM etfs WHERE ticker = 'HASH11'").fetchone()[0] == 1


def test_listagem_vazia_nao_deslista_ninguem(con, monkeypatch):
    from scout import armazenamento

    monkeypatch.setattr(b3fundos, "listar", _lista_fake)
    monkeypatch.setattr(b3fundos, "detalhar", lambda i, r, t: _DETALHES[i])
    monkeypatch.setattr(b3fundos.time, "sleep", lambda s: None)
    b3fundos.atualizar_etfs(con, hoje=date(2026, 7, 19))

    monkeypatch.setattr(b3fundos, "listar", lambda tipo: [])  # fonte fora do ar
    b3fundos.atualizar_etfs(con, hoje=date(2026, 7, 27))
    assert len(armazenamento.etfs_listados(con)) == 4  # ninguém deslistado


def test_listagem_parcial_degradada_nao_deslista(con, monkeypatch):
    """Resposta parcial da B3 (< 80% do que temos) não deslista — foi o que
    zerou os ETFs do site publicado (proxy da B3 degradado no GitHub Actions)."""
    from scout import armazenamento

    monkeypatch.setattr(b3fundos, "listar", _lista_fake)
    monkeypatch.setattr(b3fundos, "detalhar", lambda i, r, t: _DETALHES[i])
    monkeypatch.setattr(b3fundos.time, "sleep", lambda s: None)
    b3fundos.atualizar_etfs(con, hoje=date(2026, 7, 19))  # 4 ETFs

    # a B3 devolve só 1 de 4 (degradada) -> segurança: não deslista ninguém
    def _so_um(tipo):
        return (
            [{"id": 1234, "acronym": "BOVA", "fundName": "ISHARES", "tradingName": "BOVA"}]
            if tipo == "ETF"
            else []
        )

    monkeypatch.setattr(b3fundos, "listar", _so_um)
    b3fundos.atualizar_etfs(con, hoje=date(2026, 7, 27))
    assert len(armazenamento.etfs_listados(con)) == 4  # nada deslistado


def test_etf_em_liquidacao_ganha_flag_alta_na_pagina(con):
    from scout.relatorio import etf_html

    _semear_etf(con)
    con.execute(
        "INSERT INTO cadastro (cnpj, denominacao, situacao) "
        "VALUES ('10406511000161', 'ISHARES IBOVESPA', 'Em Liquidação')"
    )
    con.commit()
    classificacoes = {"10406511000161": {"classificacao_scout": "Ações Brasil", "observacoes": ""}}
    dados = etf_html.montar_dados_etf(con, "BOVA11", classificacoes)
    codigos = {flag.codigo for flag in dados["flags"].flags}
    assert "etf_situacao_cvm" in codigos
    assert dados["selo"].nivel == "grave"


def test_comparador_de_etfs(con):
    from datetime import datetime  # noqa: F401 (paridade com os demais testes)

    from scout.relatorio import etf_html
    from scout.relatorio import site as modulo_site

    _semear_etf(con)
    dados = etf_html.montar_dados_etf(
        con, "BOVA11", {"10406511000161": {"classificacao_scout": "Ações Brasil"}}
    )
    pagina = modulo_site._pagina_comparar_etfs([dados])
    assert "Comparar ETFs" in pagina
    assert '<option value="BOVA11">' in pagina
    assert '"classe": "Ações Brasil"' in pagina
    # aviso factual quando as classes diferem + sem veredito
    assert "classes diferentes" in pagina
    assert "não é recomendação" in pagina
    assert 'sem "vencedor"' in pagina  # a única menção é a própria negação
    for veredito in ("melhor etf", "vencedor:"):
        assert veredito not in pagina.lower()
    for placeholder in ("{CSS_", "{JS_", "{relatorio_html.", "{menu_html"):
        assert placeholder not in pagina
