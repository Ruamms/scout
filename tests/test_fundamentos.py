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
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("dfp_cia_aberta_DRE_con_2024.csv", (_COLS + "\n" + "\n".join(dre)).encode("latin-1"))
        zf.writestr("dfp_cia_aberta_BPA_con_2024.csv", (_COLS + "\n" + "\n".join(bpa)).encode("latin-1"))
        zf.writestr("dfp_cia_aberta_BPP_con_2024.csv", (_COLS + "\n" + "\n".join(bpp)).encode("latin-1"))
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

    banco = fundamentos.indicadores(dados[19348])
    assert banco["margem_bruta"] is None  # não se aplica a banco
    assert banco["margem_liquida"] == pytest.approx(15.0)
    assert banco["roe"] == pytest.approx(12.0)
    assert banco["divida_liquida"] is None


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
    # baixou os 4 anos completos (2022..2025)
    assert baixados == [2022, 2023, 2024, 2025]
    serie = armazenamento.fundamentos_da_empresa(con, "9512")
    assert [linha["ano"] for linha in serie] == [2022, 2023, 2024, 2025]
    assert serie[-1]["lucro_liquido"] == 15_000

    # 2ª rodada: anos fechados já carregados são pulados; só o mais recente rebaixa
    baixados.clear()
    fundamentos.atualizar(con, hoje=date(2026, 7, 19))
    assert baixados == [2025]  # só o ano recente é rebaixado
