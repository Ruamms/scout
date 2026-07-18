import pytest

from fato_relevante import analise, armazenamento, redflags
from fato_relevante.coleta import cvm
from fato_relevante.redflags import distribuicao, distribuicao_exata, fundo_novo, vacancia
from fato_relevante.redflags.contexto import Contexto


@pytest.mark.parametrize("novo_schema", [True, False], ids=["pos_rcvm175", "pre_rcvm175"])
def test_carga_trimestral(con, zip_trimestral, novo_schema):
    imoveis, resultados = cvm.carregar_zip_trimestral(
        con, zip_trimestral(novo_schema), "inf_trimestral_fii_2026.zip"
    )
    assert (imoveis, resultados) == (2, 1)
    linhas = armazenamento.imoveis_atuais(con, "11.111.111/0001-11")
    assert linhas[0]["nome"] == "GALPAO A"  # maior % receita primeiro
    assert linhas[0]["vacancia"] == 0.10
    assert linhas[1]["nome"] == "Rua Y, 2"  # sem nome -> endereço como fallback
    resultado = armazenamento.serie_resultados(con, "11.111.111/0001-11")[0]
    assert resultado["resultado_financeiro"] == 100000
    assert resultado["rendimentos_declarados"] == 90000


# --- contexto: vacância ponderada -----------------------------------------------


def _imoveis(*pares):
    return [
        {"vacancia": v, "area": a, "inadimplencia": None, "pct_receita": None, "nome": "x"}
        for v, a in pares
    ]


def test_vacancia_ponderada_por_area():
    ctx = Contexto(serie=[], imoveis_atuais=_imoveis((0.10, 1000), (0.50, 500)))
    # (0.10*1000 + 0.50*500) / 1500 = 0.2333 -> 23,33%
    assert ctx.vacancia_atual() == pytest.approx(23.33, abs=0.01)


def test_vacancia_descarta_lixo():
    ctx = Contexto(serie=[], imoveis_atuais=_imoveis((1.5, 1000), (-0.2, 100)))
    assert ctx.vacancia_atual() is None


# --- regras novas ----------------------------------------------------------------


def test_vacancia_alta_dispara():
    ctx = Contexto(serie=[], imoveis_atuais=_imoveis((0.40, 1000)))
    flag = vacancia.avaliar(ctx)
    assert flag is not None
    assert flag.severidade.name == "ALTA"


def test_vacancia_moderada_e_media():
    ctx = Contexto(serie=[], imoveis_atuais=_imoveis((0.20, 1000)))
    assert vacancia.avaliar(ctx).severidade.name == "MEDIA"


def test_vacancia_baixa_aprova():
    ctx = Contexto(serie=[], imoveis_atuais=_imoveis((0.05, 1000)))
    assert vacancia.avaliar(ctx) is None


def test_fundo_novo_dispara_e_aprova():
    serie_curta = [{"competencia": f"2026-{m:02d}"} for m in range(1, 7)]
    flag = fundo_novo.avaliar(Contexto(serie=serie_curta))
    assert flag is not None and "6 meses" in flag.fato
    serie_longa = [{"competencia": "x"}] * 30
    assert fundo_novo.avaliar(Contexto(serie=serie_longa)) is None


def _resultados(res, rend, trimestres=4):
    return [
        {"resultado_financeiro": res, "rendimentos_declarados": rend}
        for _ in range(trimestres)
    ]


def test_distribuicao_exata_negativo_e_alta():
    ctx = Contexto(serie=[], resultados=_resultados(-1000.0, 5000.0))
    flag = distribuicao_exata.avaliar(ctx)
    assert flag is not None
    assert flag.severidade.name == "ALTA"
    assert "NEGATIVO" in flag.fato


def test_distribuicao_exata_dentro_do_resultado_aprova():
    ctx = Contexto(serie=[], resultados=_resultados(100000.0, 95000.0))
    assert distribuicao_exata.aplicavel(ctx)
    assert distribuicao_exata.avaliar(ctx) is None


def test_distribuicao_exata_precisa_de_4_trimestres():
    ctx = Contexto(serie=[], resultados=_resultados(100000.0, 95000.0, trimestres=3))
    assert not distribuicao_exata.aplicavel(ctx)


def test_proxy_suprimida_quando_exata_roda():
    ctx = Contexto(serie=[], resultados=_resultados(100000.0, 95000.0))
    resultado = redflags.avaliar(ctx)
    # o tema distribuição não aparece como "não avaliada" nem duplicado
    assert distribuicao.NOME not in resultado.nao_avaliadas
    assert distribuicao_exata.OK in resultado.aprovadas


# --- integração ------------------------------------------------------------------


