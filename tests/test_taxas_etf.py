"""Taxa de administração de ETFs — curadoria (dados/taxas_etfs.csv)."""

from datetime import datetime

from scout.coleta import taxas_etf
from scout.relatorio import etf_html, site

from tests.test_etfs import _semear_etf


def _escrever_csv(tmp_path, conteudo: str):
    pasta = tmp_path / "dados"
    pasta.mkdir()
    (pasta / "taxas_etfs.csv").write_text(conteudo, encoding="utf-8-sig")
    return tmp_path


def test_carrega_ticker_maiusculo_virgula_e_ponto(tmp_path):
    raiz = _escrever_csv(
        tmp_path,
        "ticker;taxa_adm_aa;fonte;verificado_em;confianca\n"
        "bova11;0,10;https://x/reg.pdf;2026-07-20;alta\n"
        "IVVB11;0.23;;;media\n",
    )
    taxas = taxas_etf.carregar(raiz)
    assert taxas["BOVA11"]["taxa_adm_aa"] == 0.10
    assert taxas["BOVA11"]["fonte"] == "https://x/reg.pdf"
    assert taxas["BOVA11"]["verificado_em"] == "2026-07-20"
    assert taxas["BOVA11"]["confianca"] == "alta"
    assert taxas["IVVB11"]["taxa_adm_aa"] == 0.23


def test_descarta_vazio_e_absurdo(tmp_path):
    raiz = _escrever_csv(
        tmp_path,
        "ticker;taxa_adm_aa;fonte;verificado_em;confianca\n"
        "AAAA11;;fonte;;alta\n"       # sem valor -> fora
        "BBBB11;150;fonte;;alta\n"    # 150% a.a. é lixo -> fora
        ";0,30;fonte;;alta\n"          # sem ticker -> fora
        "CCCC11;0,30;fonte;;alta\n",  # válido
    )
    taxas = taxas_etf.carregar(raiz)
    assert set(taxas) == {"CCCC11"}


def test_porteiro_exige_confianca_preenchida(tmp_path):
    # regra do dono: taxa só vai pro site com confiança preenchida
    raiz = _escrever_csv(
        tmp_path,
        "ticker;taxa_adm_aa;fonte;verificado_em;confianca\n"
        "OKAY11;0,30;f;;alta\n"        # achado -> entra
        "MANU11;0,50;f;;manual\n"      # conferido à mão -> entra
        "WAIT11;;f;;nao_achou\n"       # sem taxa -> fora
        "HOLD11;0,30;f;;\n"             # tem taxa mas confiança vazia -> fora
        "NOPE11;0,30;f;;nao_achou\n",  # confiança 'nao_achou' -> fora
    )
    assert set(taxas_etf.carregar(raiz)) == {"OKAY11", "MANU11"}


def test_csv_ausente_nao_quebra(tmp_path):
    # sem CSV na raiz dada: cai no fallback do repo (ou vazio), mas NUNCA quebra
    assert isinstance(taxas_etf.carregar(tmp_path), dict)


def test_card_de_taxa_aparece_na_pagina_do_etf(con):
    _semear_etf(con)
    classificacoes = {
        "10406511000161": {"classificacao_scout": "Ações Brasil", "observacoes": "", "gestor": "BLACKROCK"}
    }
    dados = etf_html.montar_dados_etf(con, "BOVA11", classificacoes)
    # injeta a curadoria (independe do CSV do repo, que começa vazio)
    dados["taxa_adm"] = {
        "taxa_adm_aa": 0.10,
        "fonte": "https://fnet.example/reg.pdf",
        "verificado_em": "2026-07-20",
    }
    pagina = etf_html.gerar(dados, agora=datetime(2026, 7, 20, 11, 0))
    assert "Taxa de administração" in pagina
    assert "0,10% a.a." in pagina
    assert 'href="https://fnet.example/reg.pdf"' in pagina


