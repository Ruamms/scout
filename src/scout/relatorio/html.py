"""Relatório HTML auto-contido: uma página, zero dependência externa."""

from __future__ import annotations

import html as html_escape
from datetime import datetime
from pathlib import Path

from .. import formato
from ..analise import AnaliseCompleta
from ..modelos import RaioX, Severidade
from . import graficos
from .glossario import TERMOS

_COR_SELO = {
    "sem_alertas": "#22c55e",
    "leves": "#D9B44A",
    "atencao": "#f97316",
    "grave": "#D66A6A",
    "insuficiente": "#94a3b8",
}

_COR_SEVERIDADE = {
    Severidade.ALTA: "#D66A6A",
    Severidade.MEDIA: "#f97316",
    Severidade.BAIXA: "#38bdf8",
}

_RODAPE = (
    "Isto não é recomendação de investimento. As informações vêm de fontes públicas "
    "(dados abertos da CVM; cotações oficiais da B3 — série histórica COTAHIST, com o "
    "fechamento do último pregão) e são apresentadas com a respectiva evidência. Os critérios de "
    "todos os alertas são públicos e auditáveis no código-fonte."
)

# O glifo da marca (bússola do logo) desenhado em SVG: favicon nítido em
# qualquer tamanho, embutido na página — sem arquivo externo.
_SVG_FAVICON = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'>"
    "<circle cx='32' cy='32' r='24' fill='none' stroke='#8FCB9B' stroke-width='5'/>"
    "<polygon points='55,9 40,40 9,55 24,24' fill='#B9E2C1'/>"
    "<circle cx='32' cy='32' r='4' fill='#101415'/>"
    "</svg>"
)
import base64 as _base64  # noqa: E402

FAVICON = "data:image/svg+xml;base64," + _base64.b64encode(_SVG_FAVICON.encode()).decode()
TAG_FAVICON = f'<link rel="icon" href="{FAVICON}">'

_SVG_MARCA = _SVG_FAVICON.replace("<svg ", "<svg width='34' height='34' ")

# CSS do cabeçalho de marca, compartilhado por todas as páginas (site, relatório, apoio)
CSS_MARCA = """
.topo-site { display:flex; align-items:center; gap:14px; flex-wrap:wrap;
  padding-bottom:14px; border-bottom:1px solid #232D31; margin-bottom:20px; }
.brand { display:inline-flex; align-items:center; gap:10px; text-decoration:none; }
.wordmark { font-size:25px; font-weight:800; letter-spacing:.20em; color:#F4F5F6; }
.brand-o { color:#8FCB9B; }
.brand-tag { color:#8b98a9; font-size:11.5px; letter-spacing:.10em; text-transform:uppercase; }
.topo-site input { margin-left:auto; background:#182024; color:#F4F5F6;
  border:1px solid #314045; border-radius:8px; padding:7px 12px; font-size:13.5px; width:250px; }
"""


# CSS + HTML do menu superior com dropdowns (mega-menu), compartilhado pelas
# páginas de navegação (home, fiis, etfs, comparar). HTML/CSS/JS puro — o
# GitHub Pages não impõe limitação nenhuma a menu interativo.
CSS_MENU = """
.nav { display:flex; align-items:center; gap:4px; margin:14px 0 6px; flex-wrap:wrap; }
.nav .item { position:relative; }
.nav .topo-btn { background:none; border:none; color:#aeb9c7; font-size:14.5px; font-weight:600;
  padding:8px 14px; border-radius:8px; cursor:pointer; }
.nav .topo-btn:hover, .nav .item.aberto .topo-btn { background:#182024; color:#8FCB9B; }
.nav .painel { display:none; position:absolute; top:100%; left:0; z-index:40; min-width:230px;
  background:#182024; border:1px solid #314045; border-radius:12px; padding:10px;
  box-shadow:0 14px 40px rgba(0,0,0,.5); }
.nav .item.aberto .painel { display:block; }
.nav .painel a { display:block; color:#F4F5F6; text-decoration:none; font-size:13.5px;
  padding:8px 10px; border-radius:8px; }
.nav .painel a:hover { background:#232D31; color:#8FCB9B; }
.nav .painel .grupo { color:#66707d; font-size:11px; text-transform:uppercase;
  letter-spacing:.06em; padding:6px 10px 2px; }
.nav > a { color:#aeb9c7; font-size:14.5px; font-weight:600; text-decoration:none;
  padding:8px 14px; border-radius:8px; }
.nav > a:hover { background:#182024; color:#8FCB9B; }
"""

JS_MENU = """
document.querySelectorAll('.nav .topo-btn').forEach(botao => {
  botao.addEventListener('click', evento => {
    evento.stopPropagation();
    const item = botao.parentElement;
    const estava = item.classList.contains('aberto');
    document.querySelectorAll('.nav .item').forEach(i => i.classList.remove('aberto'));
    if (!estava) item.classList.add('aberto');
  });
});
document.addEventListener('click', () => {
  document.querySelectorAll('.nav .item').forEach(i => i.classList.remove('aberto'));
});
"""


def menu_html() -> str:
    return """
  <nav class="nav">
    <div class="item">
      <button class="topo-btn" type="button">FIIs ▾</button>
      <div class="painel">
        <a href="fiis.html">Todos os FIIs</a>
        <a href="fiis.html#rankings">Rankings do dia</a>
        <a href="comparar.html">⚖ Comparar FIIs</a>
      </div>
    </div>
    <div class="item">
      <button class="topo-btn" type="button">ETFs ▾</button>
      <div class="painel">
        <a href="etfs.html">Todos os ETFs</a>
        <div class="grupo">por classe</div>
        <a href="etfs.html?classe=Ações Brasil">Ações Brasil</a>
        <a href="etfs.html?classe=Ações Internacionais">Ações Internacionais</a>
        <a href="etfs.html?classe=Renda Fixa">Renda Fixa</a>
        <a href="etfs.html?classe=Cripto">Cripto</a>
      </div>
    </div>
    <a href="apoie.html">☕ Apoie</a>
  </nav>
"""




# busca viva do cabeçalho (mesma experiência da home): dropdown com ticker,
# nome, ponto do selo e badge da classe. O índice vem de busca.json (gerado
# pelo site) — baixado uma vez e cacheado pelo navegador.
CSS_BUSCA_TOPO = """
.busca-topo { position:relative; margin-left:auto; }
.busca-topo input { background:#182024; color:#F4F5F6; border:1px solid #314045;
  border-radius:8px; padding:7px 12px; font-size:13.5px; width:280px; }
#resultados-topo { position:absolute; top:100%; right:0; z-index:45; width:380px; max-width:86vw;
  background:#182024; border:1px solid #314045; border-radius:12px; margin-top:6px;
  overflow:hidden; box-shadow:0 16px 44px rgba(0,0,0,.55); }
#resultados-topo a { display:flex; align-items:center; gap:9px; padding:9px 12px;
  color:#F4F5F6; text-decoration:none; border-bottom:1px solid #232D31; font-size:13.5px; }
#resultados-topo a:last-child { border-bottom:none; }
#resultados-topo a:hover, #resultados-topo a.foco { background:#232D31; }
#resultados-topo .tk { font-weight:800; min-width:64px; }
#resultados-topo .nm { color:#8b98a9; font-size:12px; flex:1; overflow:hidden; white-space:nowrap; text-overflow:ellipsis; }
#resultados-topo .badge { font-size:9.5px; font-weight:700; letter-spacing:.05em; text-transform:uppercase;
  background:#232D31; color:#8FCB9B; border:1px solid #314045; border-radius:99px; padding:2px 8px; white-space:nowrap; }
#resultados-topo .ponto { width:8px; height:8px; border-radius:50%; flex-shrink:0; }
"""

