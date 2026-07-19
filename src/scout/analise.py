"""Monta o RaioX de um ativo a partir do cache local (sem internet).

Os indicadores vêm dos informes mensais da CVM e das cotações em cache;
o motor de red flags roda sobre as mesmas séries e devolve alertas com
evidência e fonte.
"""

from __future__ import annotations

import dataclasses
import sqlite3

from . import armazenamento, formato, ranking, redflags, series
from .modelos import FundoIrmao, Imovel, IndicadorLinha, RaioX
from .redflags.contexto import Contexto

# regra disparada -> linha de indicador que ganha o ⚠
_INDICADOR_DA_REGRA = {
    "distribuicao": "DY mensal",
    "distribuicao_exata": "DY mensal",
    "diluicao": "Nº de cotas",
    "vp_queda": "VP/cota",
    "vacancia": "Vacância",
    "cotistas": "Cotistas",
    "pvp_faixa": "P/VP",
}


Serie = list[tuple[str, float]]


@dataclasses.dataclass(frozen=True)
class DadosGraficos:
    """Séries brutas para o relatório HTML (gráficos SVG)."""

    cotacao: Serie
    vp_ajustado: Serie
    pvp: Serie
    pvp_media: float | None
    dy_por_ano: Serie
    dy_por_mes: Serie  # últimos 12 meses
    # rendimento estimado em R$/cota (DY × VP da cota do mês), alinhado às séries de DY
    rend_por_ano: list[float | None]
    rend_por_mes: list[float | None]
    pl_por_ano: Serie
    pl_por_mes: Serie
    # janela -> modo ("com"/"sem" reinvestimento) -> [(nome da série, pontos % acumulado)]
    rentabilidade: dict[str, dict[str, list[tuple[str, Serie]]]]
    vacancia: Serie = dataclasses.field(default_factory=list)  # % por trimestre


@dataclasses.dataclass(frozen=True)
class Oscilacao:
    """Mês com variação forte da cota + eventos FACTUAIS do mesmo período.

    Eventos são coincidência de período, nunca afirmação de causa — a página
    deixa isso explícito."""

    mes: str  # AAAA-MM
    variacao: float  # % no mês, sobre a cota ajustada por desdobramento
    eventos: list[str]


@dataclasses.dataclass(frozen=True)
class AnaliseCompleta:
    raiox: RaioX
    graficos: DadosGraficos
    oscilacoes: list[Oscilacao] = dataclasses.field(default_factory=list)


def montar_completo(
    con: sqlite3.Connection, ticker: str, varredura: list | None = None
) -> AnaliseCompleta | None:
    raiox = montar_raio_x(con, ticker, varredura=varredura)
    if raiox is None:
        return None
    fundo = armazenamento.resolver_fundo(con, raiox.ticker)
    serie = armazenamento.serie_complemento(con, fundo.cnpj)
    cotacoes = armazenamento.serie_cotacoes(con, raiox.ticker)
    vp_ajustada = series.serie_vp_ajustada(serie)
    indices = {
        nome: armazenamento.serie_indice(con, nome) for nome in ("CDI", "IPCA", "IFIX")
    }
    graficos = _dados_graficos(serie, cotacoes, vp_ajustada, indices)
    graficos = dataclasses.replace(
        graficos, vacancia=_serie_vacancia(armazenamento.serie_imoveis(con, fundo.cnpj))
    )
    return AnaliseCompleta(
        raiox=raiox,
        graficos=graficos,
        oscilacoes=_oscilacoes(serie, cotacoes, vp_ajustada),
    )


LIMIAR_OSCILACAO = 10.0  # variação mensal (%) a partir da qual o mês é destacado