def test_sem_taxa_nao_mostra_card(con):
    _semear_etf(con)
    dados = etf_html.montar_dados_etf(con, "BOVA11", {})
    assert dados["taxa_adm"] is None  # CSV do repo vazio
    pagina = etf_html.gerar(dados, agora=datetime(2026, 7, 20, 11, 0))
    assert "Taxa de administração" not in pagina


def test_extrai_taxa_do_regulamento_anual():
    texto = (
        "CAPÍTULO VII\nA taxa de administração é de 0,30% (trinta centésimos por cento) "
        "ao ano, calculada sobre o patrimônio líquido do Fundo."
    )
    r = taxas_etf.extrair_taxa_regulamento(texto)
    assert r["taxa_adm_aa"] == 0.30
    assert r["confianca"] == "alta"


def test_prefere_trecho_anual_e_pula_mensal():
    # aparece primeiro uma taxa "ao mês" (armadilha) e depois a anual de verdade
    texto = (
        "A provisão da taxa de administração de 0,025% ao mês é feita diariamente. "
        "A taxa de administração máxima é de 0,50% a.a."
    )
    r = taxas_etf.extrair_taxa_regulamento(texto)
    assert r["taxa_adm_aa"] == 0.50
    assert r["confianca"] == "alta"


def test_extrai_com_ponto_decimal_e_sem_ano():
    texto = "Taxa de Administração: 0.23% do patrimônio líquido."
    r = taxas_etf.extrair_taxa_regulamento(texto)
    assert r["taxa_adm_aa"] == 0.23
    assert r["confianca"] == "media"


def test_extrai_taxa_global_do_regime_175():
    # Res-175: a taxa vira "Taxa Global" (não "taxa de administração")
    r = taxas_etf.extrair_taxa_regulamento(
        "passe a viger conforme a redação: Taxa Global 0,39% (trinta e nove centésimos por cento) ao ano."
    )
    assert r["taxa_adm_aa"] == 0.39 and r["confianca"] == "alta"
    # duas taxas: pega a Taxa Global, não a do consultor de estruturação
    r2 = taxas_etf.extrair_taxa_regulamento(
        "os percentuais: (i) Taxa Global e Taxa Máxima Global: 0,12% (ii) Taxa destinada ao Consultor: 0,03%"
    )
    assert r2["taxa_adm_aa"] == 0.12


def test_documentos_de_regulamento_prioriza_alteracao():
    from scout.coleta import fnet

    docs = [
        {"id": 1, "tipo": "Regulamento", "categoria": "Regulamento", "data_entrega": ""},
        {"id": 2, "tipo": "Instrumento Particular de Alteração do Regulamento",
         "categoria": "Atos de Deliberação do Administrador", "data_entrega": ""},
        {"id": 3, "tipo": "Informe Diário", "categoria": "Informes Periódicos", "data_entrega": ""},
    ]
    ordenados = fnet.documentos_de_regulamento(docs)
    # alteração primeiro (é onde mora a Taxa Global), informe diário fora
    assert [d["id"] for d in ordenados] == [2, 1]


def test_acha_regulamento_entre_os_documentos():
    from scout.coleta import fnet

    docs = [
        {"id": 1, "tipo": "Relatório Gerencial", "categoria": "Relatório", "data_entrega": ""},
        {"id": 2, "tipo": "Regulamento", "categoria": "Documentos do Fundo", "data_entrega": ""},
    ]
    assert fnet.ultimo_regulamento(docs)["id"] == 2
    assert fnet.ultimo_regulamento(docs[:1]) is None


def test_nao_extrai_de_texto_sem_taxa_ou_absurdo():
    assert taxas_etf.extrair_taxa_regulamento("") is None
    assert taxas_etf.extrair_taxa_regulamento("Documento sem menção a tarifas.") is None
    # 20% não é taxa de administração de ETF (provavelmente taxa de performance)
    assert taxas_etf.extrair_taxa_regulamento("taxa de administração de 20% ao ano") is None


