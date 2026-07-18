"""Gráficos SVG gerados em Python puro (sem lib JS, sem dependência).

O relatório HTML precisa ser auto-contido e o executável precisa
continuar leve — então os gráficos são SVG desenhado à mão: linhas,
barras, grade e rótulos. O suficiente para contar a história do dado.
"""

from __future__ import annotations

from collections.abc import Callable

from .. import formato

LARGURA = 860
ALTURA = 300
MARGEM_ESQ = 74
MARGEM_DIR = 16
MARGEM_TOPO = 14
MARGEM_BAIXO = 34

CORES = ("#5eead4", "#f59e0b", "#a78bfa")
COR_GRADE = "#2a3441"
COR_TEXTO = "#8b98a9"
COR_MEDIA = "#f472b6"

Formatador = Callable[[float], str]
Ponto = tuple[str, float]


def grafico_linhas(
    series: list[tuple[str, list[Ponto]]],
    formatador: Formatador | None = None,
    linha_media: float | None = None,
    rotulo_media: str = "média",
) -> str:
    """Gráfico de linhas; `series` = [(nome, [(competencia, valor), ...])]."""
    formatador = formatador or (lambda v: formato.decimal(v))
    valores = [v for _, pontos in series for _, v in pontos]
    if linha_media is not None:
        valores.append(linha_media)
    if not valores:
        return ""
    minimo, maximo = _faixa(valores)
    # domínio comum: séries de tamanhos diferentes precisam compartilhar o eixo X
    dominio = sorted({competencia for _, pontos in series for competencia, _ in pontos})
    posicao = {competencia: indice for indice, competencia in enumerate(dominio)}

    partes = [_abre_svg(), *_grade_y(minimo, maximo, formatador), *_rotulos_eixo_x(dominio)]
    if linha_media is not None:
        y = _escala_y(linha_media, minimo, maximo)
        partes.append(
            f'<line x1="{MARGEM_ESQ}" y1="{y:.1f}" x2="{LARGURA - MARGEM_DIR}" y2="{y:.1f}" '
            f'stroke="{COR_MEDIA}" stroke-width="1.5" stroke-dasharray="6 4"/>'
        )
        partes.append(
            f'<text x="{LARGURA - MARGEM_DIR}" y="{y - 6:.1f}" text-anchor="end" '
            f'fill="{COR_MEDIA}" font-size="12">{rotulo_media} {formatador(linha_media)}</text>'
        )
    for indice, (nome, pontos) in enumerate(series):
        cor = CORES[indice % len(CORES)]
        coordenadas = " ".join(
            f"{_escala_x(posicao[competencia], len(dominio)):.1f},{_escala_y(v, minimo, maximo):.1f}"
            for competencia, v in pontos
        )
        partes.append(
            f'<polyline points="{coordenadas}" fill="none" stroke="{cor}" '
            'stroke-width="2" stroke-linejoin="round"/>'
        )
        # pontos com tooltip nativo (mês + valor); visíveis quando a série é curta
        raio = 3 if len(pontos) <= 40 else 6
        opacidade = "1" if len(pontos) <= 40 else "0"
        for competencia, v in pontos:
            x = _escala_x(posicao[competencia], len(dominio))
            y = _escala_y(v, minimo, maximo)
            partes.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{raio}" fill="{cor}" opacity="{opacidade}">'
                f"<title>{nome} · {formato.competencia_curta(competencia)}: {formatador(v)}</title></circle>"
            )
        if len(series) > 1:
            partes.append(
                f'<text x="{MARGEM_ESQ + 8 + indice * 170}" y="{MARGEM_TOPO + 12}" '
                f'fill="{cor}" font-size="12" font-weight="bold">— {nome}</text>'
            )
    partes.append("</svg>")
    return "".join(partes)