def _oscilacoes(
    serie: list[sqlite3.Row],
    cotacoes: list[sqlite3.Row],
    vp_ajustada: dict[str, float],
) -> list[Oscilacao]:
    """Meses com variação forte da cota, cruzados com eventos do período que
    já conhecemos pelos informes da CVM (emissão de cotas, mudança brusca no
    rendimento). Usa a cota AJUSTADA por desdobramento — split não vira
    oscilação falsa. Fatos relevantes entram na camada de exibição."""
    ajustado = [
        (linha["competencia"], linha["fechamento_ajustado"])
        for linha in cotacoes
        if linha["fechamento_ajustado"]
    ]
    bruto = {
        linha["competencia"]: linha["fechamento"]
        for linha in cotacoes
        if linha["fechamento"]
    }
    cotas = {
        linha["competencia"]: linha["cotas_emitidas"]
        for linha in serie
        if linha["cotas_emitidas"]
    }
    rendimento = {
        linha["competencia"]: linha["dy_mes"] * vp_ajustada[linha["competencia"]]
        for linha in serie
        if series.dy_valido(linha["dy_mes"]) and vp_ajustada.get(linha["competencia"])
    }

    oscilacoes = []
    for (mes_anterior, preco_anterior), (mes, preco) in zip(ajustado, ajustado[1:]):
        if not preco_anterior:
            continue
        variacao = 100 * (preco - preco_anterior) / preco_anterior
        if abs(variacao) < LIMIAR_OSCILACAO:
            continue
        # fundo ilíquido: preço BRUTO parado (sem negócio) com a série ajustada
        # saltando é artefato do ajuste de proventos sobre preço defasado —
        # exige que o preço real também tenha se movido, na mesma direção
        bruto_anterior, bruto_mes = bruto.get(mes_anterior), bruto.get(mes)
        if bruto_anterior and bruto_mes:
            variacao_bruta = 100 * (bruto_mes - bruto_anterior) / bruto_anterior
            if abs(variacao_bruta) < LIMIAR_OSCILACAO or (variacao_bruta > 0) != (variacao > 0):
                continue
        eventos = []
        base_cotas, cotas_mes = cotas.get(mes_anterior), cotas.get(mes)
        if base_cotas and cotas_mes and cotas_mes >= base_cotas * 2.5:
            # salto de 2,5x+ na base de cotas é desdobramento, não emissão
            # (mesmo limiar do ajuste de VP em series.serie_vp_ajustada)
            eventos.append(
                f"desdobramento de cotas no período (base multiplicada por {cotas_mes / base_cotas:.0f})"
            )
        elif base_cotas and cotas_mes and cotas_mes > base_cotas * 1.005:
            eventos.append(
                f"emissão de cotas no período (+{formato.decimal(100 * (cotas_mes / base_cotas - 1), 1)}% na base de cotas)"
            )
        rend_anterior, rend_mes = rendimento.get(mes_anterior), rendimento.get(mes)
        if rend_anterior and rend_mes and rend_anterior > 0:
            delta = 100 * (rend_mes - rend_anterior) / rend_anterior
            if delta <= -30:
                eventos.append(
                    f"rendimento por cota caiu de ≈R$ {formato.decimal(rend_anterior)} "
                    f"para ≈R$ {formato.decimal(rend_mes)}"
                )
            elif delta >= 30:
                eventos.append(
                    f"rendimento por cota subiu de ≈R$ {formato.decimal(rend_anterior)} "
                    f"para ≈R$ {formato.decimal(rend_mes)}"
                )
        oscilacoes.append(Oscilacao(mes=mes, variacao=variacao, eventos=eventos))
    return oscilacoes


def _serie_vacancia(imoveis: list[sqlite3.Row]) -> list[tuple[str, float]]:
    """Vacância % por trimestre, ponderada por área (lixo fora de [0,1] descartado)."""
    por_competencia: dict[str, list[tuple[float, float]]] = {}
    for linha in imoveis:
        if linha["vacancia"] is None or not 0 <= linha["vacancia"] <= 1:
            continue
        por_competencia.setdefault(linha["competencia"], []).append(
            (linha["vacancia"], linha["area"] or 0)
        )
    serie_v = []
    for competencia in sorted(por_competencia):
        pares = por_competencia[competencia]
        area_total = sum(area for _, area in pares)
        if area_total > 0:
            valor = 100 * sum(v * area for v, area in pares) / area_total
        else:
            valor = 100 * sum(v for v, _ in pares) / len(pares)
        serie_v.append((competencia, valor))
    return serie_v


