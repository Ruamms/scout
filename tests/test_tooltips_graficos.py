"""Rótulos e tooltips dos gráficos SVG."""

from scout import formato
from scout.relatorio import graficos


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


def test_barras_anuais_mostram_extra_no_topo():
    pontos = [("2024", 8.5), ("2025", 9.1)]
    svg = graficos.grafico_barras(
        pontos, formatador=lambda v: formato.percentual(v), extras=["≈ R$ 12,30", None]
    )
    assert "≈ R$ 12,30" in svg  # segunda linha no topo da barra
    assert "<title>2024: 8,50% · ≈ R$ 12,30</title>" in svg
    assert "<title>2025: 9,10%</title>" in svg  # sem extra, tooltip só com %


def test_linha_com_valores_nos_pontos():
    pontos = [(f"2025-{m:02d}", float(m)) for m in range(1, 13)]
    svg = graficos.grafico_linhas(
        [("PL", pontos)], formatador=lambda v: f"R$ {formato.decimal(v)}", valores_nos_pontos=True
    )
    # valor escrito acima de cada ponto (além do tooltip)
    assert svg.count('font-size="10">R$ ') == 12


def test_barras_mensais_extra_so_no_tooltip_e_valor_vertical():
    pontos = [(f"2024-{m:02d}", 1.0) for m in range(1, 13)] + [
        (f"2025-{m:02d}", 1.0) for m in range(1, 13)
    ]
    extras = ["≈ R$ 1,10"] * len(pontos)
    svg = graficos.grafico_barras(pontos, formatador=lambda v: formato.percentual(v), extras=extras)
    assert "<title>jan/24: 1,00% · ≈ R$ 1,10</title>" in svg
    assert 'rotate(-90' in svg  # valor % em texto vertical no topo
    # extra não vira texto solto no topo com muitas barras
    assert svg.count("≈ R$ 1,10") == len(pontos)  # só nos tooltips
