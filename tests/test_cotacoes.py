from datetime import date, datetime, timezone

import pytest

from fato_relevante import analise, armazenamento
from fato_relevante.coleta import cotacoes, cvm


def _ts(ano, mes):
    return int(datetime(ano, mes, 1, tzinfo=timezone.utc).timestamp())


def _json_yahoo():
    return {
        "chart": {
            "result": [
                {
                    "meta": {
                        "regularMarketPrice": 105.5,
                        "regularMarketTime": _ts(2026, 2) + 86400 * 16,
                    },
                    "timestamp": [_ts(2026, 1), _ts(2026, 2)],
                    "indicators": {
                        "quote": [{"close": [100.0, 105.5]}],
                        "adjclose": [{"adjclose": [99.0, 105.5]}],
                    },
                }
            ]
        }
    }


def test_extrair_json_yahoo():
    candles, preco, cotado_em = cotacoes.extrair(_json_yahoo())
    assert candles == [("2026-01", 100.0, 99.0), ("2026-02", 105.5, 105.5)]
    assert preco == 105.5
    assert cotado_em == "2026-02-17"


def test_garantir_atualizada_busca_e_grava(con, monkeypatch):
    monkeypatch.setattr(
        cotacoes, "buscar", lambda ticker: ([("2026-01", 100.0, 99.0)], 101.0, "2026-02-17")
    )
    aviso = cotacoes.garantir_atualizada(con, "tste11", hoje=date(2026, 2, 18))
    assert aviso is None
    meta = armazenamento.cotacao_meta(con, "TSTE11")
    assert meta["preco_atual"] == 101.0
    assert meta["atualizado_em"] == "2026-02-18"


def test_garantir_atualizada_nao_rebaixa_no_mesmo_dia(con, monkeypatch):
    armazenamento.gravar_cotacoes(con, "TSTE11", [], 101.0, "2026-02-17", "2026-02-18")

    def _explode(ticker):
        raise AssertionError("não deveria ir à rede")

    monkeypatch.setattr(cotacoes, "buscar", _explode)
    assert cotacoes.garantir_atualizada(con, "TSTE11", hoje=date(2026, 2, 18)) is None


def test_sem_conexao_usa_cache_com_aviso(con, monkeypatch):
    armazenamento.gravar_cotacoes(con, "TSTE11", [], 101.0, "2026-02-17", "2026-02-10")

    def _falha(ticker):
        raise OSError("sem rede")

    monkeypatch.setattr(cotacoes, "buscar", _falha)
    aviso = cotacoes.garantir_atualizada(con, "TSTE11", hoje=date(2026, 2, 18))
    assert aviso is not None
    assert "17/02/2026" in aviso


def test_serie_vp_ajustada_neutraliza_desdobramento():
    class Linha(dict):
        def __getitem__(self, chave):
            return dict.__getitem__(self, chave)

    serie = [
        Linha(competencia="2019-10", vp_cota=1600.0),
        Linha(competencia="2019-11", vp_cota=1660.0),
        Linha(competencia="2019-12", vp_cota=166.0),  # desdobramento 10:1
        Linha(competencia="2020-01", vp_cota=168.0),
    ]
    ajustada = analise._serie_vp_ajustada(serie)
    assert ajustada["2019-12"] == 166.0
    assert ajustada["2020-01"] == 168.0
    assert ajustada["2019-11"] == pytest.approx(166.0)
    assert ajustada["2019-10"] == pytest.approx(160.0)


def test_raio_x_com_cotacao_traz_pvp(con, zip_cvm):
    cvm.carregar_zip(con, zip_cvm(True), "inf_mensal_fii_2026.zip")
    armazenamento.gravar_cotacoes(
        con,
        "TSTE11",
        [("2026-01", 90.0, 90.0), ("2026-02", 100.0, 100.0)],
        100.0,
        "2026-02-17",
        "2026-02-18",
    )
    raiox = analise.montar_raio_x(con, "tste11")
    nomes = [linha.nome for linha in raiox.indicadores]
    assert nomes[0] == "Cotação"
    assert nomes[1] == "P/VP"
    cotacao = raiox.indicadores[0]
    assert cotacao.atual == "R$ 100,00"
    pvp = raiox.indicadores[1]
    # vp_cota atual da fixture = 95.45 -> P/VP = 100 / 95.45 = 1.05
    assert pvp.atual == "1,05"
    assert raiox.cotacao_em == "17/02/2026"


def test_raio_x_sem_cotacao_avisa_em_nota(con, zip_cvm):
    cvm.carregar_zip(con, zip_cvm(True), "inf_mensal_fii_2026.zip")
    raiox = analise.montar_raio_x(con, "tste11")
    assert not any(linha.nome == "Cotação" for linha in raiox.indicadores)
    assert any("sem cotação de bolsa" in nota for nota in raiox.notas)
