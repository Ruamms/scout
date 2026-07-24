"""Página de ETF — raio-x próprio da classe (NÃO é a página de FII adaptada).

O diferencial é a "carteirinha de regras": cada tipo de ETF tem regras de
distribuição, tributação e comportamento que quase ninguém conta ao investidor
(docs/ETFS.md). Tudo factual, com fonte — nunca recomendação.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from .. import analise, armazenamento, formato, series
from . import graficos
from .html import CSS_MARCA, TAG_FAVICON, _e, marca_html

# carteirinha de regras por classe — linguagem de leigo, fatos com fonte
REGRAS_POR_CLASSE = {
    "Ações Brasil": (
        "Uma cota = uma cesta de ações brasileiras, rebalanceada sozinha.",
        "Os dividendos das empresas são REINVESTIDOS dentro do fundo — nada cai na sua conta; "
        "o retorno aparece no preço da cota.",
        "IR: 15% sobre o ganho na venda, SEM a isenção de R$ 20 mil/mês das ações "
        "(Lei 11.033/2004 não alcança ETF).",
    ),
    "Ações Internacionais": (
        "Exposição ao exterior sem abrir conta lá fora — mas com DUPLA exposição: o índice E o dólar.",
        "O índice pode subir e a cota cair (quando o real valoriza) — e vice-versa.",
        "IR: 15% sobre o ganho na venda, sem isenção de R$ 20 mil/mês.",
    ),
    "Renda Fixa": (
        "Carteira de títulos com liquidez de bolsa — e o rendimento é INVISÍVEL: a cota engorda, "
        "nada pinga na conta até você vender.",
        "SEM come-cotas e SEM IOF (nem nos primeiros 30 dias — diferente de CDB/Tesouro).",
        "IR na venda pelo prazo médio da carteira do fundo (Lei 13.043/2014): >720 dias = 15% FIXO, "
        "não importa quanto tempo VOCÊ segure.",
        "Atenção: marcação a mercado — juro sobe, cota de índice longo cai. Renda fixa que oscila.",
    ),
    "Renda Fixa Internacional": (
        "Títulos de renda fixa DE FORA (ex.: T-Bills dos EUA) — renda fixa que oscila com o DÓLAR.",
        "Sem come-cotas e sem IOF; IR na venda pelo prazo médio da carteira (Lei 13.043/2014).",
        "O retorno em reais mistura os juros lá de fora com a variação cambial — pode ser negativo "
        "mesmo com os juros correndo.",
    ),
    "Cripto": (
        "Exposição a criptoativos sem carteira própria, sem seed phrase, sem exchange — a corretora "
        "reporta seu IR.",
        "PERDE a isenção de R$ 35 mil/mês da cripto comprada direto: aqui é 15% sobre o ganho, sempre.",
        "Volatilidade extrema é da natureza do ativo — e a taxa de administração costuma ser das "
        "mais altas do formato.",
    ),
    "Commodities": (
        "Commodities (ouro etc.) sem barra física nem contrato futuro.",
        "IR: 15% sobre o ganho na venda, sem isenção de R$ 20 mil/mês.",
        "Confira sempre O QUE o fundo carrega de verdade (a carteira está nesta página).",
    ),
    "FIIs (índice)": (
        "Uma cota = uma cesta de fundos imobiliários (índice), com rebalanceamento automático.",
        "Diferente dos FIIs direto: os rendimentos que o fundo recebe são reinvestidos, e a venda "
        "paga 15% de IR (FII direto tem rendimento mensal isento).",
    ),
    "Misto/Híbrido": (
        "Alocação pronta em um papel só — a PROPORÇÃO interna é quem manda no comportamento.",
        "Veja a composição real da carteira nesta página: 70/30 é um produto completamente "
        "diferente de 30/70.",
        "IR: 15% sobre o ganho na venda, sem isenções.",
    ),
}

_RODAPE = (
    "Isto não é recomendação de investimento. Fontes: B3 (fundos listados e cotações oficiais "
    "COTAHIST), CVM (registro de fundos e carteiras/CDA) e Banco Central (índices). Regras "
    "tributárias citadas em caráter informativo — confirme com um contador."
)


def montar_dados_etf(con: sqlite3.Connection, ticker: str, classificacoes: dict | None = None) -> dict | None:
    """Reúne tudo que a página do ETF precisa; None se o ticker não for ETF."""
    from ..coleta import cda

    etf = armazenamento.etf_por_ticker(con, ticker)
    if etf is None:
        return None
    classificacoes = classificacoes if classificacoes is not None else cda.carregar_classificacoes()
    classificacao = classificacoes.get(etf["cnpj"], {})
    cotacoes = armazenamento.serie_cotacoes(con, etf["ticker"])
    meta = armazenamento.cotacao_meta(con, etf["ticker"])
    cadastro = armazenamento.cadastro_do_fundo(con, etf["cnpj"])
    indices = {
        nome: armazenamento.serie_indice(con, nome) for nome in ("CDI", "IPCA", "IFIX")
    }
    cotacao = [
        (linha["competencia"], linha["fechamento"]) for linha in cotacoes if linha["fechamento"]
    ]
    ajustado = [
        (linha["competencia"], linha["fechamento_ajustado"])
        for linha in cotacoes
        if linha["fechamento_ajustado"]
    ]
    carteira = armazenamento.etf_carteira_atual(con, etf["cnpj"])
    classe = (classificacao.get("classificacao_scout") or "").strip() or None

    divergencia_classe = None
    if carteira and classe:
        grupos = {linha["grupo"]: linha["pct"] for linha in carteira}
        apontamentos = cda.verificar(
            {etf["cnpj"]: grupos},
            {etf["cnpj"]: {"ticker": etf["ticker"], "classificacao_scout": classe}},
        )
        duras = [a for a in apontamentos if a["tipo"] == "divergência"]
        if duras:
            divergencia_classe = duras[0]["motivo"]

    dados = {
        "etf": etf,
        "classe": classe,
        "reclassificado": classificacao.get("reclassificado"),
        "observacoes": (classificacao.get("observacoes") or "").strip(),
        "gestor": (cadastro["gestor"] if cadastro else None) or (classificacao.get("gestor") or "").strip(),
        "situacao_cvm": cadastro["situacao"] if cadastro else None,
        "cotacao": cotacao,
        "preco_atual": meta["preco_atual"] if meta else None,
        "cotado_em": meta["cotado_em"] if meta else None,
        "variacao_12m": series.variacao_pct(
            [{"competencia": c, "fechamento": v} for c, v in ajustado], "fechamento", 12
        ),
        "rentabilidade": analise._rentabilidades(cotacao, ajustado, indices),
        "carteira": carteira,
        "pl": armazenamento.etf_pl_atual(con, etf["cnpj"]),
        "liquidez": armazenamento.liquidez_recente(con, etf["ticker"]),
        "divergencia_classe": divergencia_classe,
        "proventos": armazenamento.proventos_do_etf(con, etf["cnpj"]),
        "posicoes": _posicoes_com_links(con, etf["cnpj"]),
        "diario": armazenamento.etf_diario_atual(con, etf["cnpj"]),
    }
    from ..coleta import taxas_etf

    dados["taxa_adm"] = taxas_etf.carregar().get((etf["ticker"] or "").upper())
    # reprecifica a carteira a preço de hoje pelo resolvedor único (ação/FII/ETF
    # já acendem; renda fixa/exterior ficam no valor do CDA até haver fonte)
    from .. import precos

    dados["posicoes"], dados["reprecificacao"] = precos.reprecificar_posicoes(con, dados["posicoes"])
    from .. import etf_flags, redflags

    resultado = etf_flags.avaliar(dados)
    dados["flags"] = resultado
    dados["selo"] = redflags.selo(resultado)
    return dados


def _posicoes_com_links(con: sqlite3.Connection, cnpj: str) -> list[dict]:
    """Top posições da carteira, com o ticker/classe resolvidos quando o
    ativo é algo que TAMBÉM analisamos (FII pelo CNPJ do emissor, ETF idem,
    ações pelo código) — o cruzamento vira link na página."""
    posicoes = []
    for linha in armazenamento.etf_posicoes_atuais(con, cnpj):
        ticker_alvo, classe_alvo = None, None
        if linha["cnpj_emissor"]:
            ticker_fii = armazenamento.ticker_fii_por_cnpj(con, linha["cnpj_emissor"])
            if ticker_fii:
                ticker_alvo, classe_alvo = ticker_fii, "FII"
            else:
                etf_alvo = con.execute(
                    "SELECT ticker FROM etfs WHERE cnpj = ?", (linha["cnpj_emissor"],)
                ).fetchone()
                if etf_alvo and etf_alvo["ticker"]:
                    ticker_alvo, classe_alvo = etf_alvo["ticker"], "ETF"
        if ticker_alvo is None and linha["codigo"]:
            classe_alvo = "Ação" if not linha["codigo"].endswith("11") else None
        posicoes.append(
            {
                "nome": linha["nome"] or linha["codigo"],
                "codigo": linha["codigo"],
                "pct": linha["pct"],
                "quantidade": linha["quantidade"] if "quantidade" in linha.keys() else None,
                "vencimento": linha["vencimento"] if "vencimento" in linha.keys() else None,
                "grupo": linha["grupo"] if "grupo" in linha.keys() else None,
                "competencia": linha["competencia"],
                "ticker_alvo": ticker_alvo,
                "classe_alvo": classe_alvo,
            }
        )
    return posicoes


def _trunca(texto: str, limite: int) -> str:
    texto = texto or ""
    return texto if len(texto) <= limite else texto[: limite - 1].rstrip() + "…"


def gerar(
    dados: dict,
    agora: datetime | None = None,
    com_menu: bool = False,
    leitura: dict | None = None,
    publicados: set[str] | None = None,
    selos: dict | None = None,
) -> str:
    from .html import (
        CSS_BUSCA_TOPO,
        CSS_MENU,
        JS_BUSCA_TOPO,
        JS_MENU,
        JS_GRAFICO_HOVER,
        _COR_SELO,
        _secao_ia,
        _secao_parecer,
        menu_html,
    )

    agora = agora or datetime.now()
    menu = menu_html() if com_menu else ""
    css_menu = (CSS_MENU + CSS_BUSCA_TOPO) if com_menu else ""
    js_menu = (JS_MENU + JS_BUSCA_TOPO) if com_menu else ""
    etf = dados["etf"]
    classe = dados["classe"] or "ETF"
    regras = REGRAS_POR_CLASSE.get(dados["classe"] or "", ())

    from .html import _ajuda

    cards = []

    def _card(nome: str, valor: str, extra: str = "") -> None:
        extra_html = f'<div class="extra">{extra}</div>' if extra else ""
        cards.append(
            f'<div class="card"><div class="nome">{nome}{_ajuda(nome)}</div>'
            f'<div class="valor">{valor}</div>{extra_html}</div>'
        )

    if dados["preco_atual"]:
        quando = (dados["cotado_em"] or "")[:10]
        _card("Cotação (fechamento oficial)", f"R$ {formato.decimal(dados['preco_atual'])}",
              f"pregão de {formato.dia_br(quando) if quando else '—'}")
    if dados["variacao_12m"] is not None:
        _card("Variação 12 meses", formato.percentual(dados["variacao_12m"], sinal=True),
              "preço ajustado por desdobramento")
    if dados["pl"]:
        _card("Patrimônio líquido", formato.moeda_compacta(dados["pl"]["pl"]),
              f"carteira CVM de {formato.competencia_br(dados['pl']['competencia'])}")
    recl = dados.get("reclassificado")
    if recl:
        origem = "leitura das posições pela IA" if recl.get("origem") == "ia" else "carteira real"
        iso = (recl.get("data") or "")[:10]
        data_br = f"{iso[8:10]}/{iso[5:7]}/{iso[0:4]}" if len(iso) == 10 else ""
        rodape_classe = _e(
            f"reclassificado{f' em {data_br}' if data_br else ''} por {origem} — "
            f"antes: {recl.get('classe_anterior') or '—'} · {recl.get('motivo') or ''}".strip(" ·—")
        )
    else:
        rodape_classe = _e(f"segmento B3: {etf['tipo_b3']}")
    _card("Classe (Scout)", _e(classe), rodape_classe)
    if dados["gestor"]:
        _card("Gestora", f'<span class="compacto">{_e(_trunca(str(dados["gestor"]), 52))}</span>', "")
    taxa_info = dados.get("taxa_adm")
    if taxa_info:
        fonte = taxa_info.get("fonte") or ""
        conferido = taxa_info.get("verificado_em") or ""
        if fonte:
            extra = (
                f'<a href="{_e(fonte)}" target="_blank" rel="noopener">regulamento</a>'
                f'{f" · conf. {_e(conferido)}" if conferido else ""}'
            )
        else:
            extra = f"regulamento do fundo{f' · conf. {_e(conferido)}' if conferido else ''}"
        _card(
            "Taxa de administração",
            f'{formato.percentual(taxa_info["taxa_adm_aa"])} a.a.',
            extra,
        )
    diario = dados.get("diario")
    if diario and diario["vl_quota"]:
        _card("Cota patrimonial", f"R$ {formato.decimal(diario['vl_quota'])}",
              f"informe diário de {formato.dia_br(diario['data'])} (FNET) — o valor da carteira por cota")
        if dados.get("preco_atual"):
            premio = 100 * (dados["preco_atual"] / diario["vl_quota"] - 1)
            acima = "acima" if premio >= 0 else "abaixo"
            _card("Prêmio/desconto", formato.percentual(premio, sinal=True),
                  f"preço de mercado (D-1) {acima} da cota patrimonial — os dois são fatos "
                  "de datas próximas, não um alvo")
    if diario and diario["cotistas"]:
        _card("Cotistas", f"{diario['cotistas']:,}".replace(",", "."),
              f"informe diário de {formato.dia_br(diario['data'])}")
    proventos = dados.get("proventos") or []
    if proventos:
        ultimo = proventos[0]
        _card(
            "Distribui renda",
            f"R$ {formato.decimal(ultimo['valor'])}/cota",
            f"pago em {formato.dia_br(ultimo['data_pagamento'])} · NÃO isento de IR",
        )

    composicao = ""
    if dados["carteira"]:
        linhas = "".join(
            f"<tr><td>{_e(linha['grupo'])}</td><td>{formato.percentual(linha['pct'])}</td></tr>"
            for linha in dados["carteira"]
        )
        competencia = formato.competencia_br(dados["carteira"][0]["competencia"])
        composicao = f"""
  <h2>Composição da carteira</h2>
  <div class="grafico">
  <table class="imoveis">
    <thead><tr><th>grupo de ativo</th><th>% da carteira</th></tr></thead>
    <tbody>{linhas}</tbody>
  </table>
  <div class="nota">carteira oficial informada à CVM (CDA) · {competencia} · agrupada por tipo de ativo</div>
  </div>
