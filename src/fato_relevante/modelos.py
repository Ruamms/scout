"""Modelos de domínio do raio-x.

Estes dataclasses são o contrato entre as camadas: a coleta e os
indicadores produzem um ``RaioX``; os renderizadores (terminal, HTML)
apenas o exibem. A futura camada de IA recebe o mesmo objeto pronto.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Severidade(str, Enum):
    ALTA = "ALTA"
    MEDIA = "MÉDIA"
    BAIXA = "BAIXA"


@dataclass(frozen=True)
class RedFlag:
    """Um alerta disparado por uma regra determinística.

    Toda red flag carrega a conta que a disparou (``evidencia``) e a
    ``fonte`` do dado — sem isso ela não pode existir.
    """

    severidade: Severidade
    titulo: str
    fato: str
    evidencia: str
    fonte: str


@dataclass(frozen=True)
class IndicadorLinha:
    """Uma linha da tabela de indicadores, já formatada para exibição."""

    nome: str
    atual: str
    doze_meses: str
    historico: str
    alerta: bool = False


@dataclass(frozen=True)
class RaioX:
    """Resultado completo da análise de um ativo."""

    ticker: str
    nome: str
    cnpj: str
    classificacao: str
    gestao: str
    dados_ate: str
    indicadores: list[IndicadorLinha] = field(default_factory=list)
    red_flags: list[RedFlag] = field(default_factory=list)
    sem_alerta: list[str] = field(default_factory=list)
    exemplo: bool = False