def grafico_barras(pontos: list[Ponto], formatador: Formatador | None = None) -> str:
    """Gráfico de barras com base em zero; `pontos` = [(rotulo, valor)]."""
    formatador = formatador or (lambda v: formato.decimal(v))
    if not pontos:
        return ""
    maximo = max(v for _, v in pontos) or 1
    maximo *= 1.15
    area = LARGURA - MARGEM_ESQ - MARGEM_DIR
    passo = area / len(pontos)
    largura_barra = min(passo * 0.62, 64)

    # com muitas barras (visão mensal), rótulos e valores viram poluição:
    # espaça os rótulos e omite o valor no topo
    passo_rotulo = max(1, -(-len(pontos) // 12))
    mostrar_valores = len(pontos) <= 15

    partes = [_abre_svg(), *_grade_y(0, maximo, formatador)]
    for indice, (rotulo, valor) in enumerate(pontos):
        x = MARGEM_ESQ + passo * indice + (passo - largura_barra) / 2
        y = _escala_y(valor, 0, maximo)
        base = ALTURA - MARGEM_BAIXO
        centro = x + largura_barra / 2
        rotulo_bonito = formato.competencia_curta(rotulo) if _parece_competencia(rotulo) else rotulo
        partes.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{largura_barra:.1f}" '
            f'height="{max(base - y, 0):.1f}" rx="3" fill="{CORES[0]}" opacity="0.85">'
            f"<title>{rotulo_bonito}: {formatador(valor)}</title></rect>"
        )
        if mostrar_valores:
            partes.append(
                f'<text x="{centro:.1f}" y="{y - 6:.1f}" text-anchor="middle" '
                f'fill="{COR_TEXTO}" font-size="11">{formatador(valor)}</text>'
            )
        if indice % passo_rotulo == 0:
            partes.append(
                f'<text x="{centro:.1f}" y="{ALTURA - MARGEM_BAIXO + 18}" text-anchor="middle" '
                f'fill="{COR_TEXTO}" font-size="12">{rotulo_bonito}</text>'
            )
    partes.append("</svg>")
    return "".join(partes)


# --- primitivas ---------------------------------------------------------------


def _abre_svg() -> str:
    return (
        f'<svg viewBox="0 0 {LARGURA} {ALTURA}" xmlns="http://www.w3.org/2000/svg" '
        'style="width:100%;height:auto" font-family="system-ui, sans-serif">'
    )


def _faixa(valores: list[float]) -> tuple[float, float]:
    minimo, maximo = min(valores), max(valores)
    folga = (maximo - minimo) * 0.08 or abs(maximo) * 0.08 or 1
    return minimo - folga, maximo + folga


def _escala_x(indice: int, total: int) -> float:
    area = LARGURA - MARGEM_ESQ - MARGEM_DIR
    if total <= 1:
        return MARGEM_ESQ + area / 2
    return MARGEM_ESQ + area * indice / (total - 1)


def _escala_y(valor: float, minimo: float, maximo: float) -> float:
    area = ALTURA - MARGEM_TOPO - MARGEM_BAIXO
    if maximo == minimo:
        return MARGEM_TOPO + area / 2
    return MARGEM_TOPO + area * (1 - (valor - minimo) / (maximo - minimo))


def _grade_y(minimo: float, maximo: float, formatador: Formatador) -> list[str]:
    partes = []
    for i in range(5):
        valor = minimo + (maximo - minimo) * i / 4
        y = _escala_y(valor, minimo, maximo)
        partes.append(
            f'<line x1="{MARGEM_ESQ}" y1="{y:.1f}" x2="{LARGURA - MARGEM_DIR}" y2="{y:.1f}" '
            f'stroke="{COR_GRADE}" stroke-width="1"/>'
        )
        partes.append(
            f'<text x="{MARGEM_ESQ - 8}" y="{y + 4:.1f}" text-anchor="end" '
            f'fill="{COR_TEXTO}" font-size="11">{formatador(valor)}</text>'
        )
    return partes


def _parece_competencia(rotulo: str) -> bool:
    return len(rotulo) == 7 and rotulo[4] == "-"


def _rotulos_eixo_x(dominio: list[str]) -> list[str]:
    """Rótulos do eixo X: janelas curtas ganham mês ('mai/26'); longas, o ano."""
    if len(dominio) <= 30:
        return _rotulos_meses(dominio)
    return _rotulos_anos(dominio)


def _rotulos_meses(dominio: list[str]) -> list[str]:
    partes = []
    passo = max(1, -(-len(dominio) // 10))
    total = len(dominio)
    for indice, competencia in enumerate(dominio):
        if indice % passo:
            continue
        x = _escala_x(indice, total)
        partes.append(
            f'<text x="{x:.1f}" y="{ALTURA - MARGEM_BAIXO + 18}" text-anchor="middle" '
            f'fill="{COR_TEXTO}" font-size="12">{formato.competencia_curta(competencia)}</text>'
        )
    return partes


def _rotulos_anos(dominio: list[str]) -> list[str]:
    """Um rótulo por virada de ano (competências AAAA-MM no eixo X)."""
    partes = []
    ultimo_ano = ""
    total = len(dominio)
    anos_no_eixo = len({competencia[:4] for competencia in dominio})
    pular_impares = anos_no_eixo > 12
    for indice, competencia in enumerate(dominio):
        ano = competencia[:4]
        if ano != ultimo_ano and not (pular_impares and int(ano) % 2):
            x = _escala_x(indice, total)
            partes.append(
                f'<text x="{x:.1f}" y="{ALTURA - MARGEM_BAIXO + 18}" text-anchor="middle" '
                f'fill="{COR_TEXTO}" font-size="12">{ano}</text>'
            )
            ultimo_ano = ano
    return partes
