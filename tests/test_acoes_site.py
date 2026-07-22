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
    assert "1 papéis de empresas do <b>IBrX-100</b>" in pagina
    # aviso explícito de cobertura em fases (para não parecer erro do site)
    assert "Cobertura em fases" in pagina and "~100 mais líquidas" in pagina
    assert 'href="TSTA4.html"' in pagina and "TESTECO" in pagina
    assert "Energia" in pagina  # setor curto (1º nível)
    assert "Maior dividend yield 12m" in pagina and "Menor P/L (com lucro)" in pagina
    assert "não recomendação" in pagina


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