def _dados_graficos(
    serie: list[sqlite3.Row],
    cotacoes: list[sqlite3.Row],
    vp_ajustada: dict[str, float],
    indices: dict[str, dict[str, float]] | None = None,
) -> DadosGraficos:
    indices = indices or {}
    cotacao = [
        (linha["competencia"], linha["fechamento"])
        for linha in cotacoes
        if linha["fechamento"]
    ]
    ajustado = [
        (linha["competencia"], linha["fechamento_ajustado"])
        for linha in cotacoes
        if linha["fechamento_ajustado"]
    ]
    pvp = [
        (competencia, fechamento / vp_ajustada[competencia])
        for competencia, fechamento in cotacao
        if vp_ajustada.get(competencia)
    ]
    pvp_media = sum(v for _, v in pvp) / len(pvp) if pvp else None

    dy_por_ano: dict[str, float] = {}
    rend_por_ano: dict[str, float | None] = {}
    pl_por_ano: dict[str, float] = {}
    dy_por_mes: list[tuple[str, float]] = []
    rend_por_mes: list[float | None] = []
    pl_por_mes: list[tuple[str, float]] = []
    for linha in serie:
        ano = linha["competencia"][:4]
        if series.dy_valido(linha["dy_mes"]):
            dy_por_ano[ano] = dy_por_ano.get(ano, 0.0) + linha["dy_mes"] * 100
            dy_por_mes.append((linha["competencia"], linha["dy_mes"] * 100))
            # rendimento estimado: o DY da CVM é relativo ao VP da cota do mês;
            # usa o VP ajustado por desdobramento para os R$ serem comparáveis
            # na base de cotas atual
            vp_mes = vp_ajustada.get(linha["competencia"])
            rendimento = linha["dy_mes"] * vp_mes if vp_mes else None
            rend_por_mes.append(rendimento)
            if rendimento is None:
                rend_por_ano[ano] = None  # mês sem VP contamina o total do ano
            elif ano not in rend_por_ano:
                rend_por_ano[ano] = rendimento
            elif rend_por_ano[ano] is not None:
                rend_por_ano[ano] += rendimento
        if linha["patrimonio_liquido"] is not None:
            pl_por_ano[ano] = linha["patrimonio_liquido"]  # último mês do ano vence
            pl_por_mes.append((linha["competencia"], linha["patrimonio_liquido"]))

    ano_parcial = serie[-1]["competencia"][:4] if serie else ""
    rotulo = lambda ano: f"{ano}*" if ano == ano_parcial else ano  # noqa: E731
    anos_dy = sorted(dy_por_ano)

    return DadosGraficos(
        cotacao=cotacao,
        vp_ajustado=sorted(vp_ajustada.items()),
        pvp=pvp,
        pvp_media=pvp_media,
        dy_por_ano=[(rotulo(ano), dy_por_ano[ano]) for ano in anos_dy],
        dy_por_mes=dy_por_mes[-12:],
        rend_por_ano=[rend_por_ano.get(ano) for ano in anos_dy],
        rend_por_mes=rend_por_mes[-12:],
        pl_por_ano=[(rotulo(ano), valor) for ano, valor in sorted(pl_por_ano.items())],
        pl_por_mes=pl_por_mes,
        rentabilidade=_rentabilidades(cotacao, ajustado, indices),
    )


def _rentabilidades(
    cotacao: list[tuple[str, float]],
    ajustado: list[tuple[str, float]],
    indices: dict[str, dict[str, float]],
) -> dict[str, dict[str, list[tuple[str, list[tuple[str, float]]]]]]:
    """Retorno % acumulado do fundo vs índices, por janela e modo.

    Modo "com" reinveste os rendimentos (cotação ajustada por proventos);
    modo "sem" é só a variação de preço. CDI/IPCA são iguais nos dois.
    """
    janelas = {"12 meses": 13, "5 anos": 61, "máximo": None}
    fontes = {"com": ajustado, "sem": cotacao}
    resultado: dict[str, dict[str, list]] = {}
    for nome_janela, tamanho in janelas.items():
        modos: dict[str, list] = {}
        for modo, fonte in fontes.items():
            recorte = fonte[-tamanho:] if tamanho else fonte
            if len(recorte) < 3 or (tamanho and len(fonte) < tamanho):
                continue
            series_janela = [("Fundo", _acumulado_fundo(recorte))]
            competencias = [competencia for competencia, _ in recorte]
            for nome_indice, valores in indices.items():
                acumulado = _acumulado_indice(valores, competencias)
                if len(acumulado) >= 3:
                    series_janela.append((nome_indice, acumulado))
            modos[modo] = series_janela
        if "com" in modos:
            resultado[nome_janela] = modos
    return resultado


