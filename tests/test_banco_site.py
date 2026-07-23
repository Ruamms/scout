"""R3/R4 Renda Fixa — página do banco emissor + listagem + calculadoras."""

from datetime import datetime

from scout.relatorio import banco_html, site as modulo_site


def _semear_banco(con, cod="C001", nome="BANCO TESTE - PRUDENCIAL", basileia=15.0):
    con.execute(
        "INSERT INTO bancos (cod_inst, nome, tcb, segmento, uf, atualizado_em)"
        " VALUES (?, ?, 'b1', 'S3', 'SP', '2026-07-23')", (cod, nome),
    )
    con.executemany(
        "INSERT INTO bancos_tri (cod_inst, anomes, ativo, carteira, captacoes, pl, lucro,"
        " capital_principal, pr, rwa, basileia) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (cod, 202412, 10e9, 6e9, 7e9, 1.5e9, 200e6, 1.2e9, 1.5e9, 10e9, basileia),
            (cod, 202503, 11e9, 6.5e9, 7.5e9, 1.6e9, 60e6, 1.3e9, 1.6e9, 10.5e9, basileia),
        ],
    )
    con.commit()


def test_pagina_do_banco_no_design(con):
    _semear_banco(con)
    dados = banco_html.montar_dados_banco(con, "C001")
    assert dados is not None and dados["selo"].rotulo  # selo de 5 níveis calculado
    pagina = banco_html.gerar(dados, agora=datetime(2026, 7, 23, 12, 0))
    assert "BANCO TESTE" in pagina and "PRUDENCIAL" not in pagina.split("<h1")[1][:80]
    assert "Índice de Basileia" in pagina and "15,00%" in pagina
    assert "🚩 Red flags" in pagina
    # carteirinha da classe: FGC por conglomerado + teto global + FGCoop
    assert "R$ 250 mil" in pagina and "conglomerado" in pagina and "FGCoop" in pagina
    # calculadoras opt-in (padrão Gordon): gross-up + cobertura FGC
    assert "CDB × LCI/LCA" in pagina and "Cobertura do FGC" in pagina
    assert pagina.count("não é recomendação") >= 2
    for veredito in ("compre", "comprar", "vale a pena", "seguro para investir"):
        assert veredito not in pagina.lower()


def test_banco_com_flag_mostra_selo_grave(con):
    _semear_banco(con, basileia=10.2)  # abaixo do requerimento com adicionais
    dados = banco_html.montar_dados_banco(con, "C001")
    assert dados["selo"].nivel == "grave"
    pagina = banco_html.gerar(dados, agora=datetime(2026, 7, 23, 12, 0))
    assert "abaixo do requerimento" in pagina


def test_sem_serie_nao_gera_pagina(con):
    con.execute("INSERT INTO bancos (cod_inst, nome, tcb) VALUES ('C009', 'SEM SERIE', 'b1')")
    con.commit()
    assert banco_html.montar_dados_banco(con, "C009") is None


def test_busca_viva_inclui_bancos(con):
    _semear_banco(con)
    dados = banco_html.montar_dados_banco(con, "C001")
    ativos = modulo_site._ativos_busca([], [], [], [dados])
    # sem ticker: a URL vem explícita em `u` e o nome curto é o que se busca
    assert ativos == [
        {
            "t": "",
            "n": "BANCO TESTE",
            "c": "Banco",
            "s": dados["selo"].nivel,
            "r": dados["selo"].rotulo,
            "u": "banco-C001.html",
        }
    ]


def test_home_busca_cobre_bancos(con):
    _semear_banco(con)
    dados = banco_html.montar_dados_banco(con, "C001")
    home = modulo_site._home([], [], datetime(2026, 7, 23, 12, 0), {}, [], [dados])
    assert "1 bancos" in home  # cobertura declarada embaixo da caixa de busca
    assert '"u": "banco-C001.html"' in home or '"u":"banco-C001.html"' in home
    assert "a.u || (a.t + '.html')" in home  # link usa a URL explícita
    assert "Bancos (CDB)" in home  # card continua com a contagem derivada da lista


def test_comparador_de_bancos(con):
    _semear_banco(con)
    dados = banco_html.montar_dados_banco(con, "C001")
    pagina = modulo_site._pagina_comparar_bancos([dados])
    assert "Comparar bancos" in pagina
    assert '<option value="C001">BANCO TESTE</option>' in pagina
    assert '"basileia": "15,00%"' in pagina
    # aviso factual de portes + lembrete do FGC; nunca veredito
    assert "portes regulatórios diferentes" in pagina and "R$ 250 mil" in pagina
    assert "não é recomendação" in pagina
    assert 'sem "vencedor"' in pagina  # a única menção é a própria negação
    for veredito in ("melhor banco", "mais seguro", "vencedor:"):
        assert veredito not in pagina.lower()
    for placeholder in ("{CSS_", "{JS_", "{relatorio_html.", "{menu_html"):
        assert placeholder not in pagina


def test_indice_bancos_lista_e_rankings(con):
    _semear_banco(con)
    dados = banco_html.montar_dados_banco(con, "C001")
    pagina = modulo_site._indice_bancos([dados], datetime(2026, 7, 23, 12, 0))
    assert "1 conglomerados com dados no IF.data" in pagina
    assert 'href="banco-C001.html"' in pagina
    assert "o risco é o banco emissor" in pagina
    assert "Maiores captações" in pagina and "Menor Basileia" in pagina
    assert "não recomendação" in pagina
