"""Ações A2 — indicadores fundamentais a partir da DFP padronizada da CVM."""

import io
import zipfile
from datetime import date

import pytest

from scout import armazenamento
from scout.coleta import fundamentos

_COLS = (
    "CNPJ_CIA;DT_REFER;VERSAO;DENOM_CIA;CD_CVM;GRUPO_DFP;MOEDA;ESCALA_MOEDA;"
    "ORDEM_EXERC;DT_INI_EXERC;DT_FIM_EXERC;CD_CONTA;DS_CONTA;VL_CONTA;ST_CONTA_FIXA"
)


def _linha(cd_cvm, conta, ds, valor, ordem="ÚLTIMO", escala="MIL"):
    return (
        f"11.111.111/0001-11;2024-12-31;1;EMPRESA;{cd_cvm};DF Consolidado;Real;{escala};"
        f"{ordem};2024-01-01;2024-12-31;{conta};{ds};{valor};S"
    )


def _zip_dfp() -> bytes:
    dre = [
        # comercial (9512): lucro em 3.11, EBIT em 3.05
        _linha("009512", "3.01", "Receita de Venda de Bens e/ou Serviços", "100"),
        _linha("009512", "3.03", "Resultado Bruto", "40"),
        _linha("009512", "3.05", "Resultado Antes do Resultado Financeiro e dos Tributos", "25"),
        _linha("009512", "3.11", "Lucro/Prejuízo Consolidado do Período", "15"),
        _linha("009512", "3.99", "Lucro por Ação - (Reais / Ação)", "2"),
        _linha("009512", "3.01", "Receita de Venda de Bens e/ou Serviços", "999", ordem="PENÚLTIMO"),
        # banco (19348): "Intermediação", lucro em 3.09, 3.05 NÃO é EBIT
        _linha("019348", "3.01", "Receitas da Intermediação Financeira", "80"),
        _linha("019348", "3.03", "Resultado Bruto Intermediação Financeira", "30"),
        _linha("019348", "3.05", "Resultado Antes dos Tributos sobre o Lucro", "20"),
        _linha("019348", "3.09", "Lucro/Prejuízo Consolidado do Período", "12"),
        _linha("019348", "3.99", "Lucro por Ação", "1"),
    ]
    bpa = [
        _linha("009512", "1", "Ativo Total", "500"),
        _linha("009512", "1.01.01", "Caixa e Equivalentes de Caixa", "30"),
        _linha("009512", "1.01.02", "Aplicações Financeiras", "20"),
        _linha("019348", "1", "Ativo Total", "900"),
    ]
    bpp = [
        _linha("009512", "2.03", "Patrimônio Líquido Consolidado", "200"),
        _linha("009512", "2.01.04", "Empréstimos e Financiamentos", "20"),
        _linha("009512", "2.02.01", "Empréstimos e Financiamentos", "60"),
        _linha("019348", "2.08", "Patrimônio Líquido Consolidado", "100"),
    ]
    dfc = [
        _linha("009512", "6.01.01.04", "Depreciação, depleção e amortização", "10"),
        # amortização de financiamento (6.03.xx) NÃO é D&A: deve ser ignorada
        _linha("009512", "6.03.03", "Amortizações de principal - financiamentos", "-5"),
    ]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("dfp_cia_aberta_DRE_con_2024.csv", (_COLS + "\n" + "\n".join(dre)).encode("latin-1"))
        zf.writestr("dfp_cia_aberta_BPA_con_2024.csv", (_COLS + "\n" + "\n".join(bpa)).encode("latin-1"))
        zf.writestr("dfp_cia_aberta_BPP_con_2024.csv", (_COLS + "\n" + "\n".join(bpp)).encode("latin-1"))
        zf.writestr("dfp_cia_aberta_DFC_MI_con_2024.csv", (_COLS + "\n" + "\n".join(dfc)).encode("latin-1"))
    return buffer.getvalue()


def test_extrai_comercial_e_banco_com_escala():
    dados = fundamentos.extrair_ano(_zip_dfp(), {9512, 19348})
    com = dados[9512]
    # escala MIL aplicada (100 -> 100.000); PENÚLTIMO ignorado (não vira 999)
    assert com["receita"] == 100_000
    assert com["resultado_bruto"] == 40_000
    assert com["ebit"] == 25_000
    assert com["lucro_liquido"] == 15_000  # 3.11, o maior 3.xx antes do 3.99
    assert com["ativo_total"] == 500_000
    assert com["caixa"] == 50_000  # 1.01.01 + 1.01.02
    assert com["patrimonio_liquido"] == 200_000
    assert com["divida_bruta"] == 80_000  # 2.01.04 + 2.02.01
    assert com["da"] == 10_000  # só a linha 6.01.01 (a amortização de financiamento 6.03 fica de fora)
    assert com["setor_financeiro"] == 0

    banco = dados[19348]
    assert banco["setor_financeiro"] == 1  # "Intermediação"
    assert banco["lucro_liquido"] == 12_000  # 3.09 (não existe 3.11 no banco)
    assert "ebit" not in banco  # 3.05 do banco não é "Antes do Resultado Financeiro"
    assert banco["patrimonio_liquido"] == 100_000  # casado pelo nome, não pelo código 2.03
    assert "divida_bruta" not in banco  # banco não tem 2.01.04/2.02.01


