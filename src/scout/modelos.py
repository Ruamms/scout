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
    codigo: str = ""


@dataclass(frozen=True)
class Selo:
    """Síntese mecânica dos alertas — critérios públicos, nunca veredito."""

    nivel: str  # sem_alertas | leves | atencao | grave | insuficiente
    rotulo: str
    descricao: str
    cor: str  # nome de cor rich / hex para HTML


@dataclass(frozen=True)
class IndicadorLinha:
    """Uma linha da tabela de indicadores, já formatada para exibição."""

    nome: str
    atual: str
    doze_meses: str
    historico: str
    alerta: bool = False
    alerta_motivo: str = ""  # título(s) da(s) red flag(s) que marcaram a linha


@dataclass(frozen=True)
class Imovel:
    """Um imóvel do fundo, do informe trimestral (frações já em %)."""

    nome: str
    area: float | None
    vacancia: float | None       # %
    inadimplencia: float | None  # %
    pct_receita: float | None    # % da receita do fundo


@dataclass(frozen=True)
class FundoIrmao:
    """Outro fundo do mesmo administrador, para o cruzamento do raio-x."""

    ticker: str  # derivado do ISIN; "" quando não derivável
    nome: str
    segmento: str
    anos: float
    selo: Selo | None
    motivos: tuple[str, ...] = ()  # títulos dos alertas que definiram o selo
    taxa: float | None = None  # taxa de administração efetiva, % a.a.


@dataclass(frozen=True)
class RaioX:
    """Resultado completo da análise de um ativo."""

    ticker: str
    nome: str
    cnpj: str
    classificacao: str
    gestao: str
    dados_ate: str
    tipo: str | None = None  # papel/tijolo/híbrido/FoF, estimado pela carteira CVM
    tipo_fonte: str = ""  # composição + competência (tooltip/fonte do tipo)
    cotacao_em: str = ""
    cotado_em_iso: str = ""  # bruto ('AAAA-MM-DD HH:MM') para cálculo de idade no render
    indicadores: list[IndicadorLinha] = field(default_factory=list)
    red_flags: list[RedFlag] = field(default_factory=list)
    sem_alerta: list[str] = field(default_factory=list)
    notas: list[str] = field(default_factory=list)
    imoveis: list[Imovel] = field(default_factory=list)
    imoveis_em: str = ""  # competência do informe trimestral dos imóveis
    imoveis_por_estado: list[tuple[str, float]] = field(default_factory=list)  # (UF, % da área)
    setores_inquilinos: list[tuple[str, float]] = field(default_factory=list)  # (setor, % da receita)
    administrador: str = ""
    fundos_irmaos: list[FundoIrmao] = field(default_factory=list)
    gestora: str = ""  # do cadastro CVM (registro de fundos)
    gestora_e_admin: bool = False  # gestora e administrador são a mesma instituição
    fundos_gestora: list[FundoIrmao] = field(default_factory=list)
    pares: list = field(default_factory=list)          # FundoResumo dos maiores pares do segmento
    pares_media: dict = field(default_factory=dict)    # médias do segmento: dy, pvp, pl, n
    selo: Selo | None = None
    red_flags_avaliadas: bool = True
    exemplo: bool = False