def _acumulado_fundo(pontos: list[tuple[str, float]]) -> list[tuple[str, float]]:
    base = pontos[0][1]
    return [(competencia, 100 * (valor / base - 1)) for competencia, valor in pontos]


def _acumulado_indice(
    valores: dict[str, float], competencias: list[str]
) -> list[tuple[str, float]]:
    """Acumula o índice mensal sobre as competências do fundo (base 0 na 1ª)."""
    acumulado = [(competencias[0], 0.0)]
    fator = 1.0
    for competencia in competencias[1:]:
        if competencia not in valores:
            break  # índice ainda não publicado para o mês (IPCA atrasa ~1 mês)
        fator *= 1 + valores[competencia] / 100
        acumulado.append((competencia, 100 * (fator - 1)))
    return acumulado


def montar_raio_x(
    con: sqlite3.Connection, ticker: str, varredura: list | None = None
) -> RaioX | None:
    """Monta o raio-x. `varredura` (ranking.varrer pré-computado) evita
    varrer o segmento de novo ao gerar muitas páginas de uma vez."""
    ticker = ticker.strip().upper()
    fundo = armazenamento.resolver_fundo(con, ticker)
    if fundo is None:
        return None
    serie = armazenamento.serie_complemento(con, fundo.cnpj)
    if not serie:
        return None
    cotacoes = armazenamento.serie_cotacoes(con, ticker)
    meta_cotacao = armazenamento.cotacao_meta(con, ticker)
    preco = meta_cotacao["preco_atual"] if meta_cotacao else None
    vp_ajustada = series.serie_vp_ajustada(serie)
    imoveis_atuais = armazenamento.imoveis_atuais(con, fundo.cnpj)
    resultados = armazenamento.serie_resultados(con, fundo.cnpj)

    contexto = Contexto(
        serie=serie,
        vp_ajustada=vp_ajustada,
        cotacoes=cotacoes,
        preco_atual=preco,
        imoveis_atuais=imoveis_atuais,
        resultados=resultados,
        tem_informe_trimestral=bool(imoveis_atuais or resultados),
    )
    resultado = redflags.avaliar(contexto)
    admin = armazenamento.administrador_do_fundo(con, fundo.cnpj)
    cadastro = armazenamento.cadastro_do_fundo(con, fundo.cnpj)
    pares, pares_media = _pares_do_segmento(con, fundo.cnpj, fundo.segmento, varredura)

    notas = []
    if not cotacoes:
        notas.append("sem cotação de bolsa para este ticker")
    if resultado.nao_avaliadas:
        notas.append(
            "não avaliadas por falta de histórico ou dado: "
            + "; ".join(resultado.nao_avaliadas)
        )

    indicadores = _montar_indicadores(serie, cotacoes, preco, vp_ajustada)
    vacancia = contexto.vacancia_atual()
    if vacancia is not None:
        indicadores.append(
            IndicadorLinha(
                "Vacância",
                formato.percentual(vacancia),
                "—",
                f"informe de {formato.competencia_br(imoveis_atuais[0]['competencia'])}",
            )
        )
    indicadores = _marcar_alertas(indicadores, resultado.flags)

    atual = serie[-1]
    return RaioX(
        ticker=ticker,
        nome=fundo.nome,
        cnpj=fundo.cnpj,
        classificacao=fundo.segmento,
        gestao=fundo.tipo_gestao,
        dados_ate=formato.competencia_br(atual["competencia"]),
        cotacao_em=_cotacao_com_hora(meta_cotacao["cotado_em"]) if meta_cotacao else "",
        cotado_em_iso=(meta_cotacao["cotado_em"] or "") if meta_cotacao else "",
        indicadores=indicadores,
        red_flags=resultado.flags,
        sem_alerta=resultado.aprovadas,
        notas=notas,
        imoveis=_montar_imoveis(imoveis_atuais),
        imoveis_em=formato.competencia_br(imoveis_atuais[0]["competencia"])
        if imoveis_atuais
        else "",
        imoveis_por_estado=_imoveis_por_estado(imoveis_atuais),
        setores_inquilinos=[
            (linha["setor"], 100 * linha["pct"])
            for linha in armazenamento.setores_atuais(con, fundo.cnpj)
        ],
        administrador=admin["administrador"] if admin else "",
        fundos_irmaos=_fundos_irmaos(con, admin, fundo.cnpj) if admin else [],
        gestora=(cadastro["gestor"] or "") if cadastro else "",
        gestora_e_admin=bool(
            cadastro
            and cadastro["cnpj_gestor"]
            and cadastro["cnpj_gestor"] == armazenamento.so_digitos(cadastro["cnpj_administrador"])
        ),
        fundos_gestora=_fundos_da_gestora(con, cadastro, fundo.cnpj),
        pares=pares,
        pares_media=pares_media,
        selo=redflags.selo(resultado),
        red_flags_avaliadas=True,
        exemplo=False,
    )


