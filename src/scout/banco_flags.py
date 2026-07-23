"""Red flags de BANCO emissor de CDB (R2 da Renda Fixa) — determinísticas.

Matéria-prima: série trimestral do IF.data (`bancos_tri`). O padrão que estas
regras perseguem é o clássico "banco estressado aspirando CDB de varejo com
taxa gorda" — os sinais eram públicos trimestres antes nas liquidações reais.
Selo de emissor SÓ liga após o benchmark retroativo passar (gate do dono,
mesma regra do A3 das ações). "Sem dado = não avaliada", nunca aprovação.

Réguas (calibradas no benchmark):
- Basileia: mínimo regulatório de PR/RWA é 8% + adicional de conservação 2,5%
  (≈10,5% para não ter restrição). <11% = ALTA (no requerimento ou abaixo — o
  Banco Master operou colado em 10,5% nos trimestres pré-liquidação); <12% =
  MÉDIA (colchão fino para um captador de varejo).
- Prejuízo recorrente: o "Lucro Líquido" do IF.data é ACUMULADO NO ANO — o
  fechamento (dezembro) é o resultado anual; a regra conta anos fechados
  negativos + o acumulado corrente. ALTA só com Basileia < 14% (prejuízo com
  colchão gigante é fato MÉDIO, não o padrão Master).
- Aspirador de CDB: captações crescendo forte (YoY) com a carteira de crédito
  crescendo muito menos — captar sem emprestar é rolagem/queima, não negócio.
- Basileia derretendo: queda relevante em 4 trimestres.
"""

from __future__ import annotations

from . import formato, redflags
from .modelos import RedFlag, Severidade

_FONTE = "BCB — IF.data (conglomerado prudencial, dados públicos trimestrais)"


def _pct(v: float) -> str:
    return formato.percentual(v)