def test_atualizar_incremental_grava_achado_e_nao_achado(con, tmp_path, monkeypatch):
    import csv

    from scout import ia
    from scout.coleta import fnet

    # o passo pula em CI; o teste força o caminho local
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("CI", raising=False)

    con.execute("INSERT INTO etfs (cnpj, ticker, radical, tipo_b3) VALUES ('111','AAA11','AAA','ETF')")
    con.execute("INSERT INTO etfs (cnpj, ticker, radical, tipo_b3) VALUES ('222','BBB11','BBB','ETF')")
    con.commit()

    caminho = tmp_path / "dados" / "taxas_etfs.csv"
    caminho.parent.mkdir()
    caminho.write_text("ticker;taxa_adm_aa;fonte;verificado_em;confianca\n", encoding="utf-8-sig")
    monkeypatch.setattr(taxas_etf, "_caminho_gravavel", lambda: caminho)

    reg = {"id": 9, "tipo": "Regulamento", "categoria": "Documentos", "data_entrega": ""}
    monkeypatch.setattr(fnet, "listar", lambda cnpj, **k: [reg])
    monkeypatch.setattr(fnet, "_garantir_documento", lambda con, cnpj, doc, destino, **k: tmp_path / f"{cnpj}.pdf")
    textos = {
        "111.pdf": "A taxa de administração é de 0,30% (trinta centésimos por cento) ao ano.",
        "222.pdf": "Regulamento sem menção ao valor da taxa.",
    }
    monkeypatch.setattr(ia, "extrair_texto_pdf", lambda caminho, **k: textos.get(caminho.name, ""))

    mensagem = taxas_etf.atualizar(con)
    assert mensagem is not None and "1 achada" in mensagem

    linhas = {l["ticker"]: l for l in csv.DictReader(caminho.open(encoding="utf-8-sig"), delimiter=";")}
    assert linhas["AAA11"]["taxa_adm_aa"] == "0,30" and linhas["AAA11"]["confianca"] == "alta"
    assert linhas["BBB11"]["taxa_adm_aa"] == "" and linhas["BBB11"]["confianca"] == "nao_achou"

    # incremental: rodar de novo não relê nada (ambos já estão no arquivo)
    assert taxas_etf.atualizar(con) is None

    # porteiro: só o achado (com confiança) entra no site; o nao_achou fica fora
    carregadas = taxas_etf.carregar(tmp_path)
    assert set(carregadas) == {"AAA11"}
    assert carregadas["AAA11"]["taxa_adm_aa"] == 0.30


def test_atualizar_so_rele_quando_o_regulamento_muda(con, tmp_path, monkeypatch):
    import csv

    from scout import ia
    from scout.coleta import fnet

    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("CI", raising=False)
    con.execute("INSERT INTO etfs (cnpj, ticker, radical, tipo_b3) VALUES ('111','AAA11','AAA','ETF')")
    con.execute("INSERT INTO etfs (cnpj, ticker, radical, tipo_b3) VALUES ('222','BBB11','BBB','ETF')")
    con.commit()

    caminho = tmp_path / "dados" / "taxas_etfs.csv"
    caminho.parent.mkdir()
    # ambos lidos há muito tempo (vencidos pelo frescor); id do regulamento na fonte
    caminho.write_text(
        "ticker;taxa_adm_aa;fonte;verificado_em;confianca\n"
        "AAA11;0,30;https://f/downloadDocumento?id=100;2020-01-01;alta\n"
        "BBB11;0,40;https://f/downloadDocumento?id=200;2020-01-01;alta\n",
        encoding="utf-8-sig",
    )
    monkeypatch.setattr(taxas_etf, "_caminho_gravavel", lambda: caminho)
    regs = {
        "111": {"id": 101, "tipo": "Regulamento", "categoria": "Doc", "data_entrega": ""},  # NOVO
        "222": {"id": 200, "tipo": "Regulamento", "categoria": "Doc", "data_entrega": ""},  # MESMO
    }
    monkeypatch.setattr(fnet, "listar", lambda cnpj, **k: [regs[cnpj]])
    baixados = []

    def _baixar(con, cnpj, doc, destino, **k):
        baixados.append(cnpj)
        return tmp_path / f"{cnpj}.pdf"

    monkeypatch.setattr(fnet, "_garantir_documento", _baixar)
    monkeypatch.setattr(ia, "extrair_texto_pdf", lambda c, **k: "taxa de administração de 0,55% ao ano")

    taxas_etf.atualizar(con)
    linhas = {l["ticker"]: l for l in csv.DictReader(caminho.open(encoding="utf-8-sig"), delimiter=";")}
    # AAA11: regulamento mudou (id 100 -> 101) -> re-leu e atualizou a taxa
    assert linhas["AAA11"]["taxa_adm_aa"] == "0,55"
    assert linhas["AAA11"]["fonte"].endswith("id=101")
    assert linhas["AAA11"]["verificado_em"] != "2020-01-01"
    # BBB11: mesmo regulamento (id 200) -> NÃO re-baixou, manteve a taxa, só renovou a data
    assert linhas["BBB11"]["taxa_adm_aa"] == "0,40"
    assert linhas["BBB11"]["verificado_em"] != "2020-01-01"
    assert baixados == ["111"]  # só o que mudou foi baixado