def _montar_imoveis(imoveis_atuais: list[sqlite3.Row]) -> list[Imovel]:
    """Converte as linhas do informe em Imovel, normalizando escalas.

    O % da receita é auto-declarado sem escala padronizada: uns fundos
    mandam percentual (soma ~100), outros mandam fração (soma ~1).
    Normaliza pela soma do próprio fundo.
    """
    somatorio = sum(linha["pct_receita"] or 0 for linha in imoveis_atuais)
    fator_receita = 100 if 0 < somatorio <= 2 else 1

    def _fracao_pct(valor: float | None) -> float | None:
        return 100 * valor if valor is not None and 0 <= valor <= 1 else None

    return [
        Imovel(
            nome=linha["nome"],
            area=linha["area"],
            vacancia=_fracao_pct(linha["vacancia"]),
            inadimplencia=_fracao_pct(linha["inadimplencia"]),
            pct_receita=linha["pct_receita"] * fator_receita
            if linha["pct_receita"] is not None
            else None,
        )
        for linha in imoveis_atuais
    ]


_UFS = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG",
    "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
}


def _uf_do_endereco(endereco: str | None) -> str | None:
    """Estima a UF pelo endereço do informe (a CVM não publica campo próprio).
    Vale a ÚLTIMA sigla válida — endereços terminam em '... cidade - UF'
    (a última evita falsos positivos como 'AL' de Alameda no início)."""
    import re as _re

    if not endereco:
        return None
    candidatas = _re.findall(r"(?<![A-Za-zÀ-ú])([A-Z]{2})(?![A-Za-zÀ-ú])", endereco.upper())
    validas = [sigla for sigla in candidatas if sigla in _UFS]
    return validas[-1] if validas else None


def _imoveis_por_estado(imoveis_atuais: list[sqlite3.Row]) -> list[tuple[str, float]]:
    """Participação de cada UF na área total dos imóveis (maiores primeiro);
    imóvel sem UF identificável entra como '?'."""
    area_por_uf: dict[str, float] = {}
    for linha in imoveis_atuais:
        area = linha["area"] or 0
        if area <= 0:
            continue
        uf = _uf_do_endereco(linha["endereco"]) or "?"
        area_por_uf[uf] = area_por_uf.get(uf, 0) + area
    total = sum(area_por_uf.values())
    if total <= 0:
        return []
    return sorted(
        ((uf, 100 * area / total) for uf, area in area_por_uf.items()),
        key=lambda item: -item[1],
    )


def _fundos_irmaos(con: sqlite3.Connection, admin, cnpj_fundo: str) -> list[FundoIrmao]:
    """Outros fundos do mesmo administrador, cada um com seu selo (sem cotação)."""
    return _montar_relacionados(
        con, armazenamento.fundos_do_administrador(con, admin["cnpj_administrador"], cnpj_fundo)
    )


def _fundos_da_gestora(con: sqlite3.Connection, cadastro, cnpj_fundo: str) -> list[FundoIrmao]:
    """Outros fundos da mesma gestora (cadastro CVM), cada um com seu selo."""
    if not cadastro or not cadastro["cnpj_gestor"]:
        return []
    return _montar_relacionados(
        con, armazenamento.fundos_do_gestor(con, cadastro["cnpj_gestor"], cnpj_fundo)
    )


