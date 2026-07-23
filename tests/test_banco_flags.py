"""R2 Renda Fixa — red flags de emissor (benchmark real: Banco Master pego
com MÉDIA em dez/2024 e ALTA em mar/2025, meses antes da liquidação de
nov/2025; Itaú/BB/Bradesco/ABC = zero flags)."""

from scout import banco_flags
from scout.modelos import Severidade


def _tri(anomes, basileia=15.0, lucro=100.0, captacoes=1000.0, carteira=800.0):
    return {"anomes": anomes, "basileia": basileia, "lucro": lucro,
            "captacoes": captacoes, "carteira": carteira}


def test_banco_saudavel_zero_flags():
    serie = [_tri(a) for a in (202412, 202503, 202506, 202512, 202603)]
    r = banco_flags.avaliar(serie)
    assert r.flags == [] and len(r.aprovadas) == 4


def test_basileia_no_piso_e_alta_caso_master():
    # Master operou colado em 10,5% nos trimestres pré-liquidação
    r = banco_flags.avaliar([_tri(202503, basileia=10.53)])
    assert any(f.severidade == Severidade.ALTA and "Basileia" in f.titulo for f in r.flags)
    r2 = banco_flags.avaliar([_tri(202503, basileia=11.5)])
    assert any(f.severidade == Severidade.MEDIA and "colchão fino" in f.titulo for f in r2.flags)


def test_prejuizo_recorrente_calibrado_pelo_colchao():
    # 2 anos fechados no vermelho SEM colchão -> ALTA (padrão Master)
    serie = [_tri(202412, lucro=-50, basileia=12.0), _tri(202512, lucro=-30, basileia=12.0),
             _tri(202603, lucro=10, basileia=12.0)]
    r = banco_flags.avaliar(serie)
    assert any(f.severidade == Severidade.ALTA and "recorrente" in f.titulo for f in r.flags)
    # mesmos prejuízos com Basileia de atacadista (30%) -> MÉDIA factual (caso Sumitomo)
    serie2 = [_tri(202412, lucro=-50, basileia=30.0), _tri(202512, lucro=-30, basileia=30.0),
              _tri(202603, lucro=10, basileia=30.0)]
    r2 = banco_flags.avaliar(serie2)
    flag = next(f for f in r2.flags if "recorrente" in f.titulo)
    assert flag.severidade == Severidade.MEDIA


def test_aspirador_de_cdb():
    serie = [_tri(202506, captacoes=1000, carteira=800),
             _tri(202606, captacoes=1600, carteira=880)]  # +60% capt, +10% carteira
    r = banco_flags.avaliar(serie)
    assert any("Captações" in f.titulo for f in r.flags)
    # crescendo junto (caso Master: capt +97% MAS carteira +96%) não dispara
    serie2 = [_tri(202506, captacoes=1000, carteira=800),
              _tri(202606, captacoes=1970, carteira=1570)]
    r2 = banco_flags.avaliar(serie2)
    assert not any("Captações" in f.titulo for f in r2.flags)


def test_basileia_derretendo():
    serie = [_tri(202506, basileia=17.0), _tri(202606, basileia=13.5)]
    r = banco_flags.avaliar(serie)
    assert any("caiu" in f.titulo for f in r.flags)


def test_sem_dado_e_nao_avaliada():
    r = banco_flags.avaliar([])
    assert r.flags == [] and r.aprovadas == [] and len(r.nao_avaliadas) == 4
