from datetime import datetime

from fato_relevante import analise, armazenamento, redflags
from fato_relevante.coleta import cvm
from fato_relevante.modelos import RedFlag, Severidade
from fato_relevante.relatorio import graficos
from fato_relevante.relatorio import html as relatorio_html


def _completo(con, zip_cvm):
    cvm.carregar_zip(con, zip_cvm(True), "inf_mensal_fii_2026.zip")
    armazenamento.gravar_cotacoes(
        con,
        "TSTE11",
        [("2026-01", 90.0, 90.0), ("2026-02", 100.0, 100.0)],
        100.0,
        "2026-02-17",
        "2026-02-18",
    )
    return analise.montar_completo(con, "tste11")


# --- selo ----------------------------------------------------------------------


def _resultado(flags=(), nao_avaliadas=()):
    resultado = redflags.Resultado()
    resultado.flags = [
        RedFlag(sev, "t", "f", "e", "fonte") for sev in flags
    ]
    resultado.nao_avaliadas = list(nao_avaliadas)
    return resultado


def test_selo_precedencia():
    assert redflags.selo(_resultado()).nivel == "sem_alertas"
    assert redflags.selo(_resultado(flags=[Severidade.BAIXA])).nivel == "leves"
    assert redflags.selo(_resultado(flags=[Severidade.MEDIA])).nivel == "atencao"
    assert redflags.selo(_resultado(flags=[Severidade.BAIXA, Severidade.ALTA])).nivel == "grave"
    # muitas regras não avaliadas -> insuficiente, mesmo com alerta baixo
    assert (
        redflags.selo(_resultado(flags=[Severidade.BAIXA], nao_avaliadas=["a", "b", "c"])).nivel
        == "insuficiente"
    )
    # alerta grave vence histórico insuficiente
    assert (
        redflags.selo(
            _resultado(flags=[Severidade.ALTA], nao_avaliadas=["a", "b", "c", "d"])
        ).nivel
        == "grave"
    )


# --- gráficos SVG ----------------------------------------------------------------


def test_grafico_linhas_gera_svg_com_media():
    svg = graficos.grafico_linhas(
        [("P/VP", [("2025-01", 1.0), ("2025-06", 1.2), ("2026-01", 0.9)])],
        linha_media=1.05,
    )
    assert svg.startswith("<svg")
    assert "polyline" in svg
    assert "média" in svg
    # janela curta ganha rótulo de mês no eixo
    assert "jan/25" in svg


def test_grafico_barras_gera_svg_com_rotulos():
    svg = graficos.grafico_barras([("2024", 8.5), ("2025", 9.1)])
    assert svg.startswith("<svg")
    assert svg.count("<rect") == 2
    assert "2024" in svg and "2025" in svg


def test_graficos_vazios_retornam_vazio():
    assert graficos.grafico_linhas([("x", [])]) == ""
    assert graficos.grafico_barras([]) == ""


# --- relatório HTML ---------------------------------------------------------------


def test_gerar_html_completo(con, zip_cvm):
    completo = _completo(con, zip_cvm)
    pagina = relatorio_html.gerar(completo, agora=datetime(2026, 7, 18, 15, 0))
    assert "TSTE11" in pagina
    assert "FUNDO TESTE FII" in pagina
    # selo presente (fundo novo -> histórico insuficiente)
    assert completo.raiox.selo is not None
    assert completo.raiox.selo.rotulo in pagina
    # datas de atualização por fonte
    assert "informes CVM até <b>02/2026</b>" in pagina
    assert "cotação de <b>17/02/2026</b>" in pagina
    assert "18/07/2026 15:00" in pagina
    # gráficos SVG embutidos e disclaimer
    assert pagina.count("<svg") >= 2
    assert "não é recomendação de investimento" in pagina
    # glossário para leigos: todo indicador exibido tem um "?" com explicação
    from fato_relevante.relatorio.glossario import TERMOS

    for linha in completo.raiox.indicadores:
        assert linha.nome in TERMOS, f"indicador sem verbete no glossário: {linha.nome}"
    assert pagina.count('class="ajuda"') >= len(completo.raiox.indicadores)
    assert 'class="dica"' in pagina