JS_BUSCA_TOPO = """
let _ativosTopo = null;
let _focoTopo = -1;
const CORES_SELO_TOPO = {"sem_alertas": "#22c55e", "leves": "#D9B44A", "atencao": "#f97316", "grave": "#D66A6A", "insuficiente": "#94a3b8"};

async function buscaTopo() {
  const campo = document.getElementById('ir-ticker');
  const caixa = document.getElementById('resultados-topo');
  if (!campo || !caixa) return;
  const termo = campo.value.trim().toLowerCase();
  _focoTopo = -1;
  if (termo.length < 2) { caixa.hidden = true; caixa.innerHTML = ''; return; }
  if (_ativosTopo === null) {
    try { _ativosTopo = await (await fetch('busca.json')).json(); }
    catch (e) { _ativosTopo = []; }
  }
  const achados = _ativosTopo.filter(a =>
    a.t.toLowerCase().includes(termo) || a.n.toLowerCase().includes(termo) || a.c.toLowerCase().includes(termo)
  ).slice(0, 8);
  if (window.scoutBusca) scoutBusca(termo, achados.length > 0);
  if (!achados.length) { caixa.hidden = true; caixa.innerHTML = ''; return; }
  caixa.innerHTML = achados.map(a =>
    `<a href="${a.t}.html"><span class="tk">${a.t}</span><span class="nm">${a.n}</span>` +
    (a.s ? `<span class="ponto" style="background:${CORES_SELO_TOPO[a.s] || '#94a3b8'}" title="${a.r}"></span>` : '') +
    `<span class="badge">${a.c}</span></a>`
  ).join('');
  caixa.hidden = false;
}

function navegaTopo(evento) {
  const caixa = document.getElementById('resultados-topo');
  const links = caixa && !caixa.hidden ? caixa.querySelectorAll('a[href]') : [];
  if (evento.key === 'Enter') {
    evento.preventDefault();
    if (links.length) { links[Math.max(_focoTopo, 0)].click(); return; }
    const ticker = evento.target.value.trim().toUpperCase();
    if (ticker) location.href = ticker + '.html';
  } else if ((evento.key === 'ArrowDown' || evento.key === 'ArrowUp') && links.length) {
    evento.preventDefault();
    _focoTopo = (_focoTopo + (evento.key === 'ArrowDown' ? 1 : -1) + links.length) % links.length;
    links.forEach((l, i) => l.classList.toggle('foco', i === _focoTopo));
  } else if (evento.key === 'Escape' && caixa) {
    caixa.hidden = true;
  }
}
"""


def analytics_script(codigo: str | None) -> str:
    """Snippet de analytics sem cookie (GoatCounter) para injetar no <head>.

    Vazio quando não há código configurado — build local e testes ficam sem
    rede e sem rastreio. Além da contagem de páginas vistas, define
    `window.scoutBusca(termo, temResultado)`: registra O QUE as pessoas
    pesquisam como evento ANÔNIMO e agregado (nunca ligado a identidade),
    sanitizado a [A-Z0-9] (só o formato de ticker; texto livre é descartado)
    e com debounce (as teclas intermediárias colapsam num evento só). A busca
    SEM resultado vira um caminho próprio — é a demanda que ainda não cobrimos.
    """
    codigo = (codigo or "").strip()
    if not codigo:
        return ""
    url = f"https://{codigo}.goatcounter.com/count"
    return (
        f'<script data-goatcounter="{url}" async src="//gc.zgo.at/count.js"></script>\n'
        "<script>(function(){var t=null;window.scoutBusca=function(termo,tem){"
        "var q=(termo||'').toUpperCase().replace(/[^A-Z0-9]/g,'').slice(0,12);"
        "if(q.length<2)return;clearTimeout(t);t=setTimeout(function(){"
        "if(!window.goatcounter||!window.goatcounter.count)return;"
        "window.goatcounter.count({path:(tem?'busca/':'busca-vazia/')+q,"
        "title:tem?'Busca':'Busca sem resultado',event:true});},1200);};})();</script>"
    )


def marca_html(inicio_href: str | None = None, com_busca_ticker: bool = False) -> str:
    """Cabeçalho de marca (bússola + SCOUT + tagline), como manda a vitrine."""
    conteudo = (
        f"{_SVG_MARCA}"
        '<span class="wordmark">SC<span class="brand-o">O</span>UT</span>'
    )
    if inicio_href:
        marca = f'<a class="brand" href="{inicio_href}" title="todos os fundos">{conteudo}</a>'
    else:
        marca = f'<span class="brand">{conteudo}</span>'
    tagline = (
        '<span class="brand-tag">nós exploramos. '
        '<span class="brand-o">você decide.</span></span>'
    )
    busca = (
        '<div class="busca-topo">'
        '<input id="ir-ticker" placeholder="buscar um fundo… (ex.: HGLG11)" autocomplete="off" '
        'oninput="buscaTopo()" onkeydown="navegaTopo(event)">'
        '<div id="resultados-topo" hidden></div></div>'
        if com_busca_ticker
        else ""
    )
    return f'<header class="topo-site">{marca}{tagline}{busca}</header>'


def salvar(
    completo: AnaliseCompleta,
    destino: Path,
    agora: datetime | None = None,
    publicados: set[str] | None = None,
    leitura: dict | None = None,
) -> Path:
    destino.mkdir(parents=True, exist_ok=True)
    caminho = destino / f"{completo.raiox.ticker}.html"
    caminho.write_text(gerar(completo, agora, publicados, leitura), encoding="utf-8")
    return caminho


