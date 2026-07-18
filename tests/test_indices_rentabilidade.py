from datetime import date

import pytest

from fato_relevante import analise, armazenamento
from fato_relevante.coleta import cvm, indices
from fato_relevante.relatorio import html as relatorio_html


def test_extrair_sgs():
    dados = [
        {"data": "01/01/2026", "valor": "1.16"},
        {"data": "01/02/2026", "valor": "1.00"},
        {"data": "", "valor": "9"},  # lixo ignorado
        {"data": "01/03/2026", "valor": ""},
    ]
    assert indices.extrair(dados) == [("2026-01", 1.16), ("2026-02", 1.0)]


def test_garantir_atualizados_grava_e_nao_rebaixa(con, monkeypatch):
    chamadas = []

    def _buscar_fake(serie):
        chamadas.append(serie)
        return [("2026-01", 1.0)]

    monkeypatch.setattr(indices, "buscar", _buscar_fake)
    assert indices.garantir_atualizados(con, hoje=date(2026, 2, 18)) is None
    assert sorted(chamadas) == ["CDI", "IPCA"]
    assert armazenamento.serie_indice(con, "CDI") == {"2026-01": 1.0}
    # segunda chamada no mesmo dia: nada de rede
    chamadas.clear()
    assert indices.garantir_atualizados(con, hoje=date(2026, 2, 18)) is None
    assert chamadas == []


def test_acumulado_indice_composto():
    valores = {"2026-01": 1.0, "2026-02": 1.0}
    acumulado = analise._acumulado_indice(valores, ["2025-12", "2026-01", "2026-02"])
    assert acumulado[0] == ("2025-12", 0.0)
    assert acumulado[1][1] == pytest.approx(1.0)
    assert acumulado[2][1] == pytest.approx(2.01)  # juros compostos


def test_acumulado_indice_para_no_mes_sem_dado():
    valores = {"2026-01": 1.0}  # fevereiro ainda não publicado
    acumulado = analise._acumulado_indice(valores, ["2025-12", "2026-01", "2026-02"])
    assert [c for c, _ in acumulado] == ["2025-12", "2026-01"]


def test_acumulado_fundo_base_zero():
    acumulado = analise._acumulado_fundo([("2026-01", 100.0), ("2026-02", 110.0)])
    assert acumulado == [("2026-01", 0.0), ("2026-02", pytest.approx(10.0))]


def test_html_com_rentabilidade_e_abas(con, zip_cvm):
    cvm.carregar_zip(con, zip_cvm(True), "inf_mensal_fii_2026.zip")
    candles = [(f"{ano}-{mes:02d}", 100.0 + i, 100.0 + i) for i, (ano, mes) in enumerate(
        [(2025, m) for m in range(1, 13)] + [(2026, 1), (2026, 2)]
    )]
    armazenamento.gravar_cotacoes(con, "TSTE11", candles, 115.0, "2026-02-17", "2026-02-18")
    armazenamento.gravar_indice(
        con, "CDI", [(f"{a}-{m:02d}", 1.0) for a in (2025, 2026) for m in range(1, 13)], "2026-02-18"
    )
    completo = analise.montar_completo(con, "tste11")
    assert "12 meses" in completo.graficos.rentabilidade
    series_12m = dict(completo.graficos.rentabilidade["12 meses"])
    assert "Fundo" in series_12m and "CDI" in series_12m

    pagina = relatorio_html.gerar(completo)
    assert "Rentabilidade acumulada" in pagina
    assert "class=\"abas\"" in pagina
    assert "function mostrar" in pagina
