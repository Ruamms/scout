"""Tipo do FII derivado da composição da carteira oficial (informe mensal da
CVM, tabela ativo_passivo): papel / tijolo / híbrido / fundo de fundos.

É uma classificação ESTIMADA a partir de fatos públicos — nunca um rótulo
editorial. A regra pesa só os três baldes imobiliários (tijolo, papel, fof),
ignorando caixa e aplicações de liquidez, que não definem a natureza do fundo.
Limiares confirmados com o mantenedor.
"""

from __future__ import annotations

PAPEL = "Papel"
TIJOLO = "Tijolo"
HIBRIDO = "Híbrido"
FOF = "Fundo de Fundos"

# ordem de exibição dos chips/filtros (relevância no mercado)
ORDEM = (TIJOLO, PAPEL, HIBRIDO, FOF)


def classificar(tijolo: float, papel: float, fof: float) -> str | None:
    """Tipo do fundo a partir dos R$ em cada balde, ou None quando não há base
    imobiliária para decidir (fundo só de caixa/liquidez, ou sem o informe).

    Percentuais são sobre a base = tijolo + papel + fof:
    - cotas de outros fundos (fof) ≥ 50% ....... Fundo de Fundos
    - tijolo ≥ 70% ............................. Tijolo
    - papel ≥ 70% ............................. Papel
    - tijolo e papel ambos ≥ 20% .............. Híbrido
    - senão ................................... o maior entre tijolo e papel
    """
    base = tijolo + papel + fof
    if base <= 0:
        return None
    f_tijolo, f_papel, f_fof = tijolo / base, papel / base, fof / base
    if f_fof >= 0.50:
        return FOF
    if f_tijolo >= 0.70:
        return TIJOLO
    if f_papel >= 0.70:
        return PAPEL
    if f_tijolo >= 0.20 and f_papel >= 0.20:
        return HIBRIDO
    return TIJOLO if tijolo >= papel else PAPEL