def gerar(
    completo: AnaliseCompleta,
    agora: datetime | None = None,
    publicados: set[str] | None = None,
    leitura: dict | None = None,
) -> str:
    """`publicados` = tickers com página no site: liga a navegação entre
    páginas e evita links mortos (None = relatório local avulso).
    `leitura` = leitura por IA persistida (leituras/<TICKER>.json)."""
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
    if dados.vacancia:
        pct = lambda v: formato.percentual(v)  # noqa: E731
        paineis_vacancia = [
            ("Histórico", graficos.grafico_linhas([("Vacância", dados.vacancia)], formatador=pct))
        ]
        if len(dados.vacancia) > 12:
            paineis_vacancia.insert(
                0,
                (
                    "3 anos",
                    graficos.grafico_linhas(
                        [("Vacância", dados.vacancia[-12:])],
                        formatador=pct,
                        valores_nos_pontos=True,
                    ),
                ),
            )
        secoes_graficos.append(
            _card_grafico_abas(
                "Vacância (%)",
                paineis_vacancia,
                nota=(
                    "vacância física ponderada pela área dos imóveis, por trimestre "
                    "(dado trimestral da CVM — não existe abertura mensal) · "
                    "no histórico completo, o valor de cada ponto aparece ao passar o mouse"
                ),
                chave_ajuda="Vacância (%)",
            )
        )
    if dados.rentabilidade:
        secoes_graficos.append(_card_rentabilidade(dados))
    if dados.dy_por_ano:
        pct = lambda v: formato.percentual(v)  # noqa: E731
        rs = lambda v: f"≈ R$ {formato.decimal(v)}" if v is not None else None  # noqa: E731
        paineis = [
            (
                "Ano",
                graficos.grafico_barras(
                    dados.dy_por_ano, formatador=pct, extras=[rs(v) for v in dados.rend_por_ano]
                ),
            )
        ]
        if len(dados.dy_por_mes) >= 6:
            paineis.append(
                (
                    "Mês",
                    graficos.grafico_barras(
                        dados.dy_por_mes, formatador=pct, extras=[rs(v) for v in dados.rend_por_mes]
                    ),
                )
            )
        secoes_graficos.append(
            _card_grafico_abas(
                "Dividend yield (%)",
                paineis,
                nota=(
                    "* ano parcial · visão mensal: últimos 12 meses · "
                    "≈ R$ = rendimento por cota estimado (DY informado à CVM × VP ajustado da cota, "
                    "na base de cotas atual)"
                ),
            )
        )
    if dados.pl_por_ano:
        paineis = [("Ano", graficos.grafico_barras(dados.pl_por_ano, formatador=formato.moeda_compacta))]
        if len(dados.pl_por_mes) >= 6:
            paineis.append(
                (
                    "Mês",
                    graficos.grafico_linhas(
                        [("PL", dados.pl_por_mes[-12:])],
                        formatador=formato.moeda_compacta,
                        valores_nos_pontos=True,
                    ),
                )
            )
        secoes_graficos.append(
            _card_grafico_abas(
                "Patrimônio líquido",
                paineis,
                nota="* ano parcial · visão mensal: últimos 12 meses",
                chave_ajuda="Patrimônio líquido (gráfico)",
            )
        )

    secao_calculadoras = _secao_calculadoras(completo)
    # fundo sem cotação/rendimento não tem calculadoras — o botão do topo
    # só existe quando a âncora existe
    botao_calculadoras = (
        '<a class="btn-topo" href="#calculadoras">🧮 Calculadoras</a>'
        if secao_calculadoras
        else ""
    )

    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(raiox.ticker)} — Scout</title>
{TAG_FAVICON}
<style>
:root {{ color-scheme: dark; }}
html {{ scroll-behavior: smooth; }}
* {{ box-sizing: border-box; margin: 0; }}
body {{ background:#101415; color:#F4F5F6; font-family:system-ui,-apple-system,sans-serif; line-height:1.5; }}
.pagina {{ max-width:960px; margin:0 auto; padding:28px 20px 40px; }}
a {{ color:#8FCB9B; }}
.topo {{ display:flex; flex-wrap:wrap; align-items:baseline; gap:10px 14px; }}
.marca {{ color:#8b98a9; font-size:14px; letter-spacing:.14em; text-transform:uppercase; }}
h1 {{ font-size:34px; }} h1 small {{ color:#8b98a9; font-size:17px; font-weight:400; }}
.selo {{ display:inline-block; padding:4px 14px; border-radius:999px; font-weight:700; font-size:14px; color:#101415; white-space:nowrap; }}
.btn-topo {{ margin-left:auto; background:#232D31; border:1px solid #314045; color:#8FCB9B; text-decoration:none; padding:6px 14px; border-radius:8px; font-size:13px; font-weight:600; }}
.btn-topo:hover {{ border-color:#8FCB9B; }}
.nav-site {{ display:flex; gap:12px; align-items:center; flex-wrap:wrap; margin-top:12px; }}
.nav-site a {{ color:#8FCB9B; text-decoration:none; font-size:13.5px; font-weight:600; }}
.nav-site input {{ background:#182024; color:#F4F5F6; border:1px solid #314045; border-radius:8px;
  padding:7px 12px; font-size:13.5px; width:280px; }}
.meta {{ color:#8b98a9; font-size:13px; margin-top:6px; }}
.cards {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(160px,1fr)); gap:10px; margin:22px 0; }}
.card {{ background:#182024; border:1px solid #232D31; border-radius:10px; padding:12px 14px; }}
.card .nome {{ color:#8b98a9; font-size:12px; text-transform:uppercase; letter-spacing:.06em; }}
.card .valor {{ font-size:21px; font-weight:700; margin-top:2px; }}
.card .extra {{ color:#8b98a9; font-size:12px; margin-top:2px; }}
.card.alerta {{ border-color:#D9B44A; }}
h2 {{ font-size:18px; margin:26px 0 10px; }}
.flag {{ background:#182024; border:1px solid #232D31; border-left:4px solid; border-radius:10px; padding:14px 16px; margin-bottom:10px; }}
.flag .sev {{ font-size:12px; font-weight:800; letter-spacing:.08em; }}
.flag h3 {{ font-size:16px; margin:2px 0 6px; }}
.flag .evid {{ background:#101415; border:1px solid #232D31; border-radius:7px; padding:6px 10px;
  font-family:ui-monospace,Consolas,monospace; font-size:12.5px; color:#aeb9c7; margin-top:8px; }}
.flag .fonte {{ color:#66707d; font-size:12px; margin-top:5px; }}
.ok {{ color:#4ade80; font-size:14px; }} .na {{ color:#8b98a9; font-size:13px; }}
ul {{ padding-left:20px; }} li {{ margin:3px 0; }}
ul.ok {{ list-style:none; padding-left:6px; }}
ul.ok li {{ color:#8b98a9; }}
ul.ok li::before {{ content:'✓  '; color:#4ade80; font-weight:700; }}
.grafico {{ background:#182024; border:1px solid #232D31; border-radius:10px; padding:14px 16px 8px; margin-bottom:14px; }}
.grafico h3 {{ font-size:15px; color:#aeb9c7; margin-bottom:8px; }}
.grafico .nota {{ color:#66707d; font-size:11px; }}
.grafico .cab {{ display:flex; justify-content:space-between; align-items:center; gap:10px; flex-wrap:wrap; }}
.abas button {{ background:#232D31; color:#8b98a9; border:1px solid #314045; border-radius:7px; padding:3px 12px; font-size:12px; cursor:pointer; }}
.abas button.ativo {{ background:#8FCB9B; color:#101415; border-color:#8FCB9B; font-weight:700; }}
.ajuda {{ display:inline-flex; align-items:center; justify-content:center; width:15px; height:15px;
  border-radius:50%; background:#314045; color:#8b98a9; font-size:10px; font-weight:700;
  cursor:help; position:relative; vertical-align:middle; margin-left:5px; }}
.ajuda .dica, .termo .dica {{ visibility:hidden; opacity:0; transition:opacity .15s; position:absolute; z-index:10;
  bottom:135%; left:50%; transform:translateX(-50%); width:270px; background:#232D31;
  border:1px solid #314045; border-radius:9px; padding:10px 12px; color:#F4F5F6;
  font-size:12.5px; font-weight:400; line-height:1.45; text-transform:none; letter-spacing:0;
  text-align:left; box-shadow:0 6px 20px rgba(0,0,0,.45); white-space:normal; }}
.ajuda:hover .dica, .ajuda:focus .dica, .termo:hover .dica, .termo:focus .dica {{ visibility:visible; opacity:1; }}
.termo {{ border-bottom:1px dotted #8b98a9; cursor:help; position:relative; }}
.calc {{ background:#182024; border:1px solid #232D31; border-radius:10px; padding:16px; margin-bottom:14px; }}
.calc h3 {{ font-size:15px; color:#aeb9c7; margin-bottom:4px; }}
.calc .desc {{ color:#8b98a9; font-size:13px; margin-bottom:12px; }}
.calc .campos {{ display:flex; flex-wrap:wrap; gap:10px; align-items:end; }}
.calc label {{ display:block; color:#8b98a9; font-size:11.5px; text-transform:uppercase; letter-spacing:.05em; margin-bottom:3px; }}
.calc input[type=number] {{ background:#101415; color:#F4F5F6; border:1px solid #314045; border-radius:8px; padding:8px 10px; width:130px; font-size:15px; }}
.calc select {{ background:#101415; color:#F4F5F6; border:1px solid #314045; border-radius:8px; padding:8px 10px; font-size:15px; }}
.calc .check {{ display:flex; align-items:center; gap:6px; color:#aeb9c7; font-size:13px; padding-bottom:8px; }}
.calc .resultado {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(170px,1fr)); gap:10px; margin-top:14px; }}
.calc .res {{ background:#101415; border:1px solid #232D31; border-radius:9px; padding:10px 12px; }}
.calc .res .rotulo {{ color:#8b98a9; font-size:11.5px; text-transform:uppercase; letter-spacing:.05em; }}
.calc .res .num {{ font-size:19px; font-weight:700; margin-top:2px; color:#8FCB9B; }}
.calc .aviso {{ color:#66707d; font-size:11.5px; margin-top:10px; }}
table.imoveis {{ width:100%; border-collapse:collapse; font-size:13.5px; }}
table.imoveis th {{ color:#8b98a9; font-size:11.5px; text-transform:uppercase; letter-spacing:.05em; text-align:left; padding:6px 10px; border-bottom:1px solid #314045; }}
table.imoveis td {{ padding:7px 10px; border-bottom:1px solid #232D31; }}
table.imoveis tbody tr:hover td {{ background:#1d262b; }}
table.imoveis td:not(:first-child), table.imoveis th:not(:first-child) {{ text-align:right; }}
.ver-mais {{ background:#232D31; color:#8FCB9B; border:1px solid #314045; border-radius:8px;
  padding:6px 16px; font-size:13px; font-weight:600; cursor:pointer; margin-top:10px; }}
.ver-mais:hover {{ border-color:#8FCB9B; }}
.rodape {{ color:#8b98a9; font-size:12.5px; border-top:1px solid #232D31; margin-top:30px; padding-top:14px; }}
{CSS_MENU if publicados is not None else ""}
{CSS_MARCA}
{CSS_BUSCA_TOPO if publicados is not None else ""}
@media print {{ body {{ background:#fff; color:#111; }} }}
</style>
</head>
<body>
<div class="pagina">
  {marca_html("index.html" if publicados is not None else None, com_busca_ticker=publicados is not None)}
  {menu_html() if publicados is not None else ""}
  <div class="topo">
    <h1>{_e(raiox.ticker)} <small>{_e(raiox.nome)}</small></h1>
    {_selo_html(raiox)}
    {botao_calculadoras}
  </div>
  <div class="meta">
    {_e(raiox.cnpj)} · {_e(raiox.classificacao)} · Gestão {_e(raiox.gestao.lower())}<br>
    informes CVM até <b>{_e(raiox.dados_ate)}</b>{_cotacao_em(raiox, agora)} · relatório gerado em {agora.strftime("%d/%m/%Y %H:%M")}
  </div>

  <div class="cards">{_cards_indicadores(raiox)}</div>

  <h2>🚩 Red flags{_ajuda("Red flags")}</h2>
  {_secao_flags(raiox)}

  {_secao_parecer(leitura)}

  {_secao_imoveis(raiox)}

  {_secao_administrador(raiox, publicados=publicados)}

  {_secao_gestora(raiox, publicados=publicados)}

  {_secao_pares(raiox, publicados=publicados)}

  {_secao_oscilacoes(completo, leitura)}

  {_secao_ia(leitura, agora, completo)}

  <h2>Gráficos</h2>
  {"".join(secoes_graficos) or '<p class="na">sem séries suficientes para gráficos</p>'}

  {secao_calculadoras}

  <div class="rodape">{_RODAPE}<br>
  Projeto open source: <a href="https://github.com/Ruamms/scout">github.com/Ruamms/scout</a>
  · <a href="apoie.html">☕ Apoie o projeto (PIX)</a></div>
</div>
<script>
function mostrar(botao, idPainel) {{
  const card = botao.closest('.grafico');
  card.querySelectorAll('.painel').forEach(p => p.hidden = (p.dataset.painel !== idPainel));
  card.querySelectorAll('.abas button').forEach(b => b.classList.toggle('ativo', b === botao));
}}

const brl = v => v.toLocaleString('pt-BR', {{style: 'currency', currency: 'BRL', maximumFractionDigits: 0}});
const num = id => parseFloat(document.getElementById(id).value) || 0;
const põe = (id, texto) => document.getElementById(id).textContent = texto;

function calcUmaCota() {{
  const preco = num('uc-preco'), rend = num('uc-rend');
  if (preco <= 0 || rend <= 0) {{ põe('uc-cotas', '—'); põe('uc-invest', '—'); return; }}
  const cotas = Math.ceil(preco / rend);
  põe('uc-cotas', cotas.toLocaleString('pt-BR'));
  põe('uc-invest', brl(cotas * preco));
}}

function calcAportes() {{
  const inicial = num('pa-inicial'), mensal = num('pa-mensal');
  const meses = Math.round(num('pa-anos') * 12), taxa = num('pa-taxa') / 100;
  const reinvestir = document.getElementById('pa-reinvestir').checked;
  let saldo = inicial, rendimentos = 0;
  for (let m = 0; m < meses; m++) {{
    const rendeu = saldo * taxa;
    rendimentos += rendeu;
    if (reinvestir) saldo += rendeu;
    saldo += mensal;
  }}
  const aportado = inicial + mensal * meses;
  põe('pa-aportado', brl(aportado));
  põe('pa-final', brl(reinvestir ? saldo : aportado));
  põe('pa-rendimentos', brl(rendimentos));
  põe('pa-renda', brl((reinvestir ? saldo : aportado) * taxa));
}}

function calcGordon() {{
  const el = document.getElementById('gd-justo');
  if (!el) return;
  const d = num('gd-div'), r = num('gd-r') / 100, g = num('gd-g') / 100;
  if (d <= 0 || r <= g) {{ el.textContent = (r <= g ? 'r precisa ser > g' : '—'); return; }}
  el.textContent = (d * (1 + g) / (r - g)).toLocaleString('pt-BR', {{style: 'currency', currency: 'BRL', minimumFractionDigits: 2}});
}}

function abrirGordon(botao) {{
  botao.hidden = true;
  botao.nextElementSibling.hidden = false;
  calcGordon();
}}

function janelaRent(botao, janela) {{
  const card = document.getElementById('card-rent');
  card.dataset.janela = janela;
  card.querySelectorAll('.abas button').forEach(b => b.classList.toggle('ativo', b === botao));
  atualizaRent();
}}

function atualizaRent() {{
  const card = document.getElementById('card-rent');
  if (!card) return;
  const modo = document.getElementById('rent-reinvestir').checked ? 'com' : 'sem';
  const alvo = card.dataset.janela + '|' + modo;
  card.querySelectorAll('.painel').forEach(p => p.hidden = (p.dataset.painel !== alvo));
}}

function irTicker(evento, campo) {{
  if (evento.key !== 'Enter') return;
  const ticker = campo.value.trim().toUpperCase();
  if (ticker) location.href = ticker + '.html';
}}

function verMais(botao, classe) {{
  const card = botao.closest('.grafico');
  const abertas = botao.textContent === botao.dataset.menos;
  card.querySelectorAll('.' + classe).forEach(tr => tr.hidden = abertas);
  botao.textContent = abertas ? botao.dataset.mais : botao.dataset.menos;
}}

function calcRetro() {{
  if (typeof RETRO === 'undefined') return;
  const valor = num('rt-valor');
  const janela = document.getElementById('rt-janela').value;
  const modo = document.getElementById('rt-reinvestir').checked ? 'com' : 'sem';
  const series = (RETRO[janela] || {{}})[modo] || {{}};
  const alvo = document.getElementById('rt-resultado');
  alvo.innerHTML = Object.entries(series).map(([nome, pct]) =>
    `<div class="res"><div class="rotulo">${{nome === 'Fundo' ? 'no fundo' : 'no ' + nome}}</div>` +
    `<div class="num">${{brl(valor * (1 + pct / 100))}}</div>` +
    `<div class="rotulo">${{pct >= 0 ? '+' : ''}}${{pct.toLocaleString('pt-BR', {{maximumFractionDigits: 2}})}}%</div></div>`
  ).join('');
}}

if (document.getElementById('uc-preco')) {{ calcUmaCota(); calcAportes(); }}
if (document.getElementById('rt-valor')) {{ calcRetro(); }}
{(JS_MENU + JS_BUSCA_TOPO) if publicados is not None else ""}
</script>
</body>
</html>
"""


def _e(texto: str) -> str:
    return html_escape.escape(str(texto), quote=True)


def _link_se_publicado(ticker: str, publicados: set[str] | None) -> str:
    """Link para a página do ticker apenas quando ela existe no site."""
    if publicados is not None and ticker not in publicados:
        return _e(ticker)
    return f'<a href="{_e(ticker)}.html">{_e(ticker)}</a>'


def _selo_html(raiox: RaioX) -> str:
    if raiox.selo is None:
        return ""
    cor = _COR_SELO.get(raiox.selo.nivel, "#94a3b8")
    return (
        f'<span class="selo" style="background:{cor}" title="{_e(raiox.selo.descricao)}">'
        f"{_e(raiox.selo.rotulo)}</span>"
    )


def _cotacao_em(raiox: RaioX, agora: datetime) -> str:
    if not raiox.cotacao_em:
        return ""
    idade = formato.idade_legivel(raiox.cotado_em_iso, agora)
    if not idade:
        return f" · cotação de <b>{_e(raiox.cotacao_em)}</b>"
    defasada = "dia" in idade  # mais de 48h: fim de semana/feriado/cache antigo
    cor = "#D9B44A" if defasada else "#8b98a9"
    aviso = " ⚠" if defasada else ""
    return (
        f" · cotação de <b>{_e(raiox.cotacao_em)}</b> "
        f'<span style="color:{cor};cursor:help" title="Idade do preço usado: {_e(idade)}. '
        "Cotação, P/VP e oscilações refletem esse momento — o preço é o fechamento OFICIAL "
        f'do último pregão da B3 (D-1).">({_e(idade)}){aviso}</span>'
    )


def _ajuda(termo: str) -> str:
    """Ícone '?' com a explicação do glossário (hover/toque); vazio se não houver."""
    texto = TERMOS.get(termo)
    if not texto:
        return ""
    return f'<span class="ajuda" tabindex="0">?<span class="dica">{_e(texto)}</span></span>'


def _cards_indicadores(raiox: RaioX) -> str:
    cards = []
    for linha in raiox.indicadores:
        classe = "card alerta" if linha.alerta else "card"
        # cada informação em sua própria linha, com rótulo por extenso
        detalhes = []
        if linha.doze_meses != "—":
            detalhes.append(f"em 12 meses: {linha.doze_meses}")
        if linha.historico != "—":
            historico = linha.historico
            if historico.startswith("média "):
                historico = "média histórica: " + historico[len("média "):]
            elif historico.endswith(" no ano"):
                historico = "no ano: " + historico[: -len(" no ano")]
            detalhes.append(historico)
        extra = "".join(f'<div class="extra">{_e(texto)}</div>' for texto in detalhes)
        aviso = ""
        if linha.alerta:
            motivo = linha.alerta_motivo or "ver a seção Red flags"
            aviso = f' <span style="cursor:help" title="Alerta: {_e(motivo)}">⚠</span>'
        cards.append(
            f'<div class="{classe}"><div class="nome">{_e(linha.nome)}'
            f"{aviso}{_ajuda(linha.nome)}</div>"
            f'<div class="valor">{_e(linha.atual)}</div>{extra}</div>'
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
        partes.append(
            '<p class="ok">✓ Verificações que rodaram e passaram sem alerta:</p>'
            f'<ul class="ok">{itens}</ul>'
        )
    for nota in raiox.notas:
        partes.append(f'<p class="na">· {_e(nota)}</p>')
    return "".join(partes)


def _secao_imoveis(raiox: RaioX, limite: int = 10) -> str:
    if not raiox.imoveis:
        return ""

    def _pct(valor: float | None) -> str:
        return formato.percentual(valor) if valor is not None else "—"

    linhas = []
    for indice, imovel in enumerate(raiox.imoveis):
        area = f"{formato.decimal(imovel.area, 0)} m²" if imovel.area else "—"
        oculta = ' class="imovel-extra" hidden' if indice >= limite else ""
        linhas.append(
            f"<tr{oculta}><td>{_e(imovel.nome)}</td><td>{area}</td>"
            f"<td>{_pct(imovel.pct_receita)}</td><td>{_pct(imovel.vacancia)}</td>"
            f"<td>{_pct(imovel.inadimplencia)}</td></tr>"
        )
    botao = ""
    if len(raiox.imoveis) > limite:
        botao = (
            f'<button class="ver-mais" onclick="verMais(this, \'imovel-extra\')" '
            f'data-mais="ver todos os {len(raiox.imoveis)} imóveis" data-menos="mostrar menos">'
            f"ver todos os {len(raiox.imoveis)} imóveis</button>"
        )
    return f"""
  <h2>Imóveis ({len(raiox.imoveis)}){_ajuda("Imóveis")}</h2>
  <div class="grafico" style="overflow-x:auto">
  <table class="imoveis">
    <thead><tr><th>imóvel</th><th>área</th><th>% da receita</th><th>vacância</th><th>inadimplência</th></tr></thead>
    <tbody>{"".join(linhas)}</tbody>
  </table>
  {botao}
  {_linha_estados(raiox)}
  {_linha_setores(raiox)}
  <div class="nota">informe trimestral de {_e(raiox.imoveis_em)} · ordenados por participação na receita</div>
  </div>
"""


def _linha_setores(raiox: RaioX) -> str:
    """Receita do fundo por setor de atuação dos inquilinos (informe trimestral)."""
    setores = [(setor, pct) for setor, pct in raiox.setores_inquilinos if pct >= 0.5]
    if not setores:
        return ""
    partes = " · ".join(f"<b>{_e(setor)}</b> {formato.percentual(pct)}" for setor, pct in setores[:8])
    return (
        f'<div class="nota" style="margin-top:6px">receita por setor de inquilino: {partes}</div>'
    )


def _linha_estados(raiox: RaioX) -> str:
    """Distribuição da área por estado (UF estimada pelo endereço do informe)."""
    estados = [(uf, pct) for uf, pct in raiox.imoveis_por_estado if uf != "?"]
    if not estados:
        return ""
    nao_identificado = next((pct for uf, pct in raiox.imoveis_por_estado if uf == "?"), 0)
    partes = " · ".join(f"<b>{_e(uf)}</b> {formato.percentual(pct)}" for uf, pct in estados[:8])
    resto = f" · não identificado {formato.percentual(nao_identificado)}" if nao_identificado >= 1 else ""
    return (
        f'<div class="nota" style="margin-top:8px">área por estado (estimada pelo endereço): '
        f"{partes}{resto}</div>"
    )


def _tabela_relacionados(
    titulo_html: str,
    descricao_html: str,
    relacionados: list,
    classe_extra: str,
    limite: int,
    publicados: set[str] | None,
) -> str:
    """Tabela de fundos ligados à mesma instituição (administrador ou gestora)."""
    linhas = []
    for indice, irmao in enumerate(relacionados):
        selo = _selo_tabela(irmao.selo, irmao.motivos)
        rotulo = (
            _link_se_publicado(irmao.ticker, publicados)
            if irmao.ticker
            else _e(irmao.nome[:40])
        )
        idade = f"{irmao.anos:.0f} anos" if irmao.anos >= 1 else "&lt;1 ano"
        taxa = f"{formato.percentual(irmao.taxa)} a.a." if irmao.taxa is not None else "—"
        oculta = f' class="{classe_extra}" hidden' if indice >= limite else ""
        linhas.append(
            f"<tr{oculta}><td>{rotulo}</td><td>{_e(irmao.nome[:44])}</td>"
            f'<td style="white-space:nowrap">{idade}</td>'
            f"<td>{_e(irmao.segmento)}</td>"
            f'<td style="white-space:nowrap">{taxa}</td><td>{selo}</td></tr>'
        )
    botao = ""
    if len(relacionados) > limite:
        botao = (
            f'<button class="ver-mais" onclick="verMais(this, \'{classe_extra}\')" '
            f'data-mais="ver todos os {len(relacionados)} fundos" data-menos="mostrar menos">'
            f"ver todos os {len(relacionados)} fundos</button>"
        )
    return f"""
  <h2>{titulo_html}</h2>
  <div class="grafico" style="overflow-x:auto">
  <p class="desc" style="color:#aeb9c7;font-size:13.5px;margin-bottom:10px">{descricao_html}</p>
  <table class="imoveis">
    <thead><tr><th>ticker</th><th>fundo</th><th>idade</th><th>segmento</th><th>taxa</th><th>selo</th></tr></thead>
    <tbody>{"".join(linhas)}</tbody>
  </table>
  {botao}
  <div class="nota">taxa de administração efetiva (média dos últimos 12 meses, dado da CVM) ·
  selo calculado sem cotação de bolsa (P/VP fora) · passe o mouse no selo para
  ver o motivo · o link abre o relatório do fundo se ele já tiver sido gerado · ticker derivado do ISIN</div>
  </div>
"""


def _secao_administrador(
    raiox: RaioX, limite: int = 12, publicados: set[str] | None = None
) -> str:
    if not raiox.fundos_irmaos:
        return ""
    complemento = " — que também é a gestora do fundo" if raiox.gestora_e_admin else ""
    return _tabela_relacionados(
        f'Administrador{_ajuda("Administrador")}',
        f"<b>{_e(raiox.administrador)}</b>{complemento} administra outros "
        f"{len(raiox.fundos_irmaos)} FIIs na base da CVM:",
        raiox.fundos_irmaos,
        "admin-extra",
        limite,
        publicados,
    )


def _secao_gestora(
    raiox: RaioX, limite: int = 12, publicados: set[str] | None = None
) -> str:
    """Fundos da mesma gestora — quem decide a estratégia. Quando gestora e
    administrador são a mesma instituição, a seção do administrador já conta
    a história e esta é omitida."""
    if not raiox.gestora or raiox.gestora_e_admin:
        return ""
    if not raiox.fundos_gestora:
        return f"""
  <h2>Gestora{_ajuda("Gestora")}</h2>
  <div class="grafico"><div class="nota" style="font-size:13px"><b>{_e(raiox.gestora)}</b>
  é a gestora deste fundo (cadastro CVM) e não gere nenhum outro FII na base — fundo único da casa.</div></div>
"""
    return _tabela_relacionados(
        f'Gestora{_ajuda("Gestora")}',
        f"<b>{_e(raiox.gestora)}</b> é a gestora deste fundo (cadastro CVM) e gere outros "
        f"{len(raiox.fundos_gestora)} FIIs:",
        raiox.fundos_gestora,
        "gestora-extra",
        limite,
        publicados,
    )


def _selo_tabela(selo, motivos: tuple[str, ...]) -> str:
    """Selo compacto para tabelas, com o MOTIVO no tooltip."""
    if selo is None:
        return "—"
    cor = _COR_SELO.get(selo.nivel, "#94a3b8")
    dica = "Alertas: " + "; ".join(motivos) if motivos else selo.descricao
    return (
        f'<span class="selo" style="background:{cor};font-size:11px;padding:2px 10px" '
        f'title="{_e(dica)}">{_e(selo.rotulo)}</span>'
    )


def _secao_pares(raiox: RaioX, publicados: set[str] | None = None) -> str:
    if not raiox.pares:
        return ""

    def _celula(valor, formatador):
        return formatador(valor) if valor is not None else "—"

    linhas = []
    for par in raiox.pares:
        rotulo = (
            _link_se_publicado(par.ticker, publicados) if par.ticker else _e(par.nome[:30])
        )
        linhas.append(
            f"<tr><td>{rotulo}</td><td>{_e(par.nome[:40])}</td>"
            f"<td>{_celula(par.dy_12m, formato.percentual)}</td>"
            f"<td>{_celula(par.pvp, formato.decimal)}</td>"
            f"<td>{_celula(par.pl, formato.moeda_compacta)}</td>"
            f"<td>{_selo_tabela(par.selo, par.motivos)}</td></tr>"
        )
    media = raiox.pares_media
    linhas.append(
        f'<tr style="border-top:2px solid #314045"><td colspan="2"><b>média do segmento '
        f"({media.get('n', 0)} fundos)</b></td>"
        f"<td><b>{_celula(media.get('dy'), formato.percentual)}</b></td>"
        f"<td><b>{_celula(media.get('pvp'), formato.decimal)}</b></td>"
        f"<td><b>{_celula(media.get('pl'), formato.moeda_compacta)}</b></td><td></td></tr>"
    )
    return f"""
  <h2>Pares do segmento — {_e(raiox.classificacao)}{_ajuda("Pares do segmento")}</h2>
  <div class="grafico" style="overflow-x:auto">
  <table class="imoveis">
    <thead><tr><th>ticker</th><th>fundo</th><th>DY 12m</th><th>P/VP</th><th>PL</th><th>selo</th></tr></thead>
    <tbody>{"".join(linhas)}</tbody>
  </table>
  <div class="nota">os {len(raiox.pares)} maiores fundos do mesmo segmento (por PL) ·
  P/VP só para fundos com cotação em cache · comparação de fatos, não recomendação</div>
  </div>
"""


def _texto_ia_para_html(texto: str) -> str:
    """Render mínimo do texto do modelo: escapa tudo e converte só **negrito**.
    Jargão de mercado (CRI, CDI, LCI…) ganha tooltip com explicação para leigos —
    definição determinística do nosso glossário, nunca do modelo."""
    import re as _re

    from .glossario import JARGAO

    escapado = _e(texto)
    resultado = _re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escapado)

    # passada única: só a primeira ocorrência de cada termo ganha tooltip, e o
    # texto inserido nunca é re-escaneado (definições citam outros termos)
    usados: set[str] = set()
    padrao = _re.compile(
        r"\b(" + "|".join(sorted((_re.escape(t) for t in JARGAO), key=len, reverse=True)) + r")s?\b"
    )

    def _marca(encontro: "_re.Match[str]") -> str:
        termo = encontro.group(1)
        if termo in usados:
            return encontro.group(0)
        usados.add(termo)
        return (
            f'<span class="termo" tabindex="0">{encontro.group(0)}'
            f'<span class="dica">{_e(JARGAO[termo])}</span></span>'
        )

    return padrao.sub(_marca, resultado)


def _secao_oscilacoes(completo: AnaliseCompleta, leitura: dict | None, visiveis: int = 8) -> str:
    """Meses de variação forte da cota + eventos factuais do mesmo período.
    Coincidência de período, não causa — e a nota diz isso com todas as letras."""
    from ..coleta.fnet import URL_DOWNLOAD

    if not completo.graficos.cotacao:
        return ""

    # documentos já lidos pela IA (fatos, comunicados, assembleias) entram
    # como evento do mês, com link para o original
    fatos_por_mes: dict[str, list[str]] = {}
    if leitura:
        _, documentos = _documentos_lidos(leitura)
        for id_doc, data, rotulo in documentos:
            try:
                dia, mes, ano = data.split("/")
                chave = f"{ano}-{mes}"
            except ValueError:
                continue
            fatos_por_mes.setdefault(chave, []).append(
                f'{_e(rotulo.lower())} publicado em {_e(data)} '
                f'(<a href="{URL_DOWNLOAD.format(id=id_doc)}" target="_blank" rel="noopener">ver original</a>)'
            )

    oscilacoes = list(reversed(completo.oscilacoes))  # mais recentes primeiro
    if not oscilacoes:
        return f"""
  <h2>Oscilações com contexto{_ajuda("Oscilações com contexto")}</h2>
  <div class="grafico"><div class="nota" style="font-size:13px">Nenhum mês com variação da cota
  acima de ±10% no histórico disponível — cota sem sustos até aqui.</div></div>
"""

    linhas = []
    for indice, osc in enumerate(oscilacoes):
        eventos = list(osc.eventos) + fatos_por_mes.get(osc.mes, [])
        cor = "#8FCB9B" if osc.variacao >= 0 else "#D66A6A"
        oculta = ' class="osc-extra" hidden' if indice >= visiveis else ""
        linhas.append(
            f"<tr{oculta}><td style='white-space:nowrap'>{_e(formato.competencia_curta(osc.mes))}</td>"
            f"<td style='color:{cor};font-weight:700;white-space:nowrap'>"
            f"{_e(formato.percentual(osc.variacao, sinal=True))}</td>"
            f"<td style='text-align:left'>{' · '.join(eventos) if eventos else '—'}</td></tr>"
        )
    botao = ""
    if len(oscilacoes) > visiveis:
        botao = (
            f'<button class="ver-mais" onclick="verMais(this, \'osc-extra\')" '
            f'data-mais="ver todos os {len(oscilacoes)} meses" data-menos="mostrar menos">'
            f"ver todos os {len(oscilacoes)} meses</button>"
        )
    return f"""
  <h2>Oscilações com contexto{_ajuda("Oscilações com contexto")}</h2>
  <div class="grafico">
  <table class="imoveis">
    <thead><tr><th>mês</th><th>variação da cota</th><th style="text-align:left">eventos do período</th></tr></thead>
    <tbody>{"".join(linhas)}</tbody>
  </table>
  {botao}
  <div class="nota" style="margin-top:8px">meses em que a cota (ajustada por desdobramento) variou
  mais de ±10% · os eventos listados ocorreram no mesmo período — é coincidência de calendário
  registrada como fato, <b>não</b> afirmação de causa · fatos/comunicados: apenas os já lidos pela IA</div>
  </div>
"""


def _secao_parecer(leitura: dict | None) -> str:
    """Parecer do auditor independente na DF anual — classificação
    determinística (regex sobre o texto oficial), com trecho e link."""
    if not leitura or not leitura.get("parecer"):
        return ""
    from ..coleta.fnet import URL_DOWNLOAD

    parecer = leitura["parecer"]
    tipo = parecer.get("tipo", "nao_identificado")
    grave = parecer.get("grave", False)
    continuidade = parecer.get("continuidade", False)
    if grave:
        cor, icone = "#D66A6A", "⚠"
    elif continuidade:
        cor, icone = "#D9B44A", "⚠"
    elif tipo == "sem_ressalva":
        cor, icone = "#4ade80", "✓"
    else:
        cor, icone = "#8b98a9", "—"
    data = parecer.get("data_entrega", "")[:10]
    aviso_continuidade = (
        '<p style="color:#D9B44A;font-size:13.5px;margin-top:6px">⚠ o auditor apontou '
        "<b>incerteza relevante quanto à continuidade operacional</b> do fundo.</p>"
        if continuidade
        else ""
    )
    trecho = (
        f'<p class="evid" style="background:#101415;border:1px solid #232D31;border-radius:7px;'
        f'padding:6px 10px;font-family:ui-monospace,Consolas,monospace;font-size:12.5px;'
        f'color:#aeb9c7;margin-top:8px">“{_e(parecer["trecho"])}”</p>'
        if parecer.get("trecho")
        else ""
    )
    link = (
        f' · <a href="{URL_DOWNLOAD.format(id=parecer["id"])}" target="_blank" rel="noopener">'
        "📄 baixar a DF original (FNET)</a>"
        if parecer.get("id")
        else ""
    )
    return f"""
  <h2>Parecer do auditor{_ajuda("Parecer do auditor")}</h2>
  <div class="grafico" style="border-left:4px solid {cor}">
  <p style="font-size:15px"><span style="color:{cor};font-weight:800">{icone} {_e(parecer.get("rotulo", ""))}</span>
  <span class="nota"> · demonstrações financeiras entregues em {_e(data)}{link}</span></p>
  {aviso_continuidade}
  {trecho}
  <div class="nota" style="margin-top:8px">classificação automática por texto sobre o PDF oficial
  (fórmulas normatizadas do relatório de auditoria) — confira no documento original</div>
  </div>
"""


def _documentos_lidos(leitura: dict) -> tuple[dict, list[tuple]]:
    """Bloco de comunicados lidos (novo `comunicados` ou legado `fatos`) +
    lista de (id, data, rotulo) por documento."""
    bloco = leitura.get("comunicados") or leitura.get("fatos") or {}
    ids = bloco.get("ids", [])
    datas = bloco.get("datas", [])
    rotulos = bloco.get("rotulos", ["Fato Relevante"] * len(ids))
    if len(datas) != len(ids):
        datas = [f"doc {id_doc}" for id_doc in ids]
    if len(rotulos) != len(ids):
        rotulos = ["Fato Relevante"] * len(ids)
    return bloco, list(zip(ids, datas, rotulos))


def _bloco_fatos_ia(leitura: dict) -> str:
    """Bloco 'Fatos relevantes, comunicados e assembleias' da leitura por IA,
    com link para cada documento original no FNET."""
    from ..coleta.fnet import URL_DOWNLOAD

    bloco, documentos = _documentos_lidos(leitura)
    if not bloco.get("texto"):
        return ""
    so_fatos = all(rotulo == "Fato Relevante" for _, _, rotulo in documentos)
    titulo = "Fatos relevantes recentes" if so_fatos else "Fatos relevantes, comunicados e assembleias"
    links = " · ".join(
        f'<a href="{URL_DOWNLOAD.format(id=id_doc)}" target="_blank" rel="noopener">'
        f"{_e(rotulo)} de {_e(data)}</a>"
        for id_doc, data, rotulo in documentos
    )
    return (
        f'<h3 style="font-size:15px;color:#aeb9c7;margin:16px 0 8px">{titulo}'
        f' <span style="color:#8b98a9;font-weight:400">({links})</span></h3>'
        f'<div style="white-space:pre-wrap">{_texto_ia_para_html(bloco["texto"])}</div>'
    )


def _bloco_evolucao(leitura: dict, completo: AnaliseCompleta | None) -> str:
    """Fato comparado entre a leitura anterior e agora — NUNCA como acerto de
    'previsão' (o selo não prevê, constata); é complemento de contexto."""
    anterior = leitura.get("anterior")
    if not anterior or completo is None:
        return ""
    quando = anterior.get("gerada_em", "")[:10]
    partes = []
    selo = anterior.get("selo")
    alertas = anterior.get("alertas") or []
    if selo:
        rotulo_alertas = (
            f"{len(alertas)} alerta{'s' if len(alertas) != 1 else ''}"
            if alertas
            else "nenhum alerta"
        )
        partes.append(f"o selo era <b>{_e(selo)}</b> ({rotulo_alertas})")
    cota_antes = anterior.get("cota")
    cota_agora = completo.graficos.cotacao[-1][1] if completo.graficos.cotacao else None
    if cota_antes and cota_agora:
        variacao = 100 * (cota_agora - cota_antes) / cota_antes
        partes.append(
            f"a cota foi de R$ {formato.decimal(cota_antes)} para R$ {formato.decimal(cota_agora)} "
            f"({_e(formato.percentual(variacao, sinal=True))})"
        )
    if not partes:
        return ""
    detalhe_alertas = (
        f' <span class="nota">— alertas da época: {_e("; ".join(alertas))}</span>' if alertas else ""
    )
    return (
        f'<div class="nota" style="font-size:13px;margin-top:12px;border-top:1px solid #232D31;'
        f'padding-top:10px"><b>Evolução desde a leitura anterior</b> ({_e(quando)}, relatório de '
        f"{_e(anterior.get('relatorio_data', '')[:10])}): {'; '.join(partes)}.{detalhe_alertas}"
        f"<br>Comparação factual entre duas fotos no tempo — o selo constata, não prevê; "
        f"variação de cota não valida nem invalida alerta.</div>"
    )


def _secao_ia(leitura: dict | None, agora: datetime, completo: AnaliseCompleta | None = None) -> str:
    if leitura and leitura.get("sem_relatorio"):
        verificado = leitura.get("verificado_em", "")[:10]
        bloco_fatos = _bloco_fatos_ia(leitura)
        nota_fatos = (
            " Os <b>fatos relevantes e comunicados</b> publicados pelo fundo foram lidos pela IA e estão abaixo."
            if bloco_fatos
            else " Sem relatório, não há o que a IA ler."
        )
        rodape_fatos = (
            '<div class="nota" style="margin-top:12px">Resumo gerado por IA a partir dos documentos '
            "oficiais — pode conter erros de leitura; os links para os originais permitem conferir "
            "tudo na fonte. Não é recomendação.</div>"
            if bloco_fatos
            else ""
        )
        return f"""
  <h2>🤖 Leitura por IA{_ajuda("Leitura por IA")}</h2>
  <div class="grafico">
  <div class="nota" style="font-size:13px">Este fundo <b>não publicou relatório gerencial</b> no FNET
  (é um documento opcional — muitos fundos divulgam apenas os informes obrigatórios da CVM,
  que já alimentam os indicadores e alertas desta página).{nota_fatos}
  Verificado em {_e(verificado)}; a checagem se repete a cada rodada de leituras.</div>
  {bloco_fatos}
  {rodape_fatos}
  </div>
"""
    if not leitura or not leitura.get("relatorio", {}).get("texto"):
        return ""
    relatorio = leitura["relatorio"]
    data_documento = relatorio.get("data_entrega", "")[:10]
    aviso_idade = ""
    try:
        dia, mes, ano = data_documento.split("/")
        idade_dias = (agora - datetime(int(ano), int(mes), int(dia))).days
        if idade_dias > 40:
            aviso_idade = (
                f' <span style="color:#D9B44A">⚠ documento de {idade_dias} dias atrás — '
                "pode existir relatório mais recente ainda não lido</span>"
            )
    except ValueError:
        pass
    from ..coleta.fnet import URL_DOWNLOAD

    link_original = ""
    if relatorio.get("id"):
        link_original = (
            f' · <a href="{URL_DOWNLOAD.format(id=relatorio["id"])}" target="_blank" '
            'rel="noopener">📄 baixar o relatório original (FNET)</a>'
        )
    bloco_fatos = _bloco_fatos_ia(leitura)
    gerada = leitura.get("gerada_em", "")[:10]
    return f"""
  <h2>🤖 Leitura por IA{_ajuda("Leitura por IA")}</h2>
  <div class="grafico">
  <div class="nota" style="margin-bottom:10px">relatório gerencial de <b>{_e(data_documento)}</b>{aviso_idade}
  · lida por IA local ({_e(leitura.get("modelo", "?"))}) em {_e(gerada)}{link_original}</div>
  <div style="white-space:pre-wrap">{_texto_ia_para_html(relatorio["texto"])}</div>
  {bloco_fatos}
  {_bloco_evolucao(leitura, completo)}
  <div class="nota" style="margin-top:12px">Resumo gerado por IA a partir dos documentos oficiais —
  pode conter erros de leitura; os trechos citados (com página, quando identificada) e o link para o
  documento original permitem conferir tudo na fonte. Não é recomendação.</div>
  </div>
"""


def _secao_calculadoras(completo: AnaliseCompleta) -> str:
    """Calculadoras interativas pré-preenchidas com os dados reais do fundo."""
    dados = completo.graficos
    preco = dados.cotacao[-1][1] if dados.cotacao else 0
    rendimento = next(
        (valor for valor in reversed(dados.rend_por_mes) if valor), 0
    )
    dys = [valor for _, valor in dados.dy_por_mes]
    dy_medio = sum(dys) / len(dys) if dys else 0
    if not preco or not rendimento:
        return ""

    def _n(valor: float, casas: int = 2) -> str:
        return f"{valor:.{casas}f}"

    return f"""
  <h2 id="calculadoras">Calculadoras{_ajuda("Calculadoras")}</h2>

  {_calculadora_retroativa(completo)}

  <div class="calc">
    <h3>Uma cota por mês{_ajuda("Uma cota por mês")}</h3>
    <p class="desc">Quantas cotas você precisaria ter para os rendimentos mensais
    comprarem, sozinhos, pelo menos uma cota nova por mês.</p>
    <div class="campos">
      <div><label for="uc-preco">Preço da cota (R$)</label>
      <input type="number" id="uc-preco" value="{_n(preco)}" step="0.01" min="0.01" oninput="calcUmaCota()"></div>
      <div><label for="uc-rend">Rendimento mensal por cota (R$)</label>
      <input type="number" id="uc-rend" value="{_n(rendimento)}" step="0.01" min="0" oninput="calcUmaCota()"></div>
    </div>
    <div class="resultado">
      <div class="res"><div class="rotulo">Cotas necessárias</div><div class="num" id="uc-cotas">—</div></div>
      <div class="res"><div class="rotulo">Investimento equivalente</div><div class="num" id="uc-invest">—</div></div>
    </div>
    <p class="aviso">Valores pré-preenchidos com a cotação atual e o último rendimento
    estimado deste fundo — edite à vontade. Simulação matemática, não projeção de resultado.</p>
  </div>

  <div class="calc">
    <h3>Projeção de aportes{_ajuda("Projeção de aportes")}</h3>
    <p class="desc">Quanto o patrimônio acumularia aportando todo mês, com os rendimentos
    no ritmo que você definir. Edite os campos e os resultados se atualizam sozinhos.</p>
    <div class="campos">
      <div><label for="pa-inicial">Aporte inicial (R$)</label>
      <input type="number" id="pa-inicial" value="1000" step="100" min="0" oninput="calcAportes()"></div>
      <div><label for="pa-mensal">Aporte mensal (R$)</label>
      <input type="number" id="pa-mensal" value="300" step="50" min="0" oninput="calcAportes()"></div>
      <div><label for="pa-anos">Prazo (anos)</label>
      <input type="number" id="pa-anos" value="10" step="1" min="1" max="50" oninput="calcAportes()"></div>
      <div><label for="pa-taxa">Rendimento mensal (%)</label>
      <input type="number" id="pa-taxa" value="{_n(dy_medio)}" step="0.05" min="0" oninput="calcAportes()"></div>
      <div class="check"><input type="checkbox" id="pa-reinvestir" checked onchange="calcAportes()">
      <label for="pa-reinvestir" style="all:unset;cursor:pointer">reinvestir os rendimentos</label></div>
    </div>
    <div class="resultado">
      <div class="res"><div class="rotulo">Total aportado</div><div class="num" id="pa-aportado">—</div></div>
      <div class="res"><div class="rotulo">Patrimônio final</div><div class="num" id="pa-final">—</div></div>
      <div class="res"><div class="rotulo">Rendimentos no período</div><div class="num" id="pa-rendimentos">—</div></div>
      <div class="res"><div class="rotulo">Renda mensal ao final</div><div class="num" id="pa-renda">—</div></div>
    </div>
    <p class="aviso">O rendimento padrão é a média mensal do DY deste fundo nos últimos 12
    meses — o futuro pode ser diferente. Não considera variação do preço da cota, impostos
    ou emissões. Simulação matemática, não promessa de rentabilidade.</p>
  </div>

  {_calculadora_gordon(preco, rendimento)}
"""


def _calculadora_gordon(preco: float, rendimento_mensal: float) -> str:
    """Preço justo pelo Modelo de Gordon — EXTRA opt-in: só abre se o usuário
    clicar, e o aviso de "não é recomendação" fica sempre visível ANTES do botão.
    r (desconto) e g (crescimento) são premissas DO USUÁRIO — o Scout nunca
    afirma um preço justo; oferece a ferramenta e mostra os fatos ao lado."""
    if not preco or not rendimento_mensal:
        return ""
    div_anual = rendimento_mensal * 12
    return f"""
  <div class="calc">
    <h3>🧮 Preço justo (Modelo de Gordon){_ajuda("Preço justo (Gordon)")}</h3>
    <div style="background:#2a2320;border:1px solid #6b5a2a;color:#e8d9a8;padding:10px 12px;border-radius:8px;font-size:13px;margin:6px 0">
      Esta calculadora está aqui para <b>facilitar sua análise</b> — <b>não é recomendação</b> de
      compra ou venda. O “preço justo” depende inteiramente das premissas que <b>VOCÊ</b> define
      (taxa de desconto e crescimento). É uma simulação sua, não um veredito do Scout.
    </div>
    <button class="btn-topo" onclick="abrirGordon(this)">Abrir a calculadora</button>
    <div hidden>
      <p class="desc">Modelo de Gordon: <b>preço justo = dividendo × (1 + g) / (r − g)</b>. Tudo editável.</p>
      <div class="campos">
        <div><label for="gd-div">Dividendo anual por cota (R$)</label>
        <input type="number" id="gd-div" value="{div_anual:.2f}" step="0.01" min="0" oninput="calcGordon()"></div>
        <div><label for="gd-r">Taxa de desconto r (% a.a.)</label>
        <input type="number" id="gd-r" value="10" step="0.5" min="0.1" oninput="calcGordon()"></div>
        <div><label for="gd-g">Crescimento g (% a.a.)</label>
        <input type="number" id="gd-g" value="0" step="0.5" oninput="calcGordon()"></div>
      </div>
      <div class="resultado">
        <div class="res"><div class="rotulo">Preço justo (com suas premissas)</div><div class="num" id="gd-justo">—</div></div>
        <div class="res"><div class="rotulo">Cotação atual (D-1)</div><div class="num">R$ {preco:.2f}</div></div>
      </div>
      <p class="aviso">Dividendo pré-preenchido com o rendimento real dos últimos 12 meses; r e g são
      SUAS premissas. Modelo teórico (crescimento perpétuo constante), sensível às premissas — não é
      recomendação nem promessa de retorno.</p>
    </div>
  </div>"""


def _card_rentabilidade(dados) -> str:
    """Card de rentabilidade com abas de janela + checkbox de reinvestimento.

    Os painéis são pré-renderizados por (janela, modo) e o JS só alterna a
    visibilidade — a página continua estática.
    """
    pct = lambda v: formato.percentual(v)  # noqa: E731
    paineis = []
    for janela, modos in dados.rentabilidade.items():
        for modo, series_janela in modos.items():
            paineis.append(
                (f"{janela}|{modo}", graficos.grafico_linhas(series_janela, formatador=pct))
            )
    janelas = list(dados.rentabilidade)
    botoes = "".join(
        f'<button class="{"ativo" if indice == 0 else ""}" '
        f"onclick=\"janelaRent(this,'{_e(janela)}')\">{_e(janela)}</button>"
        for indice, janela in enumerate(janelas)
    )
    corpo = "".join(
        f'<div class="painel" data-painel="{_e(chave)}"'
        f'{"" if chave == janelas[0] + "|com" else " hidden"}>{svg}</div>'
        for chave, svg in paineis
    )
    titulo = "Rentabilidade acumulada × CDI × IPCA"
    return f"""<div class="grafico" id="card-rent" data-janela="{_e(janelas[0])}">
    <div class="cab"><h3>{_e(titulo)}{_ajuda("Rentabilidade acumulada (com proventos) × CDI × IPCA")}</h3>
    <div class="abas">{botoes}</div></div>
    {corpo}
    <div class="check" style="margin-top:6px"><input type="checkbox" id="rent-reinvestir" checked onchange="atualizaRent()">
    <label for="rent-reinvestir" style="all:unset;cursor:pointer;color:#aeb9c7;font-size:13px">
    reinvestir os rendimentos *</label></div>
    <div class="nota">* marcado: rentabilidade com proventos reinvestidos (retorno total estimado
    a partir do fechamento oficial B3 + rendimentos informados à CVM);
    desmarcado: apenas variação de preço. CDI e IPCA: Banco Central (SGS).</div>
  </div>"""


def _calculadora_retroativa(completo: AnaliseCompleta) -> str:
    """"E se eu tivesse investido?" — usa a rentabilidade REAL que aconteceu."""
    import json

    rentabilidade = completo.graficos.rentabilidade
    if not rentabilidade:
        return ""
    # % final por janela e modo: {"12 meses": {"com": {"Fundo": 5.1, ...}, "sem": {...}}}
    finais = {
        janela: {
            modo: {nome: pontos[-1][1] for nome, pontos in series_janela if pontos}
            for modo, series_janela in modos.items()
        }
        for janela, modos in rentabilidade.items()
    }
    opcoes = "".join(
        f'<option value="{_e(janela)}">{_e("há " + janela.replace("máximo", "todo o histórico"))}</option>'
        for janela in finais
    )
    return f"""
  <div class="calc">
    <h3>E se eu tivesse investido?{_ajuda("E se eu tivesse investido?")}</h3>
    <p class="desc">Simulação com o passado que realmente aconteceu — rentabilidade do fundo
    com proventos, comparada ao CDI e à inflação no mesmo período.</p>
    <div class="campos">
      <div><label for="rt-valor">Se você tivesse investido (R$)</label>
      <input type="number" id="rt-valor" value="1000" step="100" min="1" oninput="calcRetro()"></div>
      <div><label for="rt-janela">Período</label>
      <select id="rt-janela" onchange="calcRetro()">{opcoes}</select></div>
      <div class="check"><input type="checkbox" id="rt-reinvestir" checked onchange="calcRetro()">
      <label for="rt-reinvestir" style="all:unset;cursor:pointer">reinvestindo os rendimentos</label></div>
    </div>
    <div class="resultado" id="rt-resultado"></div>
    <p class="aviso">Cálculo sobre a rentabilidade observada no período (fundo: cotação
    ajustada por proventos; CDI e IPCA: Banco Central). Passado real, não projeção —
    e passado não garante futuro.</p>
  </div>
  <script>const RETRO = {json.dumps(finais, ensure_ascii=False)};</script>
"""


def _card_grafico(titulo: str, svg: str, nota: str = "", chave_ajuda: str = "") -> str:
    rodape = f'<div class="nota">{_e(nota)}</div>' if nota else ""
    ajuda = _ajuda(chave_ajuda or titulo)
    return f'<div class="grafico"><h3>{_e(titulo)}{ajuda}</h3>{svg}{rodape}</div>'


def _card_grafico_abas(
    titulo: str, paineis: list[tuple[str, str]], nota: str = "", chave_ajuda: str = ""
) -> str:
    """Card com painéis alternáveis (ex.: Ano/Mês) via botões — JS inline mínimo."""
    paineis = [(rotulo, svg) for rotulo, svg in paineis if svg]
    if not paineis:
        return ""
    if len(paineis) == 1:
        return _card_grafico(titulo, paineis[0][1], nota, chave_ajuda)
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
    ajuda = _ajuda(chave_ajuda or titulo)
    return (
        f'<div class="grafico"><div class="cab"><h3>{_e(titulo)}{ajuda}</h3>'
        f'<div class="abas">{botoes}</div></div>{corpo}{rodape}</div>'
    )
