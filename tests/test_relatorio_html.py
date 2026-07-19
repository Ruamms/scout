from datetime import datetime

import pytest

from scout import analise, armazenamento, redflags
from scout.coleta import cvm
from scout.modelos import RedFlag, Severidade
from scout.relatorio import graficos
from scout.relatorio import html as relatorio_html


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
    # idade do preço visível e com aviso de defasagem (>48h entre 17/02 e 18/07)
    assert "(há 151 dias)" in pagina
    assert "Idade do preço usado" in pagina
    # gráficos SVG embutidos e disclaimer
    assert pagina.count("<svg") >= 2
    assert "não é recomendação de investimento" in pagina
    # glossário para leigos: todo indicador exibido tem um "?" com explicação
    from scout.relatorio.glossario import TERMOS

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

    from scout.coleta import cvm as cvm_mod

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
    assert "Fundo" in retro["12 meses"]["com"] and "CDI" in retro["12 meses"]["com"]
    assert "Fundo" in retro["12 meses"]["sem"]


def test_secao_ia_linka_documentos_originais(con, zip_cvm):
    completo = _completo(con, zip_cvm)
    leitura = {
        "ticker": "TSTE11",
        "modelo": "qwen2.5:14b",
        "gerada_em": "2026-07-18T22:00:00",
        "relatorio": {"id": 123, "data_entrega": "10/07/2026 18:00", "texto": "1. Fato citado. (p. 3)"},
        "fatos": {"ids": [9], "datas": ["05/07/2026"], "texto": "bloco de fatos"},
    }
    pagina = relatorio_html.gerar(completo, leitura=leitura)
    # quem lê pode baixar o documento oficial e conferir cada citação
    assert "downloadDocumento?id=123" in pagina
    assert "baixar o relatório original" in pagina
    assert "downloadDocumento?id=9" in pagina


def test_leitura_ia_explica_jargao_para_leigos():
    texto = "Alocação: 78% em CRI atrelados ao CDI. Novos CRI em análise."
    saida = relatorio_html._texto_ia_para_html(texto)
    # primeira ocorrência ganha tooltip com definição nossa (determinística)
    assert saida.count('class="termo"') == 2  # CRI e CDI, uma vez cada
    assert "Certificado de Recebíveis Imobiliários" in saida
    assert "colada na Selic" in saida
    # definição citando outro termo (Selic, na dica do CDI) não vira tooltip aninhado
    assert '<span class="termo" tabindex="0">Selic' not in saida
    # segunda menção a CRI fica limpa
    assert saida.endswith("Novos CRI em análise.")


def test_secao_ia_explica_fundo_sem_relatorio_gerencial(con, zip_cvm):
    from scout import leituras

    completo = _completo(con, zip_cvm)
    marcador = leituras.montar_sem_relatorio("TSTE11", agora=datetime(2026, 7, 18, 23, 0))
    pagina = relatorio_html.gerar(completo, leitura=marcador)
    # a caixa da IA existe e explica a ausência, em vez de sumir sem aviso
    assert "Leitura por IA" in pagina
    assert "não publicou relatório gerencial" in pagina
    assert "2026-07-18" in pagina

    # com fatos relevantes lidos, eles aparecem mesmo sem relatório gerencial
    com_fatos = leituras.montar_sem_relatorio(
        "TSTE11",
        fatos_meta=[{"id": 120, "data_entrega": "18/06/2026 18:58"}],
        texto_fatos="resumo dos fatos",
        modelo="teste:1b",
        agora=datetime(2026, 7, 18, 23, 0),
    )
    pagina2 = relatorio_html.gerar(completo, leitura=com_fatos)
    assert "não publicou relatório gerencial" in pagina2
    assert "foram lidos pela IA" in pagina2
    assert "resumo dos fatos" in pagina2
    assert "downloadDocumento?id=120" in pagina2


def test_oscilacoes_com_contexto(con, zip_cvm):
    completo = _completo(con, zip_cvm)  # cota 90 -> 100 = +11,1% em fev/26
    assert [osc.mes for osc in completo.oscilacoes] == ["2026-02"]
    assert completo.oscilacoes[0].variacao == pytest.approx(11.11, abs=0.01)

    leitura = {
        "ticker": "TSTE11",
        "modelo": "teste:1b",
        "gerada_em": "2026-07-18T22:00:00",
        "relatorio": {"id": 1, "data_entrega": "10/07/2026 18:00", "texto": "leitura"},
        "fatos": {"ids": [77], "datas": ["10/02/2026"], "texto": "bloco"},
    }
    pagina = relatorio_html.gerar(completo, leitura=leitura)
    assert "Oscilações com contexto" in pagina
    assert "fev/26" in pagina
    # fato relevante do mesmo mês vira evento do período, com link para o original
    assert "fato relevante publicado em 10/02/2026" in pagina
    assert "downloadDocumento?id=77" in pagina
    # a nota nega causalidade com todas as letras
    assert "não</b> afirmação de causa" in pagina


def test_oscilacoes_sem_sustos(con, zip_cvm):
    cvm.carregar_zip(con, zip_cvm(True), "inf_mensal_fii_2026.zip")
    armazenamento.gravar_cotacoes(
        con,
        "TSTE11",
        [("2026-01", 100.0, 100.0), ("2026-02", 105.0, 105.0)],
        105.0,
        "2026-02-17",
        "2026-02-18",
    )
    completo = analise.montar_completo(con, "tste11")
    assert completo.oscilacoes == []
    pagina = relatorio_html.gerar(completo)
    assert "Oscilações com contexto" in pagina
    assert "sem sustos" in pagina


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

    from scout.cli import app
    from scout.coleta import cotacoes, indices

    _completo(con, zip_cvm)
    monkeypatch.setenv("SCOUT_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(cotacoes, "garantir_atualizada", lambda con, ticker: None)
    monkeypatch.setattr(indices, "garantir_atualizados", lambda con: None)
    abertos = []
    import webbrowser

    monkeypatch.setattr(webbrowser, "open", lambda url: abertos.append(url))
    resultado = CliRunner().invoke(app, ["analisar", "tste11", "--html"])
    assert resultado.exit_code == 0
    assert (tmp_path / "relatorios" / "TSTE11.html").exists()
    assert len(abertos) == 1
