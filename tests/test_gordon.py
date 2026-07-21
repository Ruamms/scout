"""Calculadora de Preço Justo (Modelo de Gordon) — extra opt-in, sem recomendação."""

from scout.relatorio.html import _calculadora_gordon


def test_gordon_opt_in_com_aviso_e_sem_veredito():
    # 12 meses completos: div_12m = soma real; base padrão = soma de 12 meses
    html = _calculadora_gordon(
        preco=100.0,
        div_12m=8.0,
        ultimo_x12=8.4,
        dy_anual=8.0,
        ultimo_rend=0.70,
        periodo="07/2025 e 06/2026",
        n_meses=12,
    )
    # aviso de "não é recomendação" ANTES do botão de abrir (gate opt-in)
    assert "não é recomendação" in html
    assert 'onclick="abrirGordon(this)"' in html
    assert "<div hidden>" in html  # corpo só aparece ao abrir
    assert 'value="8.00"' in html  # dividendo padrão (12m completos) = soma anual dos 12 meses
    assert 'value="8.0"' in html   # r pré-preenchido com o DY do próprio fundo
    # duas bases via botão (segmented); no modo último o campo é MENSAL (0.70), não 0.70×12
    assert 'data-v12m="8.00"' in html and 'data-vult="0.70"' in html
    assert 'data-modo="12m"' in html  # 12m completos → começa no modo soma real
    assert "gordonBase('12m', this)" in html and "gordonBase('ult', this)" in html
    assert "Soma dos últimos 12 meses" in html
    assert "Só o último dividendo mensal (× 12)" in html
    assert 'id="gd-cap"' in html  # caption mostra o anual calculado internamente
    assert "data-periodo=\"07/2025 e 06/2026\"" in html  # janela da soma de 12m (via caption)
    # com 12 meses, a base padrão é a soma real (botão dela ativo)
    assert 'class="ativo" onclick="gordonBase(\'12m\', this)"' in html
    assert 'id="gd-r"' in html and 'id="gd-g"' in html
    # legenda das letras + desfaz a confusão r × taxa de administração
    assert "não</b> é a taxa de administração" in html
    assert "retorno anual que <b>VOCÊ</b>" in html
    assert "Taxa de desconto — r (% a.a.)" in html
    assert "Crescimento — g (% a.a.)" in html
    assert "R$ 100.00" in html  # cotação atual ao lado (fato), sem julgamento
    # nenhuma palavra de veredito de compra/venda ("recomendação" é permitida só no aviso "não é")
    for veredito in ("compre", "comprar", "barato", "subvalor", "sobrevalor", "vale a pena"):
        assert veredito not in html.lower()


def test_gordon_menos_de_12m_padrao_ultimo_x12():
    # com menos de 12 meses, a soma subestimaria o ano → padrão = último × 12
    html = _calculadora_gordon(
        preco=100.0,
        div_12m=3.0,
        ultimo_x12=8.4,
        dy_anual=8.4,
        ultimo_rend=0.70,
        periodo="02/2026 e 06/2026",
        n_meses=5,
    )
    assert 'value="0.70"' in html  # campo começa no valor MENSAL (o × 12 é interno)
    assert 'data-modo="ult"' in html  # padrão cai para o modo "último" com < 12 meses
    assert "Soma dos 5 meses" in html  # rótulo do botão reflete o histórico parcial
    assert 'class="ativo" onclick="gordonBase(\'ult\', this)"' in html  # base padrão = último × 12


def test_gordon_ausente_sem_dados():
    assert _calculadora_gordon(0, 8.0, 8.4, 8.0, 0.7) == ""  # sem preço
    assert _calculadora_gordon(100, 0, 0, 0, 0, n_meses=12) == ""  # sem dividendo
