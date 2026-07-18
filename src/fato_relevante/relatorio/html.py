"""Relatório HTML auto-contido: uma página, zero dependência externa."""

from __future__ import annotations

import html as html_escape
from datetime import datetime
from pathlib import Path

from .. import formato
from ..analise import AnaliseCompleta
from ..modelos import RaioX, Severidade
from . import graficos

_COR_SELO = {
    "sem_alertas": "#22c55e",
    "leves": "#eab308",
    "atencao": "#f97316",
    "grave": "#ef4444",
    "insuficiente": "#94a3b8",
}

_COR_SEVERIDADE = {
    Severidade.ALTA: "#ef4444",
    Severidade.MEDIA: "#f97316",
    Severidade.BAIXA: "#38bdf8",
}

_RODAPE = (
    "Isto não é recomendação de investimento. As informações vêm de fontes públicas "
    "(dados abertos da CVM; cotações via Yahoo Finance) e são apresentadas com a "
    "respectiva evidência. Os critérios de todos os alertas são públicos e auditáveis "
    "no código-fonte."
)


def salvar(completo: AnaliseCompleta, destino: Path, agora: datetime | None = None) -> Path:
    destino.mkdir(parents=True, exist_ok=True)
    caminho = destino / f"{completo.raiox.ticker}.html"
    caminho.write_text(gerar(completo, agora), encoding="utf-8")
    return caminho


def gerar(completo: AnaliseCompleta, agora: datetime | None = None) -> str:
    raiox = completo.raiox
    dados = completo.graficos
    agora = agora or datetime.now()

    secoes_graficos = []
    if dados.cotacao:
        series_linha = [("Cotação", dados.cotacao)]
        if dados.vp_ajustado:
            series_linha.append(("VP/cota (ajustado)", dados.vp_ajustado))
        secoes_graficos.append(
            _card_grafico(
                "Cotação × VP/cota",
                graficos.grafico_linhas(series_linha, formatador=lambda v: f"R$ {formato.decimal(v)}"),
            )
        )
    if dados.pvp:
        secoes_graficos.append(
            _card_grafico(
                "P/VP histórico",
                graficos.grafico_linhas(
                    [("P/VP", dados.pvp)],
                    formatador=lambda v: formato.decimal(v),
                    linha_media=dados.pvp_media,
                ),
            )
        )
    if dados.rentabilidade:
        pct = lambda v: formato.percentual(v)  # noqa: E731
        paineis = [
            (janela, graficos.grafico_linhas(series_janela, formatador=pct))
            for janela, series_janela in dados.rentabilidade.items()
        ]
        secoes_graficos.append(
            _card_grafico_abas(
                "Rentabilidade acumulada (com proventos) × CDI × IPCA",
                paineis,
                nota="fundo: cotação ajustada por proventos (Yahoo); CDI e IPCA: Banco Central (SGS)",
            )
        )
    if dados.dy_por_ano:
        pct = lambda v: formato.percentual(v)  # noqa: E731
        paineis = [("Ano", graficos.grafico_barras(dados.dy_por_ano, formatador=pct))]
        if len(dados.dy_por_mes) >= 6:
            paineis.append(("Mês", graficos.grafico_barras(dados.dy_por_mes, formatador=pct)))
        secoes_graficos.append(
            _card_grafico_abas(
                "Dividend yield (%)",
                paineis,
                nota="* ano parcial · visão mensal: últimos 36 meses",
            )
        )
    if dados.pl_por_ano:
        paineis = [("Ano", graficos.grafico_barras(dados.pl_por_ano, formatador=formato.moeda_compacta))]
        if len(dados.pl_por_mes) >= 6:
            paineis.append(
                ("Mês", graficos.grafico_linhas([("PL", dados.pl_por_mes)], formatador=formato.moeda_compacta))
            )
        secoes_graficos.append(
            _card_grafico_abas("Patrimônio líquido", paineis, nota="* ano parcial")
        )

    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(raiox.ticker)} — Fato Relevante</title>