"""

    secao_posicoes = ""
    if dados.get("posicoes"):
        posicoes = dados["posicoes"]

        def _linha_posicao(posicao) -> str:
            # alvo efetivo: fundos são resolvidos pelo CNPJ (ticker_alvo);
            # ações/units carregam o próprio ticker no campo `codigo`
            alvo = posicao["ticker_alvo"]
            if not alvo and posicao["codigo"] and publicados and posicao["codigo"] in publicados:
                alvo = posicao["codigo"]
            rotulo = _e(posicao["codigo"] or _trunca(posicao["nome"], 44))
            if alvo and publicados and alvo in publicados:
                rotulo = f'<a href="{_e(alvo)}.html">{_e(alvo)}</a>'
            elif posicao["ticker_alvo"]:
                rotulo = _e(posicao["ticker_alvo"])
            badge = (
                f' <span class="badge-posicao">{_e(posicao["classe_alvo"])}</span>'
                if posicao["classe_alvo"]
                else ""
            )
            nome_completo = (
                _e(_trunca(posicao["nome"], 46)) if posicao["codigo"] or posicao["ticker_alvo"] else ""
            )
            qtd = posicao.get("quantidade")
            qtd_txt = formato.compacto(qtd) if qtd else "—"
            preco = posicao.get("preco_hoje")
            preco_txt = f"R$ {formato.decimal(preco)}" if preco else "—"
            # o selo da PÁGINA do ativo (quando o Scout também o analisa) vira
            # a coluna de alerta — as páginas conversam entre si
            selo_alvo = (selos or {}).get(alvo) if alvo else None
            if selo_alvo:
                cor = _COR_SELO.get(selo_alvo.nivel, "#7C8894")
                alerta_txt = (
                    f'<span class="ponto-posicao" style="background:{cor}"></span>'
                    f'<span title="{_e(selo_alvo.descricao)}">{_e(selo_alvo.rotulo)}</span>'
                )
            else:
                alerta_txt = "—"
            return (
                f"<tr><td>{rotulo}{badge}</td><td>{nome_completo}</td>"
                f"<td>{qtd_txt}</td><td>{preco_txt}</td>"
                f"<td>{formato.percentual(posicao['pct'])}</td><td>{alerta_txt}</td></tr>"
            )

        competencia_pos = formato.competencia_br(posicoes[0]["competencia"]) if posicoes[0].get("competencia") else "—"
        cabecalho = (
            "<thead><tr><th>ativo</th><th>nome</th><th>quantidade</th>"
            "<th>preço hoje</th><th>% da carteira</th><th>alerta</th></tr></thead>"
        )
        topo = "".join(_linha_posicao(p) for p in posicoes[:10])
        cobertura = (dados.get("reprecificacao") or {}).get("cobertura_pct") or 0
        nota_cobertura = (
            f" · <b>{formato.percentual(cobertura)}</b> da carteira já tem preço de hoje na nossa base "
            "(ações/FII/ETF pelo fechamento oficial D-1; títulos públicos e debêntures pelo PU "
            "indicativo da ANBIMA); o restante (exterior/cripto) fica no valor do CDA"
            if cobertura
            else ""
        )
        nota_datada = (
            f"posição informada à CVM na carteira de <b>{competencia_pos}</b> (CDA) — a carteira de hoje "
            f"pode estar diferente{nota_cobertura} · quando o Scout também analisa o ativo (FII, ETF ou "
            "ação), o link leva ao raio-x dele e a coluna <b>alerta</b> mostra o selo daquela página; "
            "“—” = ativo que ainda não cobrimos (renda fixa, exterior)"
        )
        completa = ""
        if len(posicoes) > 10:
            restantes = posicoes[10:]  # o top 10 já está na tabela acima — aqui só o que falta
            linhas_completa = "".join(_linha_posicao(p) for p in restantes)
            completa = f"""
  <details class="carteira-completa">
    <summary>Ver os outros {len(restantes)} ativos ({len(posicoes)} no total)</summary>
    <table class="imoveis">
      {cabecalho}
      <tbody>{linhas_completa}</tbody>
    </table>
  </details>"""
        secao_posicoes = f"""
  <h2>Principais posições</h2>
  <div class="grafico">
  <table class="imoveis">
    {cabecalho}
    <tbody>{topo}</tbody>
  </table>{completa}
  <div class="nota">{nota_datada}</div>
  </div>