def test_calculadoras_prefilled_com_dados_do_fundo(con, zip_cvm):
    completo = _completo(con, zip_cvm)
    pagina = relatorio_html.gerar(completo)
    assert "Uma cota por mês" in pagina
    assert "Projeção de aportes" in pagina
    # pré-preenchidas: preço = última cotação (100.00) e rendimento = dy*vp ajustado
    assert 'id="uc-preco" value="100.00"' in pagina
    assert 'id="uc-rend" value="1.05"' in pagina  # 0.011 * 95.45
    assert "function calcUmaCota" in pagina and "function calcAportes" in pagina
    assert "não promessa de rentabilidade" in pagina


def test_botao_calculadoras_e_ancora(con, zip_cvm):
    completo = _completo(con, zip_cvm)
    pagina = relatorio_html.gerar(completo)
    assert 'href="#calculadoras"' in pagina
    assert 'id="calculadoras"' in pagina


def test_calculadora_retroativa_com_rentabilidade(con, zip_cvm):
    import json

    from fato_relevante.coleta import cvm as cvm_mod

    cvm_mod.carregar_zip(con, zip_cvm(True), "inf_mensal_fii_2026.zip")
    candles = [(f"{ano}-{mes:02d}", 100.0 + i, 100.0 + i) for i, (ano, mes) in enumerate(
        [(2025, m) for m in range(1, 13)] + [(2026, 1), (2026, 2)]
    )]
    armazenamento.gravar_cotacoes(con, "TSTE11", candles, 115.0, "2026-02-17", "2026-02-18")
    armazenamento.gravar_indice(
        con, "CDI", [(f"{a}-{m:02d}", 1.0) for a in (2025, 2026) for m in range(1, 13)], "2026-02-18"
    )
    completo = analise.montar_completo(con, "tste11")
    pagina = relatorio_html.gerar(completo)
    assert "E se eu tivesse investido?" in pagina
    assert "const RETRO = " in pagina
    assert "function calcRetro" in pagina
    # o JSON embutido carrega o % final de cada série por janela
    trecho = pagina.split("const RETRO = ")[1].split(";</script>")[0]
    retro = json.loads(trecho)
    assert "12 meses" in retro
    assert "Fundo" in retro["12 meses"] and "CDI" in retro["12 meses"]


def test_sem_cotacao_nao_mostra_calculadoras(con, zip_cvm):
    cvm.carregar_zip(con, zip_cvm(True), "inf_mensal_fii_2026.zip")
    completo = analise.montar_completo(con, "tste11")
    pagina = relatorio_html.gerar(completo)
    assert "Uma cota por mês" not in pagina


def test_salvar_html_escreve_arquivo(con, zip_cvm, tmp_path):
    completo = _completo(con, zip_cvm)
    caminho = relatorio_html.salvar(completo, tmp_path / "rel")
    assert caminho.name == "TSTE11.html"
    conteudo = caminho.read_text(encoding="utf-8")
    assert conteudo.startswith("<!doctype html>")


def test_cli_html_gera_e_abre(con, zip_cvm, tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from fato_relevante.cli import app
    from fato_relevante.coleta import cotacoes, indices

    _completo(con, zip_cvm)
    monkeypatch.setenv("FATO_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(cotacoes, "garantir_atualizada", lambda con, ticker: None)
    monkeypatch.setattr(indices, "garantir_atualizados", lambda con: None)
    abertos = []
    import webbrowser

    monkeypatch.setattr(webbrowser, "open", lambda url: abertos.append(url))
    resultado = CliRunner().invoke(app, ["analisar", "tste11", "--html"])
    assert resultado.exit_code == 0
    assert (tmp_path / "relatorios" / "TSTE11.html").exists()
    assert len(abertos) == 1
