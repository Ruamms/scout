"""E10 — preço por ativo de RENDA FIXA: títulos públicos via PU ANBIMA.

O CDA identifica título público por CD_SELIC + DT_VENC (CD_ATIVO/DS_ATIVO vêm
vazios — antes essas linhas eram descartadas e o IMAB11 ficava sem posições);
o PU diário do mercado secundário da ANBIMA casa exatamente nessa chave.
"""

import io
import zipfile
from datetime import date

from scout import precos
from scout.coleta import cda


def test_cda_captura_titulo_publico_por_selic_e_vencimento():
    cab = ("TP_FUNDO_CLASSE;CNPJ_FUNDO_CLASSE;DENOM_SOCIAL;DT_COMPTC;VL_PATRIM_LIQ;"
           "TP_APLIC;TP_ATIVO;VL_MERC_POS_FINAL;CD_ATIVO;DS_ATIVO;EMISSOR;QT_POS_FINAL;"
           "CD_SELIC;DT_VENC\n")
    linha = ("FIIM;10.406.511/0001-61;ETF RF;2026-06-30;1000000;Títulos Públicos;;"
             "251659.23;;;;6092;760199;2037-05-15\n")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("cda_fie_202606.csv", (cab + linha).encode("latin-1"))
    _, _, _, posicoes = cda.extrair_carteiras(buffer.getvalue(), {"10406511000161"})
    itens = posicoes["10406511000161"]
    assert len(itens) == 1
    assert itens[0]["codigo"] == "TPF760199"  # CD_SELIC vira a identidade
    assert itens[0]["vencimento"] == "2037-05-15"
    assert itens[0]["quantidade"] == 6092.0
    assert "Título público federal" in itens[0]["nome"]


_MS_ANBIMA = (
    "ANBIMA - cabecalho\n"
    "\n"
    "Titulo@Data Referencia@Codigo SELIC@Data Base/Emissao@Data Vencimento@Tx. Compra@Tx. Venda@Tx. Indicativas@PU@Desvio\n"
    "NTN-B@20260721@760199@20200515@20370515@7,1@7,0@7,05@4.321,098765@0,01\n"
    "LTN@20260721@100000@20240705@20261001@13,8@13,7@13,8@974,162802@0,01\n"
).encode("latin-1")


def test_reprecifica_titulo_publico_pelo_pu_anbima(con, monkeypatch):
    monkeypatch.setattr(precos, "_cache_anbima", None)  # limpa o cache do módulo
    monkeypatch.setattr(precos, "_baixar_anbima", lambda dia: _MS_ANBIMA)
    posicoes = [
        {"codigo": "TPF760199", "nome": "Título público federal", "pct": 90.0,
         "quantidade": 6092.0, "vencimento": "2037-05-15", "ticker_alvo": None},
        {"codigo": "TPF999999", "nome": "Título público federal", "pct": 10.0,
         "quantidade": 10.0, "vencimento": "2099-01-01", "ticker_alvo": None},  # sem PU no dia
    ]
    enriquecidas, resumo = precos.reprecificar_posicoes(con, posicoes)
    # PU pt-BR "4.321,098765" parseado; valor = PU × quantidade; nome ganha o título da ANBIMA
    assert enriquecidas[0]["preco_hoje"] == 4321.098765
    assert round(enriquecidas[0]["valor_hoje"], 2) == round(4321.098765 * 6092, 2)
    assert enriquecidas[0]["nome"] == "NTN-B (venc. 15/05/2037)"
    assert enriquecidas[0]["cotado_em"] == "2026-07-21"
    # título sem PU no arquivo: fica sem preço (nunca inventa)
    assert enriquecidas[1]["preco_hoje"] is None
    assert resumo["cobertura_pct"] == 90.0


def test_anbima_fora_do_ar_nao_quebra(con, monkeypatch):
    monkeypatch.setattr(precos, "_cache_anbima", None)
    monkeypatch.setattr(precos, "_baixar_anbima", lambda dia: None)  # 6 tentativas falham
    posicoes = [{"codigo": "TPF760199", "nome": "x", "pct": 100.0, "quantidade": 1.0,
                 "vencimento": "2037-05-15", "ticker_alvo": None}]
    enriquecidas, resumo = precos.reprecificar_posicoes(con, posicoes)
    assert enriquecidas[0]["preco_hoje"] is None  # posição fica no valor do CDA
    assert resumo["cobertura_pct"] == 0.0


_DB_ANBIMA = (
    "ANBIMA - Associacao\n"
    "\n"
    "Código@Nome@Repac./  Venc.@Índice/ Correção@Taxa de Compra@Taxa de Venda@Taxa Indicativa@"
    "Desvio Padrão@Intervalo Min@Intervalo Máx@PU@% PU Par@Duration@% Reune@Referência NTN-B\n"
    "SBSPD7@CIA SANEAMENTO BASICO SP (*)@15/12/2031@IPCA + 5,2%@--@--@5,1@0@5,0@5,2@1.234,567890@101,2@800@@\n"
    "JBSS32@JBS S/A (*) (**)@01/08/2030@DI + 1,2%@--@--@1,3@0@1,2@1,4@1042,5@100,1@600@@\n"
).encode("latin-1")


def test_reprecifica_debenture_pelo_pu_anbima(con, monkeypatch):
    monkeypatch.setattr(precos, "_cache_debentures", None)
    monkeypatch.setattr(precos, "_baixar_anbima", lambda dia, url=None: _DB_ANBIMA)
    posicoes = [
        # debênture com código = nome no CDA: preço + nome do emissor
        {"codigo": "SBSPD7", "nome": "SBSPD7", "pct": 60.0, "quantidade": 100.0,
         "vencimento": None, "ticker_alvo": None, "grupo": "Renda Fixa"},
        # PU pt-BR sem milhar também parseia
        {"codigo": "JBSS32", "nome": "JBSS32", "pct": 30.0, "quantidade": 10.0,
         "vencimento": None, "ticker_alvo": None, "grupo": "Renda Fixa"},
        # fora do arquivo: fica no valor do CDA (nunca inventa)
        {"codigo": "XXXX99", "nome": "XXXX99", "pct": 10.0, "quantidade": 1.0,
         "vencimento": None, "ticker_alvo": None, "grupo": "Renda Fixa"},
    ]
    enriquecidas, resumo = precos.reprecificar_posicoes(con, posicoes)
    assert enriquecidas[0]["preco_hoje"] == 1234.56789
    assert enriquecidas[0]["nome"] == "debênture CIA SANEAMENTO BASICO SP"  # (*) limpo
    assert enriquecidas[1]["preco_hoje"] == 1042.5
    assert enriquecidas[2]["preco_hoje"] is None
    assert resumo["cobertura_pct"] == 90.0


def test_debenture_so_consulta_anbima_para_renda_fixa(con, monkeypatch):
    chamadas = []
    monkeypatch.setattr(precos, "_cache_debentures", None)
    monkeypatch.setattr(
        precos, "_baixar_anbima", lambda dia, url=None: chamadas.append(1) or _DB_ANBIMA
    )
    # ação sem pregão e ativo do exterior NÃO disparam o download do arquivo
    posicoes = [
        {"codigo": "MORT11", "nome": "deslistada", "pct": 50.0, "quantidade": 1.0,
         "vencimento": None, "ticker_alvo": None, "grupo": "Ações"},
        {"codigo": "BRCYCRD03M11", "nome": "exterior", "pct": 50.0, "quantidade": 1.0,
         "vencimento": None, "ticker_alvo": None, "grupo": "Exterior"},
    ]
    precos.reprecificar_posicoes(con, posicoes)
    assert chamadas == []
