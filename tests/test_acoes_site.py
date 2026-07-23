"""A4/A6 — página da empresa (ações) e listagem no site."""

from datetime import date, datetime

from scout.relatorio import acao_html, site as modulo_site


def _semear_empresa(con):
    con.execute(
        "INSERT INTO empresas (cod_cvm, cnpj, radical, nome, nome_pregao, setor_b3, setor_cvm,"
        " situacao, auditor, segmento_listagem, no_ibrx100, acoes_on, acoes_pn, acoes_total)"
        " VALUES ('9999','11222333000144','TSTA','TESTE S.A.','TESTECO',"
        " 'Energia / Elétricas / Geração','Energia','ATIVO','AUDITORA XYZ','Novo Mercado',1,"
        " 500000000,500000000,1000000000)"
    )
    con.executemany(
        "INSERT INTO papeis (ticker, cod_cvm, isin, tipo) VALUES (?, '9999', ?, ?)",
        [("TSTA3", "BRTSTAACNOR1", "ON"), ("TSTA4", "BRTSTAACNPR8", "PN")],
    )
    # 2 anos de balanço: receita 100, lucro 20 (2025) — PL 100; EBIT 30 + D&A 10
    con.executemany(
        "INSERT INTO fundamentos (cod_cvm, ano, receita, resultado_bruto, ebit, lucro_liquido,"
        " ativo_total, patrimonio_liquido, caixa, divida_bruta, setor_financeiro, da)"
        " VALUES ('9999', ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)",
        [
            (2024, 90e9, 40e9, 25e9, 15e9, 200e9, 90e9, 10e9, 30e9, 9e9),
            (2025, 100e9, 45e9, 30e9, 20e9, 220e9, 100e9, 12e9, 32e9, 10e9),
        ],
    )
    # cotações mensais + meta (preço D-1)
    con.executemany(
        "INSERT INTO cotacoes (ticker, competencia, fechamento, fechamento_ajustado) VALUES (?,?,?,?)",
        [("TSTA4", f"2026-{m:02d}", 38.0 + m, 38.0 + m) for m in range(1, 7)],
    )
    con.execute(
        "INSERT INTO cotacoes_meta (ticker, preco_atual, cotado_em, atualizado_em)"
        " VALUES ('TSTA4', 40.0, '2026-07-20', '2026-07-21')"
    )
    # proventos 12m: R$ 2/ação
    con.execute(
        "INSERT INTO acao_proventos (ticker, data_com, label, valor)"
        " VALUES ('TSTA4', '2026-05-10', 'DIVIDENDO', 2.0)"
    )
    con.commit()


def test_montar_dados_acao_none_para_desconhecido(con):
    assert acao_html.montar_dados_acao(con, "XXXX9") is None


def test_montar_dados_e_multiplos(con):
    _semear_empresa(con)
    dados = acao_html.montar_dados_acao(con, "TSTA4", hoje=date(2026, 7, 21))
    assert dados is not None
    assert dados["empresa"]["nome_pregao"] == "TESTECO"
    assert len(dados["papeis"]) == 2 and len(dados["balancos"]) == 2
    m = dados["multiplos"]["TSTA4"]
    # LPA = 20e9/1e9 = 20 -> P/L = 40/20 = 2; VPA = 100 -> P/VP 0.4; DY = 2/40 = 5%
    assert round(m["pl"], 2) == 2.0
    assert round(m["pvp"], 2) == 0.4
    assert round(m["dy"], 2) == 5.0
    # indicadores do último ano: ROE 20%, margem líquida 20%, EBITDA 40e9
    assert round(dados["indicadores"]["roe"], 1) == 20.0
    assert dados["indicadores"]["ebitda"] == 40e9