"""

    grafico_cotacao = ""
    if dados["cotacao"]:
        svg = graficos.grafico_linhas(
            [("Cotação", dados["cotacao"])],
            formatador=lambda v: f"R$ {formato.decimal(v)}",
        )
        if svg:
            grafico_cotacao = f'<h2>Gráficos</h2><div class="grafico"><h3>Cotação (fechamento oficial B3)</h3>{svg}</div>'

    rentabilidade = ""
    janela_maxima = dados["rentabilidade"].get("máximo") or dados["rentabilidade"].get("12 meses")
    if janela_maxima and "com" in janela_maxima:
        svg = graficos.grafico_linhas(
            janela_maxima["com"], formatador=lambda v: formato.percentual(v)
        )
        if svg:
            rentabilidade = (
                f'<div class="grafico"><h3>Rentabilidade acumulada × CDI × IPCA × IFIX</h3>{svg}'
                '<div class="nota">retorno do preço ajustado (ETFs acumuladores reinvestem os '
                "proventos — o preço JÁ É o retorno total) · índices: Banco Central e B3</div></div>"
            )

    from .html import _COR_SELO, _COR_SEVERIDADE

    selo_html = ""
    if dados.get("selo"):
        cor = _COR_SELO.get(dados["selo"].nivel, "#7C8894")
        selo_html = (
            f'<span class="selo" style="background:{cor}" title="{_e(dados["selo"].descricao)}">'
            f"{_e(dados['selo'].rotulo)}</span>"
        )

    flags_html = ""
    if dados.get("flags"):
        resultado = dados["flags"]
        partes = []
        for flag in resultado.flags:
            cor = _COR_SEVERIDADE[flag.severidade]
            partes.append(
                f'<div class="flag" style="border-left-color:{cor}">'
                f'<span class="sev" style="color:{cor}">{_e(flag.severidade.value)}</span>'
                f"<h3>{_e(flag.titulo)}</h3><p>{_e(flag.fato)}</p>"
                f'<p class="evid">evidência: {_e(flag.evidencia)}</p>'
                f'<p class="fonte">fonte: {_e(flag.fonte)}</p></div>'
            )
        if not partes and resultado.aprovadas:
            partes.append('<p class="ok">✓ nenhum alerta disparado</p>')
        if resultado.aprovadas:
            itens_aprovadas = "".join(f"<li>{_e(texto)}</li>" for texto in resultado.aprovadas)
            partes.append(
                '<p class="ok">✓ Verificações que rodaram e passaram sem alerta:</p>'
                f'<ul class="ok">{itens_aprovadas}</ul>'
            )
        for pendente in resultado.nao_avaliadas:
            partes.append(f'<p class="na">· não avaliada: {_e(pendente)}</p>')
        flags_html = f"<h2>🚩 Red flags</h2>{''.join(partes)}"

    itens_regras = "".join(f"<li>{_e(regra)}</li>" for regra in regras)
    if proventos:
        ultimo = proventos[0]
        itens_regras += (
            f"<li><b>Este fundo é da geração DISTRIBUIDORA:</b> paga renda em dinheiro "
            f"(último provento: R$ {formato.decimal(ultimo['valor'])}/cota em "
            f"{formato.dia_br(ultimo['data_base'])}) — e diferente de FII, o rendimento "
            f"de ETF <b>não é isento de IR</b> (o próprio aviso oficial diz).</li>"
        )
    observacao = (
        f'<div class="nota" style="margin-top:8px">nota da curadoria: {_e(dados["observacoes"])}</div>'
        if dados["observacoes"]
        else ""
    )

    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(etf["ticker"])} — Scout</title>
{TAG_FAVICON}
<style>
:root {{ color-scheme: dark; }}
* {{ box-sizing:border-box; margin:0; }}
body {{ background:#0F1416; color:#EAEEF0; font-family:system-ui,sans-serif; line-height:1.5; }}
.pagina {{ max-width:960px; margin:0 auto; padding:28px 20px 40px; }}
h1 {{ font-family:'Scout Display',system-ui,sans-serif; font-size:28px; font-weight:700; letter-spacing:-.02em; margin:6px 0 2px; }} h1 small {{ color:#9AA7B2; font-size:15px; font-weight:400; }}
h2 {{ font-family:'Scout Display',system-ui,sans-serif; font-size:22px; font-weight:700; letter-spacing:-.01em; margin:26px 0 10px; }}
a {{ color:#8FCB9B; }}
.meta {{ color:#9AA7B2; font-size:13px; }}
.cards {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(170px,1fr)); gap:10px; margin:20px 0; }}
.card {{ background:#161D20; border:1px solid #1B2225; border-radius:10px; padding:12px 14px; }}
.card .nome {{ color:#9AA7B2; font-size:12px; text-transform:uppercase; letter-spacing:.06em; }}
.card .valor {{ font-family:'Scout Display',system-ui,sans-serif; font-size:23px; font-weight:700; letter-spacing:-.01em; margin-top:4px; font-variant-numeric:tabular-nums; }}
.card .valor .compacto {{ font-size:15px; line-height:1.35; display:block; }}
.badge-posicao {{ font-size:9.5px; font-weight:700; letter-spacing:.05em; text-transform:uppercase;
  background:#1B2225; color:#8FCB9B; border:1px solid #263034; border-radius:99px; padding:1px 7px; }}
.ponto-posicao {{ display:inline-block; width:8px; height:8px; border-radius:50%;
  margin-right:6px; vertical-align:middle; }}
.card .extra {{ color:#9AA7B2; font-size:12px; margin-top:2px; }}
.selo {{ display:inline-block; padding:3px 12px; border-radius:999px; font-weight:700;
  font-size:12px; color:#0F1416; white-space:nowrap; vertical-align:middle; }}
.ajuda {{ display:inline-flex; align-items:center; justify-content:center; width:15px; height:15px;
  border-radius:50%; background:#263034; color:#9AA7B2; font-size:10px; font-weight:700;
  cursor:help; position:relative; vertical-align:middle; margin-left:5px; }}
.ajuda .dica {{ visibility:hidden; opacity:0; transition:opacity .15s; position:absolute; z-index:10;
  bottom:135%; left:50%; transform:translateX(-50%); width:270px; background:#1B2225;
  border:1px solid #263034; border-radius:9px; padding:10px 12px; color:#EAEEF0;
  font-size:12.5px; font-weight:400; line-height:1.45; text-transform:none; letter-spacing:0;
  text-align:left; box-shadow:0 6px 20px rgba(0,0,0,.45); white-space:normal; }}
.ajuda:hover .dica, .ajuda:focus .dica {{ visibility:visible; opacity:1; }}
.termo {{ border-bottom:1px dotted #9AA7B2; cursor:help; position:relative; }}
.termo .dica {{ visibility:hidden; opacity:0; transition:opacity .15s; position:absolute; z-index:10;
  bottom:135%; left:50%; transform:translateX(-50%); width:270px; background:#1B2225;
  border:1px solid #263034; border-radius:9px; padding:10px 12px; color:#EAEEF0;
  font-size:12.5px; font-weight:400; line-height:1.45; text-align:left;
  box-shadow:0 6px 20px rgba(0,0,0,.45); white-space:normal; }}
.termo:hover .dica, .termo:focus .dica {{ visibility:visible; opacity:1; }}
.flag {{ background:#161D20; border:1px solid #1B2225; border-left:4px solid; border-radius:10px; padding:14px 16px; margin-bottom:10px; }}
.flag .sev {{ font-size:12px; font-weight:800; letter-spacing:.08em; }}
.flag h3 {{ font-size:16px; margin:2px 0 6px; }}
.flag .evid {{ background:#0F1416; border:1px solid #1B2225; border-radius:7px; padding:6px 10px;
  font-family:ui-monospace,Consolas,monospace; font-size:12.5px; color:#9AA7B2; margin-top:8px; }}
.flag .fonte {{ color:#6B7681; font-size:12px; margin-top:5px; }}
.ok {{ color:#7BD69A; font-size:14px; }} .na {{ color:#9AA7B2; font-size:13px; }}
ul.ok {{ list-style:none; padding-left:6px; }}
ul.ok li {{ color:#9AA7B2; margin:3px 0; }}
ul.ok li::before {{ content:'✓  '; color:#7BD69A; font-weight:700; }}
.regras {{ background:#161D20; border:1px solid #8FCB9B; border-radius:10px; padding:16px 18px; }}
.regras h2 {{ margin:0 0 8px; font-size:16px; color:#8FCB9B; }}
.regras li {{ margin:6px 0 6px 18px; font-size:14px; }}
.grafico {{ background:#161D20; border:1px solid #1B2225; border-radius:10px; padding:14px 16px 10px; margin-bottom:14px; }}
.grafico h3 {{ font-size:15px; color:#9AA7B2; margin-bottom:8px; }}
.grafico .nota, .nota {{ color:#6B7681; font-size:11.5px; }}
table.imoveis {{ width:100%; border-collapse:collapse; font-size:13.5px; font-variant-numeric:tabular-nums; }}
table.imoveis th {{ color:#9AA7B2; font-size:11.5px; text-transform:uppercase; letter-spacing:.05em; text-align:left; padding:6px 10px; border-bottom:1px solid #263034; }}
table.imoveis td {{ padding:7px 10px; border-bottom:1px solid #1B2225; }}
table.imoveis td:not(:first-child), table.imoveis th:not(:first-child) {{ text-align:right; }}
.rodape {{ color:#9AA7B2; font-size:12.5px; border-top:1px solid #1B2225; margin-top:30px; padding-top:14px; }}
{css_menu}
{CSS_MARCA}
</style>
</head>
<body>
<div class="pagina">
  {marca_html("index.html", com_busca_ticker=com_menu)}
  {menu}
  <h1>{_e(etf["ticker"])} <small title="{_e(etf["denominacao"] or "")}">{_e(_trunca(etf["denominacao"] or "", 82))}</small> {selo_html}</h1>
  <div class="meta">ETF · {_e(classe)} · dados oficiais B3 + CVM · página gerada em {agora.strftime("%d/%m/%Y %H:%M")}</div>

  <div class="cards">{"".join(cards)}</div>

  {flags_html}

  {_secao_parecer(leitura)}

  {_secao_ia(leitura, agora)}

  <div class="regras">
  <h2>As regras deste tipo de ETF ({_e(classe)})</h2>
  <ul>{itens_regras or "<li>classe ainda não classificada pela curadoria.</li>"}</ul>
  {observacao}
  </div>

  {composicao}

  {secao_posicoes}

  {grafico_cotacao}
  {rentabilidade}

  <div class="rodape">{_RODAPE}<br>
  Projeto open source: <a href="https://github.com/Ruamms/scout">github.com/Ruamms/scout</a>
  · <a href="etfs.html">todos os ETFs</a> · <a href="index.html">FIIs</a></div>
</div>
<script>
{JS_GRAFICO_HOVER}
{js_menu}
</script>
</body>
</html>
"""