def test_manual_vale_so_ate_o_regulamento_mudar(con, tmp_path, monkeypatch):
    import csv

    from scout import ia
    from scout.coleta import fnet

    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("CI", raising=False)
    con.execute("INSERT INTO etfs (cnpj, ticker, radical, tipo_b3) VALUES ('111','MMM11','MMM','ETF')")
    con.execute("INSERT INTO etfs (cnpj, ticker, radical, tipo_b3) VALUES ('222','NNN11','NNN','ETF')")
    con.commit()

    caminho = tmp_path / "dados" / "taxas_etfs.csv"
    caminho.parent.mkdir()
    caminho.write_text(
        "ticker;taxa_adm_aa;fonte;verificado_em;confianca\n"
        "MMM11;0,10;https://f/downloadDocumento?id=100;2020-01-01;manual\n"  # doc NÃO muda
        "NNN11;0,20;https://f/downloadDocumento?id=200;2020-01-01;manual\n",  # doc MUDA
        encoding="utf-8-sig",
    )
    monkeypatch.setattr(taxas_etf, "_caminho_gravavel", lambda: caminho)
    regs = {
        "111": {"id": 100, "tipo": "Regulamento", "categoria": "Doc", "data_entrega": ""},  # MESMO
        "222": {"id": 201, "tipo": "Regulamento", "categoria": "Doc", "data_entrega": ""},  # NOVO
    }
    monkeypatch.setattr(fnet, "listar", lambda cnpj, **k: [regs[cnpj]])
    baixados = []

    def _baixar(con, cnpj, doc, destino, **k):
        baixados.append(cnpj)
        return tmp_path / f"{cnpj}.pdf"

    monkeypatch.setattr(fnet, "_garantir_documento", _baixar)
    monkeypatch.setattr(ia, "extrair_texto_pdf", lambda c, **k: "taxa de administração de 0,55% ao ano")

    taxas_etf.atualizar(con)
    linhas = {l["ticker"]: l for l in csv.DictReader(caminho.open(encoding="utf-8-sig"), delimiter=";")}
    # MMM11: mesmo regulamento -> manual preservado, nem baixou o PDF
    assert linhas["MMM11"]["taxa_adm_aa"] == "0,10" and linhas["MMM11"]["confianca"] == "manual"
    # NNN11: regulamento mudou (200 -> 201) -> ATÉ a manual foi reavaliada
    assert linhas["NNN11"]["taxa_adm_aa"] == "0,55"
    assert baixados == ["222"]  # só o que mudou baixou


def test_indice_etfs_tem_coluna_taxa(con):
    _semear_etf(con)
    dados = etf_html.montar_dados_etf(con, "BOVA11", {"10406511000161": {"classificacao_scout": "Ações Brasil"}})
    dados["taxa_adm"] = {"taxa_adm_aa": 0.10, "fonte": "", "verificado_em": ""}
    html = site._indice_etfs([dados], datetime(2026, 7, 20, 11, 0))
    assert "<th>taxa</th>" in html
    assert "0,10% a.a." in html