def _montar_relacionados(con: sqlite3.Connection, linhas) -> list[FundoIrmao]:
    irmaos = []
    for linha in linhas:
        serie = armazenamento.serie_complemento(con, linha["cnpj"])
        if not serie:
            continue
        contexto = Contexto(
            serie=serie,
            vp_ajustada=series.serie_vp_ajustada(serie),
            imoveis_atuais=armazenamento.imoveis_atuais(con, linha["cnpj"]),
            resultados=armazenamento.serie_resultados(con, linha["cnpj"]),
        )
        resultado = redflags.avaliar(contexto)
        irmaos.append(
            FundoIrmao(
                ticker=series.ticker_do_isin(linha["isin"]),
                nome=linha["nome"] or linha["cnpj"],
                segmento=linha["segmento"] or "—",
                anos=len(serie) / 12,
                selo=redflags.selo(resultado),
                motivos=tuple(flag.titulo for flag in resultado.flags),
            )
        )
    return irmaos


_ticker_do_isin = series.ticker_do_isin


def _cotacao_com_hora(cotado_em: str | None) -> str:
    """'2026-07-17 18:04' -> '17/07/2026 18:04' (hora do último negócio, se houver)."""
    if not cotado_em:
        return ""
    data = formato.dia_br(cotado_em)
    hora = cotado_em[11:16] if len(cotado_em) >= 16 else ""
    return f"{data} {hora}".strip()


def _pares_do_segmento(
    con: sqlite3.Connection,
    cnpj: str,
    segmento: str,
    varredura: list | None = None,
    top: int = 5,
) -> tuple[list, dict]:
    """Maiores pares do mesmo segmento (por PL) + médias do segmento."""
    if not segmento or segmento == "—":
        return [], {}
    if varredura is not None:
        resumos = [r for r in varredura if r.segmento == segmento]
    else:
        cnpjs = {
            linha["cnpj"]
            for linha in con.execute(
                """
                WITH ultimo AS (
                    SELECT cnpj, MAX(competencia) AS competencia FROM informes_gerais GROUP BY cnpj
                )
                SELECT g.cnpj FROM informes_gerais g
                JOIN ultimo u ON u.cnpj = g.cnpj AND u.competencia = g.competencia
                WHERE g.segmento = ?
                """,
                (segmento,),
            )
        }
        if len(cnpjs) < 2:
            return [], {}
        resumos = ranking.varrer(con, cnpjs=cnpjs)
    if len(resumos) < 2:
        return [], {}

    def _media(campo: str) -> float | None:
        valores = [getattr(r, campo) for r in resumos if getattr(r, campo) is not None]
        return sum(valores) / len(valores) if valores else None

    media = {
        "dy": _media("dy_12m"),
        "pvp": _media("pvp"),
        "pl": _media("pl"),
        "n": len(resumos),
    }
    pares = sorted(
        (r for r in resumos if r.cnpj != cnpj),
        key=lambda r: r.pl or 0,
        reverse=True,
    )[:top]
    return pares, media


def _marcar_alertas(indicadores: list[IndicadorLinha], flags) -> list[IndicadorLinha]:
    motivos: dict[str, list[str]] = {}
    for flag in flags:
        nome = _INDICADOR_DA_REGRA.get(flag.codigo)
        if nome:
            motivos.setdefault(nome, []).append(flag.titulo)
    return [
        dataclasses.replace(linha, alerta=True, alerta_motivo="; ".join(motivos[linha.nome]))
        if linha.nome in motivos
        else linha
        for linha in indicadores
    ]