def test_indicadores_derivados():
    dados = fundamentos.extrair_ano(_zip_dfp(), {9512, 19348})
    com = fundamentos.indicadores(dados[9512])
    assert com["margem_bruta"] == pytest.approx(40.0)
    assert com["margem_liquida"] == pytest.approx(15.0)
    assert com["roe"] == pytest.approx(7.5)
    assert com["divida_liquida"] == pytest.approx(30_000)  # 80k - 50k caixa
    assert com["divida_liquida_pl"] == pytest.approx(0.15)
    assert com["ebitda"] == pytest.approx(35_000)  # EBIT 25k + D&A 10k
    assert com["margem_ebitda"] == pytest.approx(35.0)

    banco = fundamentos.indicadores(dados[19348])
    assert banco["margem_bruta"] is None  # não se aplica a banco
    assert banco["margem_liquida"] == pytest.approx(15.0)
    assert banco["roe"] == pytest.approx(12.0)
    assert banco["divida_liquida"] is None
    assert banco["ebitda"] is None  # banco não tem EBIT -> sem EBITDA


def test_atualizar_grava_serie_e_e_incremental(con, monkeypatch):
    con.execute(
        "INSERT INTO empresas (cod_cvm, cnpj, radical, no_ibrx100) VALUES ('9512', '1', 'PETR', 1)"
    )
    con.commit()
    baixados = []

    def _baixar_fake(ano):
        baixados.append(ano)
        return _zip_dfp()

    monkeypatch.setattr(fundamentos, "_baixar", _baixar_fake)
    fundamentos.atualizar(con, hoje=date(2026, 7, 19))
    # baixou os 6 anos completos (2020..2025 — CAGR de 5 anos no checklist)
    assert baixados == [2020, 2021, 2022, 2023, 2024, 2025]
    serie = armazenamento.fundamentos_da_empresa(con, "9512")
    assert [linha["ano"] for linha in serie] == [2020, 2021, 2022, 2023, 2024, 2025]
    assert serie[-1]["lucro_liquido"] == 15_000

    # 2ª rodada: anos fechados já carregados são pulados; só o mais recente rebaixa
    baixados.clear()
    fundamentos.atualizar(con, hoje=date(2026, 7, 19))
    assert baixados == [2025]  # só o ano recente é rebaixado


def test_multiplos_pl_pvp_dy():
    # 1000 ações, lucro 200 -> LPA 0,20; PL 1000 -> VPA 1,00; preço 2,00; div 0,10/ação
    r = fundamentos.multiplos(
        preco=2.0, dividendos_12m=0.10, lucro=200.0, patrimonio_liquido=1000.0, acoes_total=1000.0
    )
    assert r["pl"] == pytest.approx(10.0)   # 2,00 / 0,20
    assert r["pvp"] == pytest.approx(2.0)   # 2,00 / 1,00
    assert r["dy"] == pytest.approx(5.0)    # 100 * 0,10 / 2,00


def test_multiplos_none_quando_falta_ou_prejuizo():
    # sem ações: P/L e P/VP None (precisam do LPA/VPA); DY independe de ações
    r0 = fundamentos.multiplos(2.0, 0.1, 200.0, 1000.0, None)
    assert r0["pl"] is None and r0["pvp"] is None and r0["dy"] == pytest.approx(5.0)
    # prejuízo -> P/L None (não faz sentido), mas P/VP e DY seguem
    r = fundamentos.multiplos(2.0, 0.0, -50.0, 1000.0, 1000.0)
    assert r["pl"] is None and r["pvp"] == pytest.approx(2.0) and r["dy"] == pytest.approx(0.0)
    # sem preço -> P/VP e DY None
    r2 = fundamentos.multiplos(None, 0.1, 200.0, 1000.0, 1000.0)
    assert r2["pvp"] is None and r2["dy"] is None


