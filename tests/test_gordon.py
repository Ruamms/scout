"""Calculadora de Preço Justo (Modelo de Gordon) — extra opt-in, sem recomendação."""

from scout.relatorio.html import _calculadora_gordon


def test_gordon_opt_in_com_aviso_e_sem_veredito():
    # div_anual = soma real de 12 meses; dy_anual = DY do fundo (seed do r); último rend
    html = _calculadora_gordon(
        preco=100.0, div_anual=8.0, dy_anual=8.0, ultimo_rend=0.70, periodo="07/2025 e 06/2026"
    )
    # aviso de "não é recomendação" ANTES do botão de abrir (gate opt-in)
    assert "não é recomendação" in html
    assert 'onclick="abrirGordon(this)"' in html
    assert "<div hidden>" in html  # corpo só aparece ao abrir
    assert 'value="8.00"' in html  # dividendo anual = soma dos 12 meses
    assert 'value="8.0"' in html   # r pré-preenchido com o DY do próprio fundo
    assert "último rendimento: R$ 0.70" in html  # referência do último dividendo
    # nota do período: janela exata que gerou o dividendo padrão
    assert "dividendos distribuídos entre 07/2025 e 06/2026" in html
    assert 'id="gd-r"' in html and 'id="gd-g"' in html
    assert "R$ 100.00" in html  # cotação atual ao lado (fato), sem julgamento
    # nenhuma palavra de veredito de compra/venda ("recomendação" é permitida só no aviso "não é")
    for veredito in ("compre", "comprar", "barato", "subvalor", "sobrevalor", "vale a pena"):
        assert veredito not in html.lower()


def test_gordon_ausente_sem_dados():
    assert _calculadora_gordon(0, 8.0, 8.0, 0.7) == ""    # sem preço
    assert _calculadora_gordon(100, 0, 0, 0) == ""         # sem dividendo
