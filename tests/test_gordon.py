"""Calculadora de Preço Justo (Modelo de Gordon) — extra opt-in, sem recomendação."""

from scout.relatorio.html import _calculadora_gordon


def test_gordon_opt_in_com_aviso_e_sem_veredito():
    html = _calculadora_gordon(preco=100.0, rendimento_mensal=0.80)
    # aviso de "não é recomendação" ANTES do botão de abrir (gate opt-in)
    assert "não é recomendação" in html
    assert 'onclick="abrirGordon(this)"' in html
    assert "<div hidden>" in html  # corpo só aparece ao abrir
    # dividendo anual pré-preenchido = rendimento mensal × 12
    assert 'value="9.60"' in html
    assert 'id="gd-r"' in html and 'id="gd-g"' in html
    # cotação atual mostrada ao lado (fato), sem julgamento
    assert "R$ 100.00" in html
    # nenhuma palavra de veredito de compra/venda ("recomendação" é permitida só no aviso "não é")
    for veredito in ("compre", "comprar", "barato", "subvalor", "sobrevalor", "vale a pena"):
        assert veredito not in html.lower()


def test_gordon_ausente_sem_dados():
    assert _calculadora_gordon(0, 0.5) == ""       # sem preço
    assert _calculadora_gordon(100, 0) == ""        # sem rendimento
