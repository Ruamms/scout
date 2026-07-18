from fato_relevante import formato
from fato_relevante.relatorio import apoio, graficos


# --- PIX ------------------------------------------------------------------------


def test_crc16_vetor_padrao():
    # vetor de verificação clássico do CRC-16/CCITT-FALSE
    assert apoio._crc16("123456789") == "29B1"


def test_payload_pix_estrutura():
    payload = apoio.payload_pix()
    assert payload.startswith("000201")
    assert "br.gov.bcb.pix" in payload
    assert "ruamms3@gmail.com" in payload
    assert "5802BR" in payload
    # CRC: 6304 + 4 hexas no final, e recalculável
    assert payload[-8:-4] == "6304"
    assert apoio._crc16(payload[:-4]) == payload[-4:]


def test_pagina_apoio(tmp_path):
    caminho = apoio.salvar(tmp_path)
    conteudo = caminho.read_text(encoding="utf-8")
    assert caminho.name == "apoie.html"
    assert "ruamms3@gmail.com" in conteudo
    assert "<svg" in conteudo  # QR code
    assert "copia-e-cola" in conteudo


# --- rótulos e tooltips dos gráficos ----------------------------------------------


def test_competencia_curta():
    assert formato.competencia_curta("2026-05") == "mai/26"
    assert formato.competencia_curta("2024-12") == "dez/24"
    assert formato.competencia_curta("2024") == "2024"  # rótulo de ano passa direto


def test_linha_curta_tem_rotulos_de_mes_e_tooltip():
    pontos = [(f"2025-{m:02d}", float(m)) for m in range(1, 13)]
    svg = graficos.grafico_linhas([("Fundo", pontos)])
    assert "jan/25" in svg
    assert "<circle" in svg
    assert "<title>Fundo · mar/25: 3,00</title>" in svg


def test_linha_longa_usa_rotulos_de_ano():
    pontos = [
        (f"{ano}-{mes:02d}", 1.0)
        for ano in range(2017, 2027)
        for mes in range(1, 13)
    ]
    svg = graficos.grafico_linhas([("x", pontos)])
    assert ">2020<" in svg
    # rótulo de mês só nos tooltips, não no eixo
    assert ">jan/17</text>" not in svg


def test_barras_mensais_com_tooltip_e_rotulo_curto():
    pontos = [(f"2025-{m:02d}", 0.5 + m / 100) for m in range(1, 13)]
    svg = graficos.grafico_barras(pontos, formatador=lambda v: formato.percentual(v))
    assert "<title>jan/25: 0,51%</title>" in svg
    assert "jan/25" in svg