<style>
:root {{ color-scheme: dark; }}
* {{ box-sizing: border-box; margin: 0; }}
body {{ background:#0b1017; color:#dbe3ec; font-family:system-ui,-apple-system,sans-serif; line-height:1.5; }}
.pagina {{ max-width:960px; margin:0 auto; padding:28px 20px 40px; }}
a {{ color:#5eead4; }}
.topo {{ display:flex; flex-wrap:wrap; align-items:baseline; gap:10px 14px; }}
.marca {{ color:#8b98a9; font-size:14px; letter-spacing:.14em; text-transform:uppercase; }}
h1 {{ font-size:34px; }} h1 small {{ color:#8b98a9; font-size:17px; font-weight:400; }}
.selo {{ display:inline-block; padding:4px 14px; border-radius:999px; font-weight:700; font-size:14px; color:#0b1017; }}
.meta {{ color:#8b98a9; font-size:13px; margin-top:6px; }}
.cards {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(160px,1fr)); gap:10px; margin:22px 0; }}
.card {{ background:#121a24; border:1px solid #1f2a38; border-radius:10px; padding:12px 14px; }}
.card .nome {{ color:#8b98a9; font-size:12px; text-transform:uppercase; letter-spacing:.06em; }}
.card .valor {{ font-size:21px; font-weight:700; margin-top:2px; }}
.card .extra {{ color:#8b98a9; font-size:12px; margin-top:2px; }}
.card.alerta {{ border-color:#eab308; }}
h2 {{ font-size:18px; margin:26px 0 10px; }}
.flag {{ background:#121a24; border:1px solid #1f2a38; border-left:4px solid; border-radius:10px; padding:14px 16px; margin-bottom:10px; }}
.flag .sev {{ font-size:12px; font-weight:800; letter-spacing:.08em; }}
.flag h3 {{ font-size:16px; margin:2px 0 6px; }}
.flag .evid, .flag .fonte {{ color:#8b98a9; font-size:13px; }}
.ok {{ color:#4ade80; font-size:14px; }} .na {{ color:#8b98a9; font-size:13px; }}
ul {{ padding-left:20px; }} li {{ margin:3px 0; }}
.grafico {{ background:#121a24; border:1px solid #1f2a38; border-radius:10px; padding:14px 16px 8px; margin-bottom:14px; }}
.grafico h3 {{ font-size:15px; color:#aeb9c7; margin-bottom:8px; }}
.grafico .nota {{ color:#66707d; font-size:11px; }}
.grafico .cab {{ display:flex; justify-content:space-between; align-items:center; gap:10px; flex-wrap:wrap; }}
.abas button {{ background:#1a2432; color:#8b98a9; border:1px solid #2a3441; border-radius:7px; padding:3px 12px; font-size:12px; cursor:pointer; }}
.abas button.ativo {{ background:#5eead4; color:#0b1017; border-color:#5eead4; font-weight:700; }}
.rodape {{ color:#8b98a9; font-size:12.5px; border-top:1px solid #1f2a38; margin-top:30px; padding-top:14px; }}
@media print {{ body {{ background:#fff; color:#111; }} }}
</style>
</head>
<body>
<div class="pagina">
  <div class="marca">FATO RELEVANTE — o raio-x dos ativos da bolsa</div>
  <div class="topo">
    <h1>{_e(raiox.ticker)} <small>{_e(raiox.nome)}</small></h1>
    {_selo_html(raiox)}
  </div>
  <div class="meta">
    {_e(raiox.cnpj)} · {_e(raiox.classificacao)} · Gestão {_e(raiox.gestao.lower())}<br>
    informes CVM até <b>{_e(raiox.dados_ate)}</b>{_cotacao_em(raiox)} · relatório gerado em {agora.strftime("%d/%m/%Y %H:%M")}
  </div>

  <div class="cards">{_cards_indicadores(raiox)}</div>

  <h2>🚩 Red flags</h2>
  {_secao_flags(raiox)}

  <h2>Gráficos</h2>
  {"".join(secoes_graficos) or '<p class="na">sem séries suficientes para gráficos</p>'}

  <div class="rodape">{_RODAPE}<br>
  Projeto open source: <a href="https://github.com/Ruamms/fato-relevante">github.com/Ruamms/fato-relevante</a>
  · <a href="apoie.html">☕ Apoie o projeto (PIX)</a></div>
</div>
<script>
function mostrar(botao, idPainel) {{
  const card = botao.closest('.grafico');
  card.querySelectorAll('.painel').forEach(p => p.hidden = (p.dataset.painel !== idPainel));
  card.querySelectorAll('.abas button').forEach(b => b.classList.toggle('ativo', b === botao));
}}
</script>
</body>
</html>
"""


def _e(texto: str) -> str:
    return html_escape.escape(str(texto), quote=True)


def _selo_html(raiox: RaioX) -> str:
    if raiox.selo is None:
        return ""
    cor = _COR_SELO.get(raiox.selo.nivel, "#94a3b8")
    return (
        f'<span class="selo" style="background:{cor}" title="{_e(raiox.selo.descricao)}">'
        f"{_e(raiox.selo.rotulo)}</span>"
    )


def _cotacao_em(raiox: RaioX) -> str:
    if not raiox.cotacao_em:
        return ""
    return f" · cotação de <b>{_e(raiox.cotacao_em)}</b>"


def _cards_indicadores(raiox: RaioX) -> str:
    cards = []
    for linha in raiox.indicadores:
        classe = "card alerta" if linha.alerta else "card"
        extra = f"12m: {_e(linha.doze_meses)}" if linha.doze_meses != "—" else ""
        historico = _e(linha.historico) if linha.historico != "—" else ""
        separador = " · " if extra and historico else ""
        cards.append(
            f'<div class="{classe}"><div class="nome">{_e(linha.nome)}'
            f'{" ⚠" if linha.alerta else ""}</div>'
            f'<div class="valor">{_e(linha.atual)}</div>'
            f'<div class="extra">{extra}{separador}{historico}</div></div>'
        )
    return "".join(cards)


def _secao_flags(raiox: RaioX) -> str:
    partes = []
    for flag in raiox.red_flags:
        cor = _COR_SEVERIDADE[flag.severidade]
        partes.append(
            f'<div class="flag" style="border-left-color:{cor}">'
            f'<span class="sev" style="color:{cor}">{_e(flag.severidade.value)}</span>'
            f"<h3>{_e(flag.titulo)}</h3>"
            f"<p>{_e(flag.fato)}</p>"
            f'<p class="evid">evidência: {_e(flag.evidencia)}</p>'
            f'<p class="fonte">fonte: {_e(flag.fonte)}</p></div>'
        )
    if not partes and raiox.red_flags_avaliadas:
        partes.append('<p class="ok">✓ nenhum alerta disparado</p>')
    if raiox.sem_alerta:
        itens = "".join(f"<li>{_e(texto)}</li>" for texto in raiox.sem_alerta)
        partes.append(f'<p class="ok">✓ sem alerta:</p><ul class="ok">{itens}</ul>')
    for nota in raiox.notas:
        partes.append(f'<p class="na">· {_e(nota)}</p>')
    return "".join(partes)


def _card_grafico(titulo: str, svg: str, nota: str = "") -> str:
    rodape = f'<div class="nota">{_e(nota)}</div>' if nota else ""
    return f'<div class="grafico"><h3>{_e(titulo)}</h3>{svg}{rodape}</div>'


def _card_grafico_abas(titulo: str, paineis: list[tuple[str, str]], nota: str = "") -> str:
    """Card com painéis alternáveis (ex.: Ano/Mês) via botões — JS inline mínimo."""
    paineis = [(rotulo, svg) for rotulo, svg in paineis if svg]
    if not paineis:
        return ""
    if len(paineis) == 1:
        return _card_grafico(titulo, paineis[0][1], nota)
    botoes = "".join(
        f'<button class="{"ativo" if indice == 0 else ""}" '
        f"onclick=\"mostrar(this,'{_e(rotulo)}')\">{_e(rotulo)}</button>"
        for indice, (rotulo, _) in enumerate(paineis)
    )
    corpo = "".join(
        f'<div class="painel" data-painel="{_e(rotulo)}"{"" if indice == 0 else " hidden"}>{svg}</div>'
        for indice, (rotulo, svg) in enumerate(paineis)
    )
    rodape = f'<div class="nota">{_e(nota)}</div>' if nota else ""
    return (
        f'<div class="grafico"><div class="cab"><h3>{_e(titulo)}</h3>'
        f'<div class="abas">{botoes}</div></div>{corpo}{rodape}</div>'
    )