def test_raio_x_com_imoveis_e_vacancia(con, zip_cvm, zip_trimestral):
    cvm.carregar_zip(con, zip_cvm(True), "inf_mensal_fii_2026.zip")
    cvm.carregar_zip_trimestral(con, zip_trimestral(), "inf_trimestral_fii_2026.zip")
    raiox = analise.montar_raio_x(con, "tste11")
    assert len(raiox.imoveis) == 2
    assert raiox.imoveis[0].nome == "GALPAO A"
    assert raiox.imoveis[0].vacancia == pytest.approx(10.0)
    assert raiox.imoveis_em == "03/2026"
    nomes = [linha.nome for linha in raiox.indicadores]
    assert "Vacância" in nomes
    # vacância ponderada: (0.10*1000 + 0.50*500)/1500 = 23,33% -> regra MÉDIA dispara
    assert any(flag.codigo == "vacancia" for flag in raiox.red_flags)


def test_pct_receita_em_fracao_e_normalizado(con, zip_cvm):
    # fundo que declara % da receita como fração (soma ~1): 0.6 + 0.4
    import io
    import zipfile

    imovel = (
        "CNPJ_Fundo_Classe;Data_Referencia;Versao;Nome_Imovel;Area;"
        "Percentual_Vacancia;Percentual_Inadimplencia;Percentual_Receitas_FII\n"
        "11.111.111/0001-11;2026-03-01;1;A;1000;0.1;0;0.6\n"
        "11.111.111/0001-11;2026-03-01;1;B;500;0.1;0;0.4\n"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("inf_trimestral_fii_imovel_2026.csv", imovel.encode("latin-1"))
        zf.writestr(
            "inf_trimestral_fii_resultado_contabil_financeiro_2026.csv",
            "CNPJ_Fundo_Classe;Data_Referencia;Versao\n".encode("latin-1"),
        )
    cvm.carregar_zip(con, zip_cvm(True), "inf_mensal_fii_2026.zip")
    cvm.carregar_zip_trimestral(con, buffer.getvalue(), "inf_trimestral_fii_2026.zip")
    raiox = analise.montar_raio_x(con, "tste11")
    assert raiox.imoveis[0].pct_receita == pytest.approx(60.0)
    assert raiox.imoveis[1].pct_receita == pytest.approx(40.0)


def test_html_botao_ver_todos_imoveis(con, zip_cvm, zip_trimestral):
    from fato_relevante.relatorio import html as relatorio_html
    from fato_relevante.modelos import Imovel
    import dataclasses

    cvm.carregar_zip(con, zip_cvm(True), "inf_mensal_fii_2026.zip")
    cvm.carregar_zip_trimestral(con, zip_trimestral(), "inf_trimestral_fii_2026.zip")
    completo = analise.montar_completo(con, "tste11")
    # infla a lista para além do limite de 10
    muitos = [
        Imovel(nome=f"IM {i}", area=100.0, vacancia=1.0, inadimplencia=0.0, pct_receita=1.0)
        for i in range(15)
    ]
    raiox = dataclasses.replace(completo.raiox, imoveis=muitos)
    completo = dataclasses.replace(completo, raiox=raiox)
    pagina = relatorio_html.gerar(completo)
    assert "ver todos os 15 imóveis" in pagina
    assert pagina.count('class="imovel-extra" hidden') == 5
    assert "function verMais" in pagina


def test_indicador_com_alerta_traz_motivo_no_tooltip(con, zip_cvm, zip_trimestral):
    from fato_relevante.relatorio import html as relatorio_html

    cvm.carregar_zip(con, zip_cvm(True), "inf_mensal_fii_2026.zip")
    cvm.carregar_zip_trimestral(con, zip_trimestral(), "inf_trimestral_fii_2026.zip")
    raiox = analise.montar_raio_x(con, "tste11")
    vacancia_linha = next(l for l in raiox.indicadores if l.nome == "Vacância")
    assert vacancia_linha.alerta is True
    assert "Vacância física alta" in vacancia_linha.alerta_motivo
    completo = analise.montar_completo(con, "tste11")
    pagina = relatorio_html.gerar(completo)
    assert 'title="Alerta: Vacância física alta"' in pagina


def test_html_com_secao_imoveis_e_grafico_vacancia(con, zip_cvm, zip_trimestral):
    from fato_relevante.relatorio import html as relatorio_html

    cvm.carregar_zip(con, zip_cvm(True), "inf_mensal_fii_2026.zip")
    cvm.carregar_zip_trimestral(con, zip_trimestral(), "inf_trimestral_fii_2026.zip")
    completo = analise.montar_completo(con, "tste11")
    assert completo.graficos.vacancia == [("2026-03", pytest.approx(23.33, abs=0.01))]
    pagina = relatorio_html.gerar(completo)
    assert "Imóveis (2)" in pagina
    assert "GALPAO A" in pagina
    assert "Vacância (%)" in pagina