def avaliar(serie: list[dict]) -> redflags.Resultado:
    """`serie` = linhas de bancos_tri (asc por anomes) de UM emissor."""
    resultado = redflags.Resultado()
    serie = sorted(serie, key=lambda l: l["anomes"])
    atual = serie[-1] if serie else None

    # --- 1. Basileia (PR/RWA) -------------------------------------------------
    nome = "Basileia baixa"
    if atual is None or atual.get("basileia") is None:
        resultado.nao_avaliadas.append(nome)
    else:
        basileia = atual["basileia"]
        trimestre = atual["anomes"]
        if basileia < 11:
            resultado.flags.append(RedFlag(
                severidade=Severidade.ALTA,
                titulo=f"Basileia de {_pct(basileia)} — abaixo do requerimento com adicionais",
                fato=(
                    "O índice de Basileia (capital ÷ ativos ponderados pelo risco) está colado ou "
                    "abaixo dos ~10,5% exigidos com adicionais — colchão zero. É o que protege quem "
                    "empresta ao banco — inclusive quem compra CDB acima do teto do FGC."
                ),
                evidencia=f"PR/RWA = {_pct(basileia)} em {trimestre} (mínimo 8% + adicional 2,5%)",
                fonte=_FONTE,
            ))
        elif basileia < 12:
            resultado.flags.append(RedFlag(
                severidade=Severidade.MEDIA,
                titulo=f"Basileia de {_pct(basileia)} — colchão fino",
                fato=(
                    "O índice de Basileia está acima do mínimo, mas com pouco colchão para um "
                    "captador de varejo — uma perda relevante de crédito consome esse espaço rápido."
                ),
                evidencia=f"PR/RWA = {_pct(basileia)} em {trimestre}",
                fonte=_FONTE,
            ))
        else:
            resultado.aprovadas.append(f"Basileia com folga ({_pct(basileia)}) no último trimestre")

    # --- 2. Prejuízo recorrente -----------------------------------------------
    nome = "Prejuízo recorrente"
    fechamentos = [l for l in serie if l["anomes"] % 100 == 12 and l.get("lucro") is not None][-3:]
    if not fechamentos or atual is None or atual.get("lucro") is None:
        resultado.nao_avaliadas.append(nome)
    else:
        anos_negativos = [l["anomes"] // 100 for l in fechamentos if l["lucro"] < 0]
        corrente_negativo = atual["anomes"] % 100 != 12 and atual["lucro"] < 0
        if len(anos_negativos) >= 2 or (anos_negativos and corrente_negativo):
            # calibração do benchmark: prejuízo recorrente COM colchão gigante
            # (atacadistas tipo Sumitomo, Basileia ~30%) não é o padrão Master —
            # só vira ALTA quando o capital não tem gordura para absorver
            basileia_atual = atual.get("basileia")
            grave = basileia_atual is None or basileia_atual < 14
            resultado.flags.append(RedFlag(
                severidade=Severidade.ALTA if grave else Severidade.MEDIA,
                titulo="Prejuízo recorrente",
                fato=(
                    "O banco fechou no vermelho em anos seguidos — prejuízo consome o capital que "
                    "sustenta a Basileia, e banco que não gera resultado depende de captar cada vez mais."
                ),
                evidencia=(
                    f"anos fechados no prejuízo: {', '.join(map(str, anos_negativos)) or '—'}"
                    + (f" · acumulado de {atual['anomes']} também negativo ({formato.moeda_compacta(atual['lucro'])})"
                       if corrente_negativo else "")
                ),
                fonte=_FONTE,
            ))
        elif anos_negativos or corrente_negativo:
            referencia = f"ano {anos_negativos[0]}" if anos_negativos else f"acumulado de {atual['anomes']}"
            resultado.flags.append(RedFlag(
                severidade=Severidade.MEDIA,
                titulo="Prejuízo recente",
                fato="Resultado negativo recente — um ano isolado acontece; a recorrência é o alarme.",
                evidencia=f"prejuízo no {referencia}",
                fonte=_FONTE,
            ))
        else:
            resultado.aprovadas.append("Sem prejuízo nos últimos anos fechados nem no acumulado corrente")

    # --- 3. Aspirador de CDB (captação >> carteira) ----------------------------
    nome = "Captação crescendo muito acima da carteira"
    homologo = next(
        (l for l in serie if atual and l["anomes"] == atual["anomes"] - 100), None
    )
    if (
        atual is None or homologo is None
        or not homologo.get("captacoes") or atual.get("captacoes") is None
        or not homologo.get("carteira") or atual.get("carteira") is None
    ):
        resultado.nao_avaliadas.append(nome)
    else:
        cresc_capt = 100 * (atual["captacoes"] / homologo["captacoes"] - 1)
        cresc_cart = 100 * (atual["carteira"] / homologo["carteira"] - 1)
        if cresc_capt > 40 and cresc_cart < cresc_capt / 2:
            resultado.flags.append(RedFlag(
                severidade=Severidade.MEDIA,
                titulo=f"Captações +{_pct(cresc_capt)} em 12 meses, carteira só +{_pct(cresc_cart)}",
                fato=(
                    "O banco está captando muito mais rápido do que empresta. Captar caro sem "
                    "carteira que pague é o padrão clássico de rolagem — quem financia é quem "
                    "compra o CDB."
                ),
                evidencia=(
                    f"captações {formato.moeda_compacta(homologo['captacoes'])} → "
                    f"{formato.moeda_compacta(atual['captacoes'])} · carteira "
                    f"{formato.moeda_compacta(homologo['carteira'])} → {formato.moeda_compacta(atual['carteira'])}"
                ),
                fonte=_FONTE,
            ))
        else:
            resultado.aprovadas.append("Captações e carteira de crédito crescendo em ritmo compatível")

    # --- 4. Basileia derretendo -----------------------------------------------
    nome = "Basileia em queda rápida"
    ha_um_ano = next(
        (l for l in serie if atual and l["anomes"] == atual["anomes"] - 100), None
    )
    if (
        atual is None or ha_um_ano is None
        or atual.get("basileia") is None or ha_um_ano.get("basileia") is None
    ):
        resultado.nao_avaliadas.append(nome)
    else:
        queda = ha_um_ano["basileia"] - atual["basileia"]
        if queda >= 3:
            resultado.flags.append(RedFlag(
                severidade=Severidade.MEDIA,
                titulo=f"Basileia caiu {queda:.1f} p.p. em 12 meses",
                fato=(
                    "O colchão de capital está derretendo rápido — prejuízo, crescimento de risco "
                    "ou ambos. A direção importa tanto quanto o nível."
                ),
                evidencia=f"{_pct(ha_um_ano['basileia'])} ({ha_um_ano['anomes']}) → {_pct(atual['basileia'])} ({atual['anomes']})",
                fonte=_FONTE,
            ))
        else:
            resultado.aprovadas.append("Basileia estável nos últimos 12 meses")

    resultado.flags.sort(
        key=lambda f: {Severidade.ALTA: 0, Severidade.MEDIA: 1, Severidade.BAIXA: 2}[f.severidade]
    )
    return resultado