def test_multiplos_do_papel_junta_as_fontes(con):
    con.execute("INSERT INTO empresas (cod_cvm, radical, acoes_total) VALUES ('9512','PETR',1000)")
    con.execute("INSERT INTO papeis (ticker, cod_cvm, isin, tipo) VALUES ('PETR4','9512','x','PN')")
    con.execute(
        "INSERT INTO fundamentos (cod_cvm, ano, lucro_liquido, patrimonio_liquido) VALUES ('9512',2024,200,1000)"
    )
    armazenamento.gravar_cotacoes(con, "PETR4", [("2026-06", 2.0, 2.0)], 2.0, "2026-07-17", "2026-07-17T20:00")
    con.execute("INSERT INTO acao_proventos (ticker, data_com, label, valor) VALUES ('PETR4','2026-05-01','DIV',0.10)")
    # provento fora da janela de 12 meses não conta
    con.execute("INSERT INTO acao_proventos (ticker, data_com, label, valor) VALUES ('PETR4','2020-01-01','DIV',9.99)")
    con.commit()
    r = fundamentos.multiplos_do_papel(con, "petr4", hoje=date(2026, 7, 20))
    assert r["pl"] == pytest.approx(10.0)
    assert r["pvp"] == pytest.approx(2.0)
    assert r["dy"] == pytest.approx(5.0)  # só os 0,10 recentes


# --- ITR trimestral: trimestres isolados + lucro TTM -------------------------


def _zip_itr(ano: int = 2026) -> bytes:
    import io
    import zipfile

    cab = ("CNPJ_CIA;DT_REFER;VERSAO;DENOM_CIA;CD_CVM;ESCALA_MOEDA;ORDEM_EXERC;"
           "DT_INI_EXERC;DT_FIM_EXERC;CD_CONTA;DS_CONTA;VL_CONTA\n")
    linhas = (
        # T1 isolado (ÚLTIMO) + homólogo (PENÚLTIMO) — receita e lucro
        f"11;{ano}-03-31;1;TST;9999;MIL;ÚLTIMO;{ano}-01-01;{ano}-03-31;3.01;Receita;100000\n"
        f"11;{ano}-03-31;1;TST;9999;MIL;ÚLTIMO;{ano}-01-01;{ano}-03-31;3.11;Lucro;20000\n"
        f"11;{ano}-03-31;1;TST;9999;MIL;PENÚLTIMO;{ano-1}-01-01;{ano-1}-03-31;3.11;Lucro;15000\n"
        # ACUMULADO do ano (jan–jun): NÃO pode entrar como trimestre
        f"11;{ano}-06-30;1;TST;9999;MIL;ÚLTIMO;{ano}-01-01;{ano}-06-30;3.11;Lucro;45000\n"
        # T2 isolado
        f"11;{ano}-06-30;1;TST;9999;MIL;ÚLTIMO;{ano}-04-01;{ano}-06-30;3.11;Lucro;25000\n"
        # versão 2 do T1 corrige o lucro (a maior versão vence)
        f"11;{ano}-03-31;2;TST;9999;MIL;ÚLTIMO;{ano}-01-01;{ano}-03-31;3.11;Lucro;21000\n"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr(f"itr_cia_aberta_DRE_con_{ano}.csv", (cab + linhas).encode("latin-1"))
    return buffer.getvalue()


def test_extrair_trimestres_isolados_e_versao():
    tris = fundamentos.extrair_trimestres(_zip_itr(2026), {9999})
    assert tris[(9999, "2026-T1")]["lucro_liquido"] == 21_000_000  # versão 2 venceu, escala MIL
    assert tris[(9999, "2026-T2")]["lucro_liquido"] == 25_000_000
    assert tris[(9999, "2025-T1")]["lucro_liquido"] == 15_000_000  # homólogo entra
    # o acumulado jan–jun (6 meses) NÃO virou trimestre
    assert all(t.endswith(("T1", "T2")) for _, t in tris)


def test_lucro_ttm_desliza_a_janela(con):
    con.execute("INSERT INTO fundamentos (cod_cvm, ano, lucro_liquido) VALUES ('9999', 2025, 100e9)")
    con.executemany(
        "INSERT INTO fundamentos_tri (cod_cvm, trimestre, lucro_liquido) VALUES ('9999', ?, ?)",
        [("2026-T1", 30e9), ("2025-T1", 20e9)],
    )
    con.commit()
    # TTM = 100 + 30 − 20 = 110 bi
    assert fundamentos.lucro_ttm(con, "9999") == 110e9


def test_lucro_ttm_none_sem_par_homologo(con):
    con.execute("INSERT INTO fundamentos (cod_cvm, ano, lucro_liquido) VALUES ('9999', 2025, 100e9)")
    con.execute("INSERT INTO fundamentos_tri (cod_cvm, trimestre, lucro_liquido) VALUES ('9999', '2026-T1', 30e9)")
    con.commit()
    assert fundamentos.lucro_ttm(con, "9999") is None  # sem o homólogo 2025-T1, não desliza
