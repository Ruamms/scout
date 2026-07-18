"""Motor de red flags: roda todas as regras sobre o contexto do fundo.

Cada regra é um módulo com `CODIGO`, `NOME`, `OK`, `aplicavel(ctx)` e
`avaliar(ctx) -> RedFlag | None`. O motor separa três destinos:
alertas disparados, regras aprovadas e regras não avaliadas por falta
de dado/histórico — os três aparecem na tela, porque "não olhei" é
diferente de "olhei e está ok".
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..modelos import RedFlag, Selo, Severidade
from . import cotistas, diluicao, distribuicao, pvp_faixa, rendimento, vp_queda
from .contexto import Contexto

REGRAS = [distribuicao, diluicao, vp_queda, cotistas, pvp_faixa, rendimento]

_ORDEM_SEVERIDADE = {Severidade.ALTA: 0, Severidade.MEDIA: 1, Severidade.BAIXA: 2}


@dataclass
class Resultado:
    flags: list[RedFlag] = field(default_factory=list)
    aprovadas: list[str] = field(default_factory=list)
    nao_avaliadas: list[str] = field(default_factory=list)


def avaliar(ctx: Contexto) -> Resultado:
    resultado = Resultado()
    for regra in REGRAS:
        if not regra.aplicavel(ctx):
            resultado.nao_avaliadas.append(regra.NOME)
            continue
        flag = regra.avaliar(ctx)
        if flag is None:
            resultado.aprovadas.append(regra.OK)
        else:
            resultado.flags.append(flag)
    resultado.flags.sort(key=lambda flag: _ORDEM_SEVERIDADE[flag.severidade])
    return resultado


_MAX_NAO_AVALIADAS_PARA_SINTESE = 2


def selo(resultado: Resultado) -> Selo:
    """Síntese mecânica dos alertas. Precedência: grave > atenção >
    histórico insuficiente > leves > sem alertas."""
    severidades = {flag.severidade for flag in resultado.flags}
    if Severidade.ALTA in severidades:
        return Selo("grave", "Alerta grave", "Ao menos um alerta de severidade alta disparou", "red")
    if Severidade.MEDIA in severidades:
        return Selo("atencao", "Atenção", "Ao menos um alerta de severidade média disparou", "dark_orange")
    if len(resultado.nao_avaliadas) > _MAX_NAO_AVALIADAS_PARA_SINTESE:
        return Selo(
            "insuficiente",
            "Histórico insuficiente",
            f"{len(resultado.nao_avaliadas)} de {len(REGRAS)} regras sem dado/histórico para avaliar",
            "grey62",
        )
    if Severidade.BAIXA in severidades:
        return Selo("leves", "Alertas leves", "Apenas alertas de severidade baixa", "yellow")
    return Selo("sem_alertas", "Sem alertas", "Todas as regras avaliadas; nenhuma disparou", "green")