def test_pagina_da_acao_renderiza_no_design(con):
    _semear_empresa(con)
    dados = acao_html.montar_dados_acao(con, "TSTA4", hoje=date(2026, 7, 21))
    pagina = acao_html.gerar(dados, agora=datetime(2026, 7, 21, 12, 0), publicados={"TSTA3", "TSTA4"})
    # identidade e design novo
    assert "TSTA4" in pagina and "TESTECO" in pagina
    assert "Scout Display" in pagina  # fonte do design-refresh
    # cards com múltiplos e fundamentos
    assert "P/L" in pagina and "P/VP" in pagina and "Dividend yield 12m" in pagina
    assert "ROE" in pagina and "EBITDA" in pagina
    # carteirinha de regras da classe (isenção, JCP, ON vs PN)
    assert "R$ 20 mil" in pagina and "JCP" in pagina and "tag along" in pagina
    # papéis da empresa com link cruzado para o irmão
    assert 'href="TSTA3.html"' in pagina
    # balanço anual + rodapé com fontes
    assert "Balanço anual (DFP)" in pagina
    assert "não é recomendação" in pagina.lower()
    # nunca veredito
    for veredito in ("compre", "comprar", "barato", "subvalor", "sobrevalor"):
        assert veredito not in pagina.lower()


def test_indice_acoes_lista_e_rankings(con):
    _semear_empresa(con)
    dados = acao_html.montar_dados_acao(con, "TSTA4", hoje=date(2026, 7, 21))
    pagina = modulo_site._indice_acoes([dados], datetime(2026, 7, 21, 12, 0))
    assert "1 papéis de <b>todas as companhias listadas em bolsa na B3</b>" in pagina
    # aviso de cobertura completa com honestidade sobre buracos de dado
    assert "Cobertura completa" in pagina and "nunca número inventado" in pagina
    assert 'href="TSTA4.html"' in pagina and "TESTECO" in pagina
    assert "Energia" in pagina  # setor curto (1º nível)
    assert "Maior dividend yield 12m" in pagina and "Menor P/L (com lucro)" in pagina
    assert "não recomendação" in pagina


def test_calculadoras_graham_e_bazin(con):
    _semear_empresa(con)
    dados = acao_html.montar_dados_acao(con, "TSTA4", hoje=date(2026, 7, 21))
    pagina = acao_html.gerar(dados, agora=datetime(2026, 7, 21, 12, 0))
    # Graham: prefill com LPA (20e9/1e9=20.00) e VPA (100e9/1e9=100.00) reais
    assert "fórmula de Graham" in pagina
    assert 'id="gr-lpa" value="20.00"' in pagina
    assert 'id="gr-vpa" value="100.00"' in pagina
    assert 'id="gr-mult" value="22.5"' in pagina  # premissa editável do usuário
    # Bazin: sem ano cheio anterior (provento é de 2026), base = últimos 12m
    assert "método Bazin" in pagina
    assert 'id="bz-div"' in pagina and 'data-v12m="2.00"' in pagina
    assert 'id="bz-dy" value="6"' in pagina  # DY mínimo clássico
    # mesmo padrão da Gordon: aviso ANTES do botão, corpo escondido, sem veredito
    assert pagina.count("não é recomendação") >= 2
    assert 'onclick="abrirCalc(this, calcGraham)"' in pagina
    for veredito in ("compre", "comprar", "barato", "subvalor", "sobrevalor"):
        assert veredito not in pagina.lower()


def test_graham_ausente_em_prejuizo(con):
    _semear_empresa(con)
    con.execute("UPDATE fundamentos SET lucro_liquido = -5e9 WHERE ano = 2025")
    con.commit()
    dados = acao_html.montar_dados_acao(con, "TSTA4", hoje=date(2026, 7, 21))
    pagina = acao_html.gerar(dados, agora=datetime(2026, 7, 21, 12, 0))
    assert "fórmula de Graham" not in pagina  # raiz de negativo não existe
    assert "método Bazin" in pagina  # dividendos existem, Bazin segue


def test_historico_de_proventos_com_dy(con):
    _semear_empresa(con)
    dados = acao_html.montar_dados_acao(con, "TSTA4", hoje=date(2026, 7, 21))
    pagina = acao_html.gerar(dados, agora=datetime(2026, 7, 21, 12, 0))
    assert "Histórico de proventos" in pagina
    # DY do ano = 2.00 / 44.00 (fechamento de jun/2026, último mês do ano na base)
    assert "DY 4,55%" in pagina