def _montar_indicadores(
    serie: list[sqlite3.Row],
    cotacoes: list[sqlite3.Row],
    preco: float | None,
    vp_ajustada: dict[str, float],
) -> list[IndicadorLinha]:
    atual = serie[-1]
    primeira = serie[0]["competencia"]
    linhas = []

    if preco is not None and cotacoes:
        linhas.append(
            IndicadorLinha(
                "Cotação",
                f"R$ {formato.decimal(preco)}",
                _oscilacao_12m(cotacoes, preco),
                _oscilacao_no_ano(cotacoes, preco),
            )
        )
        vp = atual["vp_cota"]
        if vp:
            linhas.append(
                IndicadorLinha(
                    "P/VP",
                    formato.decimal(preco / vp),
                    "—",
                    _media_pvp(cotacoes, vp_ajustada),
                )
            )

    pl = atual["patrimonio_liquido"]
    if pl is not None:
        linhas.append(
            IndicadorLinha(
                "Patrimônio líquido",
                formato.moeda_compacta(pl),
                _variacao_12m(serie, "patrimonio_liquido"),
                f"dados desde {formato.competencia_br(primeira)}",
            )
        )

    vp = atual["vp_cota"]
    if vp is not None:
        linhas.append(
            IndicadorLinha(
                "VP/cota",
                formato.decimal(vp),
                _variacao_12m(serie, "vp_cota"),
                _media_vp_ajustada(vp_ajustada),
            )
        )

    cotas = atual["cotas_emitidas"]
    if cotas is not None:
        linhas.append(
            IndicadorLinha(
                "Nº de cotas",
                formato.compacto(cotas),
                _variacao_12m(serie, "cotas_emitidas"),
                "—",
            )
        )

    ativo = atual["valor_ativo"]
    if ativo is not None:
        linhas.append(
            IndicadorLinha(
                "Valor do ativo",
                formato.moeda_compacta(ativo),
                _variacao_12m(serie, "valor_ativo"),
                "—",
            )
        )

    dy = atual["dy_mes"]
    if dy is not None:
        linhas.append(
            IndicadorLinha(
                "DY mensal",
                formato.percentual(dy * 100),
                _dy_acumulado_12m(serie),
                _media_dy(serie),
            )
        )

    cotistas = atual["cotistas"]
    if cotistas is not None:
        linhas.append(
            IndicadorLinha(
                "Cotistas",
                formato.compacto(cotistas),
                _variacao_12m(serie, "cotistas"),
                "—",
            )
        )

    return linhas


# --- células formatadas ------------------------------------------------------


def _variacao_12m(serie: list[sqlite3.Row], campo: str) -> str:
    variacao = series.variacao_pct(serie, campo, 12)
    if variacao is None:
        return "—"
    return formato.percentual(variacao, sinal=True)


def _oscilacao_12m(cotacoes: list[sqlite3.Row], preco_atual: float) -> str:
    alvo = series.competencia_menos_meses(cotacoes[-1]["competencia"], 12)
    base = series.valor_em(cotacoes, "fechamento", alvo)
    if not base:
        return "—"
    return formato.percentual(100 * (preco_atual - base) / base, sinal=True)


def _oscilacao_no_ano(cotacoes: list[sqlite3.Row], preco_atual: float) -> str:
    dezembro = f"{int(cotacoes[-1]['competencia'][:4]) - 1}-12"
    base = series.valor_em(cotacoes, "fechamento", dezembro)
    if not base:
        return "—"
    return f"{formato.percentual(100 * (preco_atual - base) / base, sinal=True)} no ano"


def _media_pvp(cotacoes: list[sqlite3.Row], vp_ajustada: dict[str, float]) -> str:
    razoes = [
        candle["fechamento"] / vp_ajustada[candle["competencia"]]
        for candle in cotacoes
        if candle["fechamento"] and vp_ajustada.get(candle["competencia"])
    ]
    if not razoes:
        return "—"
    return f"média {formato.decimal(sum(razoes) / len(razoes))}"


def _media_vp_ajustada(vp_ajustada: dict[str, float]) -> str:
    if not vp_ajustada:
        return "—"
    valores = list(vp_ajustada.values())
    return f"média {formato.decimal(sum(valores) / len(valores))}"


def _dy_acumulado_12m(serie: list[sqlite3.Row]) -> str:
    acumulado = series.dy_acumulado(serie, 12)
    if acumulado is None:
        return "—"
    return f"{formato.percentual(acumulado * 100)} acumulado"


def _media_dy(serie: list[sqlite3.Row]) -> str:
    validos = [linha["dy_mes"] for linha in serie if series.dy_valido(linha["dy_mes"])]
    if not validos:
        return "—"
    return f"média {formato.percentual(sum(validos) / len(validos) * 100)}"
