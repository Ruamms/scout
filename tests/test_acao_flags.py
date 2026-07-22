"""A3 — red flags societárias de ação (regras validadas no benchmark real:
Oi 2016 = Negativa de Opinião; IRB 2019 = 324d de atraso + versão 5;
Americanas 2022 = Negativa + 230d; WEG/Itaú/Petrobras 2024 = zero flags)."""

from datetime import date

from scout import acao_flags
from scout.modelos import Severidade


def _meta(ano, **kw):
    base = {"ano": ano, "dt_receb": f"{ano + 1}-02-20", "versao": 1,
            "acoes_total": 1_000_000.0, "acoes_tesouro": 0.0,
            "parecer_tipo": "Sem Ressalva", "parecer_continuidade": 0, "parecer_trecho": None}
    base.update(kw)
    return base


def _dados(**kw):
    base = {
        "metas": [_meta(2023), _meta(2024)],
        "balancos": [{"ano": 2023, "lucro_liquido": 100e6}, {"ano": 2024, "lucro_liquido": 120e6}],
        "proventos_ano_por_ticker": {"TSTA4": {2024: 1.5}},
        "auditores": [{"auditor": "KPMG", "inicio": "2019-01-01", "fim": None}],
    }
    base.update(kw)
    return base


def test_empresa_saudavel_zero_flags():
    r = acao_flags.avaliar(_dados(), hoje=date(2025, 7, 1))
    assert r.flags == []
    assert len(r.aprovadas) == 6  # todas as regras rodaram e passaram


def test_parecer_adverso_e_alta():
    dados = _dados(metas=[_meta(2023), _meta(2024, parecer_tipo="Negativa de Opinião")])
    r = acao_flags.avaliar(dados, hoje=date(2025, 7, 1))
    assert any("Negativa de Opinião" in f.titulo and f.severidade == Severidade.ALTA for f in r.flags)


def test_ressalva_e_media_e_continuidade_sobe_pra_alta():
    dados = _dados(metas=[_meta(2024, parecer_tipo="Com Ressalva")])
    r = acao_flags.avaliar(dados, hoje=date(2025, 7, 1))
    assert any(f.severidade == Severidade.MEDIA and "Ressalva" in f.titulo for f in r.flags)
    dados = _dados(metas=[_meta(2024, parecer_tipo="Sem Ressalva", parecer_continuidade=1)])
    r = acao_flags.avaliar(dados, hoje=date(2025, 7, 1))
    assert any(f.severidade == Severidade.ALTA and "continuidade" in f.titulo for f in r.flags)


def test_atraso_na_entrega_gradua_por_dias():
    dados = _dados(metas=[_meta(2024, dt_receb="2025-04-20")])  # 20 dias
    r = acao_flags.avaliar(dados, hoje=date(2025, 7, 1))
    assert any("dias após o prazo" in f.titulo and f.severidade == Severidade.MEDIA for f in r.flags)
    dados = _dados(metas=[_meta(2024, dt_receb="2025-11-16")])  # 230 dias (Americanas)
    r = acao_flags.avaliar(dados, hoje=date(2026, 1, 1))
    assert any("dias após o prazo" in f.titulo and f.severidade == Severidade.ALTA for f in r.flags)


def test_reapresentacao_dispara():
    dados = _dados(metas=[_meta(2024, versao=5)])  # IRB 2019 foi versão 5
    r = acao_flags.avaliar(dados, hoje=date(2025, 7, 1))
    assert any("reapresentado" in f.titulo.lower() for f in r.flags)


def test_diluicao_por_emissao():
    dados = _dados(metas=[_meta(2023, acoes_total=1_000_000.0), _meta(2024, acoes_total=1_400_000.0)])
    r = acao_flags.avaliar(dados, hoje=date(2025, 7, 1))
    assert any("Base de ações cresceu" in f.titulo for f in r.flags)


def test_diluicao_salvaguardas_contra_falso_positivo():
    # unidade inconsistente (mil ↔ unidade, caso RAPT real): razão implausível NÃO vira flag
    dados = _dados(metas=[_meta(2023, acoes_total=329_331.0), _meta(2024, acoes_total=349_724_671.0)])
    r = acao_flags.avaliar(dados, hoje=date(2025, 7, 1))
    assert not any("Base de ações" in f.titulo for f in r.flags)
    assert any("unidade inconsistente" in n for n in r.nao_avaliadas)
    # desdobramento entre os exercícios (caso VIVT real): comparação crua invalidada
    dados = _dados(
        metas=[_meta(2023, acoes_total=1_650_000_000.0), _meta(2024, acoes_total=3_230_000_000.0)],
        eventos=[{"data": "2024-06-10", "label": "DESDOBRAMENTO", "fator": 100.0}],
    )
    r = acao_flags.avaliar(dados, hoje=date(2025, 7, 1))
    assert not any("Base de ações" in f.titulo for f in r.flags)
    assert any("evento societário" in n for n in r.nao_avaliadas)


def test_proventos_em_ano_de_prejuizo():
    dados = _dados(
        balancos=[{"ano": 2024, "lucro_liquido": -50e6}],
        proventos_ano_por_ticker={"TSTA4": {2024: 2.0}},
    )
    r = acao_flags.avaliar(dados, hoje=date(2025, 7, 1))
    assert any("prejuízo" in f.titulo for f in r.flags)


def test_troca_frequente_de_auditor():
    dados = _dados(auditores=[
        {"auditor": "KPMG", "inicio": "2021-05-01", "fim": "2022-12-31"},
        {"auditor": "EY", "inicio": "2023-01-01", "fim": "2024-06-30"},
        {"auditor": "GRANT THORNTON", "inicio": "2024-07-01", "fim": None},
    ])
    r = acao_flags.avaliar(dados, hoje=date(2025, 7, 1))
    assert any("auditores diferentes" in f.titulo for f in r.flags)


def test_trecho_da_continuidade_e_a_frase_certa():
    """Regressão (caso BRKM3 real): a evidência da flag de continuidade citava a
    frase da OPINIÃO ('apresentam adequadamente...'), que contradiz o alerta. O
    trecho tem que ser a frase da própria incerteza de continuidade."""
    from scout import parecer

    texto = (
        "Opinião sobre as demonstrações financeiras. Em nossa opinião, as demonstrações "
        "financeiras acima referidas apresentam adequadamente, em todos os aspectos "
        "relevantes, a posição patrimonial e financeira da Companhia. "
        "Incerteza relevante relacionada com a continuidade operacional. Chamamos a "
        "atenção para a Nota 1, que indica que a Companhia incorreu no prejuízo de "
        "R$ 9.880 milhões no exercício."
    )
    resultado = parecer.classificar(texto)
    assert resultado["continuidade"] is True
    trecho = parecer.trecho_continuidade(texto)
    assert "continuidade operacional" in trecho
    assert "apresentam adequadamente" not in trecho  # a frase da opinião NÃO é evidência disso


def test_sem_dado_e_nao_avaliada_nunca_aprovacao():
    r = acao_flags.avaliar({"metas": [], "balancos": [], "auditores": [],
                            "proventos_ano_por_ticker": {}}, hoje=date(2025, 7, 1))
    assert r.flags == [] and r.aprovadas == []
    assert len(r.nao_avaliadas) == 6