def test_checklist_de_fatos_na_pagina(con):
    _semear_empresa(con)
    # trimestres: T1–T3/2025 lucrativos + T1/2026 e homólogo (P/L vira TTM)
    con.executemany(
        "INSERT INTO fundamentos_tri (cod_cvm, trimestre, receita, lucro_liquido) VALUES ('9999', ?, ?, ?)",
        [("2025-T1", 25e9, 5e9), ("2025-T2", 25e9, 5e9), ("2025-T3", 25e9, 5e9),
         ("2026-T1", 28e9, 7e9)],
    )
    con.commit()
    dados = acao_html.montar_dados_acao(con, "TSTA4", hoje=date(2026, 7, 21))
    # TTM = anual 2025 (20e9) + T1'26 (7e9) − T1'25 (5e9) = 22e9 → P/L 40/22 ≈ 1.82
    assert dados["multiplos"]["TSTA4"]["lucro_base"] == "ttm"
    assert round(dados["multiplos"]["TSTA4"]["pl"], 2) == round(40.0 / 22.0, 2)
    # T4/2025 derivado do anual: 20e9 − 15e9 = 5e9 (entra na série dos 20 tris)
    assert ("2025-T4", 5e9) in dados["trimestres_lucro"]
    pagina = acao_html.gerar(dados, agora=datetime(2026, 7, 21, 12, 0))
    assert "Checklist de fatos" in pagina
    assert "não é nota nem recomendação" in pagina
    assert "últimos 12 meses (anual + trimestres ITR)" in pagina  # rótulo do P/L TTM
    assert "ROE acima de 10%" in pagina and "Liquidez acima de R$ 2 milhões/dia" in pagina


def test_medianas_setor_e_comparacao_nos_cards(con):
    _semear_empresa(con)  # TSTA (Energia)
    # +5 empresas do MESMO setor com P/L conhecidos → mediana com amostra ≥5
    for i, lucro in enumerate((10e9, 10e9, 20e9, 40e9, 80e9)):
        cod = f"88{i}"
        con.execute(
            "INSERT INTO empresas (cod_cvm, cnpj, radical, nome, nome_pregao, setor_b3,"
            " situacao, no_ibrx100, acoes_total) VALUES (?, ?, ?, ?, ?, 'Energia / X / Y', 'ATIVO', 0, 1000000000)",
            (cod, f"9900000000010{i}", f"EN{i}A", f"ENERGETICA {i}", f"EN{i}"),
        )
        con.execute(
            "INSERT INTO papeis (ticker, cod_cvm, isin, tipo) VALUES (?, ?, '', 'ON')",
            (f"EN{i}A3", cod),
        )
        con.execute(
            "INSERT INTO fundamentos (cod_cvm, ano, lucro_liquido, patrimonio_liquido, receita)"
            " VALUES (?, 2025, ?, 100e9, 50e9)", (cod, lucro),
        )
        con.execute(
            "INSERT INTO cotacoes_meta (ticker, preco_atual, cotado_em, atualizado_em)"
            " VALUES (?, 40.0, '2026-07-20', '2026-07-21')", (f"EN{i}A3",),
        )
    con.commit()
    medianas = acao_html.medianas_setor(con, hoje=date(2026, 7, 21))
    # P/L das 6 (com TSTA): [2.0(TSTA), 4.0, 4.0, 2.0, 1.0, 0.5] → mediana 2.0, n=6
    mediana_pl, n = medianas["Energia"]["pl"]
    assert n == 6 and mediana_pl == 2.0
    # cards mostram a régua do setor (factual, com o tamanho da amostra)
    dados = acao_html.montar_dados_acao(con, "TSTA4", hoje=date(2026, 7, 21), medianas=medianas)
    pagina = acao_html.gerar(dados, agora=datetime(2026, 7, 21, 12, 0))
    assert "mediana do setor: 2,00 (6 cias)" in pagina
    # sem medianas pré-computadas (CLI), a página sai sem a régua — nunca inventa
    dados_cli = acao_html.montar_dados_acao(con, "TSTA4", hoje=date(2026, 7, 21))
    assert dados_cli["setor_stats"] == {}


