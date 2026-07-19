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
    return {
        "etf": etf,
        "classe": (classificacao.get("classificacao_scout") or "").strip() or None,
        "observacoes": (classificacao.get("observacoes") or "").strip(),
        "gestor": (cadastro["gestor"] if cadastro else None) or (classificacao.get("gestor") or "").strip(),
        "cotacao": cotacao,
        "preco_atual": meta["preco_atual"] if meta else None,
        "cotado_em": meta["cotado_em"] if meta else None,
        "variacao_12m": series.variacao_pct(
            [{"competencia": c, "fechamento": v} for c, v in ajustado], "fechamento", 12
        ),
        "rentabilidade": analise._rentabilidades(cotacao, ajustado, indices),
        "carteira": armazenamento.etf_carteira_atual(con, etf["cnpj"]),
        "pl": armazenamento.etf_pl_atual(con, etf["cnpj"]),
    }


def gerar(dados: dict, agora: datetime | None = None) -> str:
    agora = agora or datetime.now()
    etf = dados["etf"]
    classe = dados["classe"] or "ETF"
    regras = REGRAS_POR_CLASSE.get(dados["classe"] or "", ())

    cards = []

    def _card(nome: str, valor: str, extra: str = "") -> None:
        extra_html = f'<div class="extra">{extra}</div>' if extra else ""
        cards.append(
            f'<div class="card"><div class="nome">{nome}</div>'
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
    _card("Classe (Scout)", _e(classe), _e(f"segmento B3: {etf['tipo_b3']}"))
    if dados["gestor"]:
        _card("Gestora", _e(str(dados["gestor"])[:38]), "")

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

    itens_regras = "".join(f"<li>{_e(regra)}</li>" for regra in regras)
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
body {{ background:#101415; color:#F4F5F6; font-family:system-ui,sans-serif; line-height:1.5; }}
.pagina {{ max-width:960px; margin:0 auto; padding:28px 20px 40px; }}
h1 {{ font-size:26px; margin:6px 0 2px; }} h1 small {{ color:#8b98a9; font-size:15px; font-weight:400; }}
h2 {{ font-size:18px; margin:26px 0 10px; }}
a {{ color:#8FCB9B; }}
.meta {{ color:#8b98a9; font-size:13px; }}
.cards {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(170px,1fr)); gap:10px; margin:20px 0; }}
.card {{ background:#182024; border:1px solid #232D31; border-radius:10px; padding:12px 14px; }}
.card .nome {{ color:#8b98a9; font-size:12px; text-transform:uppercase; letter-spacing:.06em; }}
.card .valor {{ font-size:21px; font-weight:700; margin-top:2px; }}
.card .extra {{ color:#8b98a9; font-size:12px; margin-top:2px; }}
.regras {{ background:#182024; border:1px solid #3E8E7E; border-radius:10px; padding:16px 18px; }}
.regras h2 {{ margin:0 0 8px; font-size:16px; color:#8FCB9B; }}
.regras li {{ margin:6px 0 6px 18px; font-size:14px; }}
.grafico {{ background:#182024; border:1px solid #232D31; border-radius:10px; padding:14px 16px 10px; margin-bottom:14px; }}
.grafico h3 {{ font-size:15px; color:#aeb9c7; margin-bottom:8px; }}
.grafico .nota, .nota {{ color:#66707d; font-size:11.5px; }}
table.imoveis {{ width:100%; border-collapse:collapse; font-size:13.5px; }}
table.imoveis th {{ color:#8b98a9; font-size:11.5px; text-transform:uppercase; letter-spacing:.05em; text-align:left; padding:6px 10px; border-bottom:1px solid #314045; }}
table.imoveis td {{ padding:7px 10px; border-bottom:1px solid #232D31; }}
table.imoveis td:not(:first-child), table.imoveis th:not(:first-child) {{ text-align:right; }}
.rodape {{ color:#8b98a9; font-size:12.5px; border-top:1px solid #232D31; margin-top:30px; padding-top:14px; }}
{CSS_MARCA}
</style>
</head>
<body>
<div class="pagina">
  {marca_html("index.html")}
  <h1>{_e(etf["ticker"])} <small>{_e((etf["denominacao"] or "")[:70])}</small></h1>
  <div class="meta">ETF · {_e(classe)} · dados oficiais B3 + CVM · página gerada em {agora.strftime("%d/%m/%Y %H:%M")}</div>

  <div class="cards">{"".join(cards)}</div>

  <div class="regras">
  <h2>🧭 As regras deste tipo de ETF ({_e(classe)})</h2>
  <ul>{itens_regras or "<li>classe ainda não classificada pela curadoria.</li>"}</ul>
  {observacao}
  </div>

  {composicao}

  {grafico_cotacao}
  {rentabilidade}

  <div class="rodape">{_RODAPE}<br>
  Projeto open source: <a href="https://github.com/Ruamms/scout">github.com/Ruamms/scout</a>
  · <a href="etfs.html">todos os ETFs</a> · <a href="index.html">FIIs</a></div>
</div>
</body>
</html>
"""