def test_home_tem_pills_de_setor_das_acoes(con):
    _semear_empresa(con)
    dados = acao_html.montar_dados_acao(con, "TSTA4", hoje=date(2026, 7, 21))
    home = modulo_site._home([], [], datetime(2026, 7, 21, 12, 0), {}, [dados])
    # pill de setor linkando a listagem com o filtro pré-selecionado (?setor=)
    assert '<a class="pill" href="acoes.html?setor=Energia">Energia <b>1</b></a>' in home


def test_comparador_de_acoes(con):
    _semear_empresa(con)
    dados = acao_html.montar_dados_acao(con, "TSTA4", hoje=date(2026, 7, 21))
    pagina = modulo_site._pagina_comparar_acoes([dados])
    assert "Comparar ações" in pagina
    assert '<option value="TSTA4">TSTA4 — TESTECO</option>' in pagina
    # linhas de fatos por papel + aviso de setores diferentes (JS)
    for rotulo in ('["P/L"', '["ROE"', '["Margem líquida"', '["Alertas"'):
        assert rotulo in pagina
    assert "setores diferentes" in pagina
    assert "sem &quot;vencedor&quot;" in pagina or 'sem "vencedor"' in pagina
    for veredito in ("compre", "comprar", "barato", "vencedor:"):
        assert veredito not in pagina.lower()


def test_busca_viva_inclui_acoes(con):
    _semear_empresa(con)
    dados = acao_html.montar_dados_acao(con, "TSTA4", hoje=date(2026, 7, 21))
    ativos = modulo_site._ativos_busca([], [], [dados])
    # sem dfp_meta semeada, o selo cai honestamente em "insuficiente" (nunca aprovação)
    assert ativos == [
        {"t": "TSTA4", "n": "TESTECO", "c": "Ação", "s": "insuficiente", "r": "Histórico insuficiente"}
    ]


def test_selo_e_flags_na_pagina_e_listagem(con):
    _semear_empresa(con)
    # dfp_meta saudável + uma reapresentação p/ disparar flag
    con.execute(
        "INSERT INTO dfp_meta (cod_cvm, ano, dt_receb, versao, acoes_total, acoes_tesouro,"
        " parecer_tipo, parecer_continuidade, parecer_trecho)"
        " VALUES ('9999', 2025, '2026-02-20', 3, 1000000000, 0, 'Sem Ressalva', 0, NULL)"
    )
    con.execute(
        "INSERT INTO auditores (cod_cvm, auditor, inicio, fim) VALUES ('9999','KPMG','2020-01-01',NULL)"
    )
    con.commit()
    dados = acao_html.montar_dados_acao(con, "TSTA4", hoje=date(2026, 7, 21))
    assert any("reapresentado" in f.titulo.lower() for f in dados["flags"].flags)
    assert dados["selo"].nivel == "atencao"
    pagina = acao_html.gerar(dados, agora=datetime(2026, 7, 21, 12, 0))
    assert "🚩 Red flags" in pagina and "reapresentado" in pagina.lower()
    assert "Atenção" in pagina  # selo no topo
    listagem = modulo_site._indice_acoes([dados], datetime(2026, 7, 21, 12, 0))
    assert "selo-dot" in listagem and "Atenção" in listagem


def test_secao_processos_judiciais_na_pagina(con):
    _semear_empresa(con)
    dados = acao_html.montar_dados_acao(con, "TSTA4", hoje=date(2026, 7, 21))
    leitura = {"processos": {"id": 999, "referencia": "2026-12-31", "valor_provisionado": 2.5e9,
                             "texto": "- Tributário de R$ 1,2 bi: \"trecho\" (perda: possível)"}}
    pagina = acao_html.gerar(dados, agora=datetime(2026, 7, 21, 12, 0), leitura=leitura)
    assert "Processos judiciais (FRE)" in pagina
    assert "R$ 2,5B" in pagina  # valor provisionado (estruturado, sem IA)
    assert "rad.cvm.gov.br" in pagina  # link para o original
    assert "pode conter erros de leitura" in pagina  # honestidade da IA
    # sem o bloco, a seção não aparece
    assert "Processos judiciais (FRE)" not in acao_html.gerar(dados, agora=datetime(2026, 7, 21, 12, 0))
