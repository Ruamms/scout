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
    "sem_alertas": "#7BD69A",
    "leves": "#E3C25C",
    "atencao": "#E39A55",
    "grave": "#DB7A7A",
    "insuficiente": "#7C8894",
}

_COR_SEVERIDADE = {
    Severidade.ALTA: "#DB7A7A",
    Severidade.MEDIA: "#E39A55",
    Severidade.BAIXA: "#6FB6D8",
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
    "<circle cx='32' cy='32' r='25' fill='none' stroke='#8FCB9B' stroke-width='5'/>"
    "<polygon points='47.56,16.44 36.95,36.95 16.44,47.56' fill='#CDEBD3'/>"
    "<polygon points='47.56,16.44 27.05,27.05 16.44,47.56' fill='#6FA87C'/>"
    "<circle cx='32' cy='32' r='3.6' fill='#0F1416'/>"
    "</svg>"
)
import base64 as _base64  # noqa: E402

FAVICON = "data:image/svg+xml;base64," + _base64.b64encode(_SVG_FAVICON.encode()).decode()
TAG_FAVICON = f'<link rel="icon" href="{FAVICON}">'

_SVG_MARCA = _SVG_FAVICON.replace("<svg ", "<svg width='34' height='34' ")

# CSS do cabeçalho de marca, compartilhado por todas as páginas (site, relatório, apoio)
CSS_MARCA = """
@font-face { font-family:'Scout Display'; src:url('scout-display.ttf') format('truetype');
  font-weight:400 700; font-display:swap; }
.topo-site { position:sticky; top:0; z-index:20; display:flex; align-items:center; gap:16px;
  flex-wrap:wrap; padding:12px 0; border-bottom:1px solid #263034; margin-bottom:22px;
  background:rgba(15,20,22,.92); backdrop-filter:blur(10px); }
.brand { display:inline-flex; align-items:center; gap:10px; text-decoration:none; }
.wordmark { font-family:'Scout Display',system-ui,sans-serif; font-size:20px; font-weight:700;
  letter-spacing:.08em; color:#EAEEF0; }
.brand-o { color:#8FCB9B; }
.brand-tag { color:#6B7681; font-size:11px; letter-spacing:.08em; text-transform:uppercase; }
.topo-site input { margin-left:auto; background:#161D20; color:#EAEEF0;
  border:1px solid #263034; border-radius:9px; padding:8px 13px; font-size:13.5px; width:270px; }
.topo-site input:focus { outline:2px solid #8FCB9B; outline-offset:1px; border-color:#8FCB9B; }
.selo-dot { display:inline-flex; align-items:center; gap:6px; font-size:12px; font-weight:600; white-space:nowrap; }
.selo-dot .pt { width:7px; height:7px; border-radius:50%; flex-shrink:0; }
td.col-selo, th.col-selo { text-align:left; }
"""


# CSS + HTML do menu superior com dropdowns (mega-menu), compartilhado pelas
# páginas de navegação (home, fiis, etfs, comparar). HTML/CSS/JS puro — o
# GitHub Pages não impõe limitação nenhuma a menu interativo.
CSS_MENU = """
.nav { display:flex; align-items:center; gap:2px; margin:0 0 6px; flex-wrap:wrap; }
.nav .item { position:relative; }
.nav .topo-btn { background:none; border:none; color:#9AA7B2; font-size:14px; font-weight:600;
  padding:7px 13px; border-radius:8px; cursor:pointer; }
.nav .topo-btn:hover, .nav .item.aberto .topo-btn { background:#1E272B; color:#EAEEF0; }
.nav .painel { display:none; position:absolute; top:100%; left:0; z-index:40; min-width:230px;
  background:#161D20; border:1px solid #263034; border-radius:12px; padding:10px;
  box-shadow:0 14px 40px rgba(0,0,0,.5); }
.nav .item.aberto .painel { display:block; }
.nav .painel a { display:block; color:#EAEEF0; text-decoration:none; font-size:13.5px;
  padding:8px 10px; border-radius:8px; }
.nav .painel a:hover { background:#1E272B; color:#8FCB9B; }
.nav .painel .grupo { color:#6B7681; font-size:11px; text-transform:uppercase;
  letter-spacing:.06em; padding:6px 10px 2px; }
.nav > a { color:#9AA7B2; font-size:14px; font-weight:600; text-decoration:none;
  padding:7px 13px; border-radius:8px; }
.nav > a:hover { background:#1E272B; color:#EAEEF0; }
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

# Crosshair + tooltip flutuante nos gráficos de linha (estilo terminal de
# mercado): os eixos ficam, o valor interno some, e ao passar o mouse aparece
# a linha-guia com o valor de cada série no ponto. Lê os círculos que o
# graficos.py já desenha (data-val/data-lbl/data-nome/data-cor) — JS puro.
JS_GRAFICO_HOVER = '''
(function(){
  var NS='http://www.w3.org/2000/svg';
  function wire(svg){
    var pts=[].slice.call(svg.querySelectorAll('circle[data-val]'));
    if(pts.length<2) return;
    var wrap=svg.closest('.grafico'); if(!wrap) return;
    if(getComputedStyle(wrap).position==='static') wrap.style.position='relative';
    var groups={}, order=[];
    pts.forEach(function(c){
      c.setAttribute('data-r0', c.getAttribute('r')||'3');
      c.setAttribute('data-op0', c.getAttribute('opacity')||'1');
      var lbl=c.getAttribute('data-lbl'), x=parseFloat(c.getAttribute('cx'));
      if(!groups[lbl]){ groups[lbl]={x:x,lbl:lbl,items:[]}; order.push(lbl); }
      groups[lbl].items.push({nome:c.getAttribute('data-nome'),val:c.getAttribute('data-val'),
        cor:c.getAttribute('data-cor'),cy:parseFloat(c.getAttribute('cy')),el:c});
    });
    var cols=order.map(function(l){return groups[l];}).sort(function(a,b){return a.x-b.x;});
    var guide=document.createElementNS(NS,'line');
    guide.setAttribute('y1',14); guide.setAttribute('y2',266);
    guide.setAttribute('stroke','#8FCB9B'); guide.setAttribute('stroke-width','1');
    guide.setAttribute('stroke-dasharray','3 3'); guide.setAttribute('opacity','0');
    guide.setAttribute('pointer-events','none'); svg.appendChild(guide);
    var tip=document.createElement('div');
    tip.style.cssText='position:absolute;pointer-events:none;z-index:6;background:#1E272B;border:1px solid #33434A;border-radius:9px;padding:8px 11px;font-size:12px;color:#EAEEF0;box-shadow:0 8px 24px rgba(0,0,0,.5);opacity:0;transition:opacity .08s;white-space:nowrap;font-variant-numeric:tabular-nums;';
    wrap.appendChild(tip);
    function reset(){ pts.forEach(function(c){ c.setAttribute('r',c.getAttribute('data-r0')); c.setAttribute('opacity',c.getAttribute('data-op0')); }); }
    svg.addEventListener('pointermove', function(e){
      var rect=svg.getBoundingClientRect(); if(!rect.width) return;
      var sx=rect.width/860, sy=rect.height/300;
      var vbx=(e.clientX-rect.left)/sx, best=null, bd=1e9;
      cols.forEach(function(g){ var d=Math.abs(g.x-vbx); if(d<bd){bd=d;best=g;} });
      if(!best) return;
      reset();
      guide.setAttribute('x1',best.x); guide.setAttribute('x2',best.x); guide.setAttribute('opacity','1');
      var top=1e9;
      best.items.forEach(function(it){ it.el.setAttribute('r','5'); it.el.setAttribute('opacity','1'); if(it.cy<top) top=it.cy; });
      tip.innerHTML='<div style="color:#6B7681;font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px;">'+best.lbl+'</div>'+
        best.items.map(function(it){ return '<div style="display:flex;align-items:center;gap:7px;margin-top:2px;"><span style="width:8px;height:8px;border-radius:50%;background:'+it.cor+';"></span><span style="color:#9AA7B2;">'+it.nome+'</span><b style="margin-left:auto;padding-left:12px;">'+it.val+'</b></div>'; }).join('');
      var leftPx=best.x*sx, topPx=top*sy, flip=leftPx>rect.width-160;
      tip.style.left=leftPx+'px'; tip.style.top=(topPx-12)+'px';
      tip.style.transform='translate('+(flip?'calc(-100% - 14px)':'14px')+',-100%)';
      tip.style.opacity='1';
    });
    svg.addEventListener('pointerleave', function(){ guide.setAttribute('opacity','0'); tip.style.opacity='0'; reset(); });
  }
  var svgs=document.querySelectorAll('.grafico svg');
  for(var i=0;i<svgs.length;i++){ try{ wire(svgs[i]); }catch(e){} }
})();
'''


def menu_html() -> str:
    return """
  <nav class="nav">
    <div class="item">
      <button class="topo-btn" type="button">FIIs ▾</button>
      <div class="painel">
        <a href="fiis.html">Todos os FIIs</a>
        <a href="fiis.html#rankings">Rankings do dia</a>
        <a href="comparar.html">Comparar FIIs</a>
      </div>
    </div>
    <div class="item">
      <button class="topo-btn" type="button">ETFs ▾</button>
      <div class="painel">
        <a href="etfs.html">Todos os ETFs</a>
        <a href="comparar-etfs.html">Comparar ETFs</a>
        <div class="grupo">por classe</div>
        <a href="etfs.html?classe=Ações Brasil">Ações Brasil</a>
        <a href="etfs.html?classe=Ações Internacionais">Ações Internacionais</a>
        <a href="etfs.html?classe=Renda Fixa">Renda Fixa</a>
        <a href="etfs.html?classe=Cripto">Cripto</a>
      </div>
    </div>
    <div class="item">
      <button class="topo-btn" type="button">Ações ▾</button>
      <div class="painel">
        <a href="acoes.html">Todas as ações</a>
        <a href="comparar-acoes.html">Comparar ações</a>
      </div>
    </div>
    <div class="item">
      <button class="topo-btn" type="button">Bancos ▾</button>
      <div class="painel">
        <a href="bancos.html">Todos os bancos</a>
        <a href="comparar-bancos.html">Comparar bancos</a>
      </div>
    </div>
    <a href="metodologia.html">Metodologia</a>
    <a href="apoie.html">Apoiar</a>
  </nav>
"""




# busca viva do cabeçalho (mesma experiência da home): dropdown com ticker,
# nome, ponto do selo e badge da classe. O índice vem de busca.json (gerado
# pelo site) — baixado uma vez e cacheado pelo navegador.
CSS_BUSCA_TOPO = """
.busca-topo { position:relative; margin-left:auto; }
.busca-topo input { background:#161D20; color:#EAEEF0; border:1px solid #263034;
  border-radius:9px; padding:8px 13px; font-size:13.5px; width:280px; }
.busca-topo input:focus { outline:2px solid #8FCB9B; outline-offset:1px; border-color:#8FCB9B; }
#resultados-topo { position:absolute; top:100%; right:0; z-index:45; width:380px; max-width:86vw;
  background:#161D20; border:1px solid #263034; border-radius:12px; margin-top:6px;
  overflow:hidden; box-shadow:0 16px 44px rgba(0,0,0,.55); }
#resultados-topo a { display:flex; align-items:center; gap:9px; padding:9px 12px;
  color:#EAEEF0; text-decoration:none; border-bottom:1px solid #1B2225; font-size:13.5px; }
#resultados-topo a:last-child { border-bottom:none; }
#resultados-topo a:hover, #resultados-topo a.foco { background:#1E272B; }
#resultados-topo .tk { font-weight:800; min-width:64px; }
#resultados-topo .nm { color:#9AA7B2; font-size:12px; flex:1; overflow:hidden; white-space:nowrap; text-overflow:ellipsis; }
#resultados-topo .badge { font-size:9.5px; font-weight:700; letter-spacing:.05em; text-transform:uppercase;
  background:#1E272B; color:#8FCB9B; border:1px solid #263034; border-radius:99px; padding:2px 8px; white-space:nowrap; }
#resultados-topo .ponto { width:8px; height:8px; border-radius:50%; flex-shrink:0; }
"""

JS_BUSCA_TOPO = """
let _ativosTopo = null;
let _focoTopo = -1;
const CORES_SELO_TOPO = {"sem_alertas": "#7BD69A", "leves": "#E3C25C", "atencao": "#E39A55", "grave": "#DB7A7A", "insuficiente": "#7C8894"};

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
    `<a href="${a.u || (a.t + '.html')}">` +
    (a.t ? `<span class="tk">${a.t}</span>` : '') +
    `<span class="nm">${a.n}</span>` +
    (a.s ? `<span class="ponto" style="background:${CORES_SELO_TOPO[a.s] || '#7C8894'}" title="${a.r}"></span>` : '') +
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


def botao_reportar_html(url: str | None) -> str:
    """Botão flutuante 'Reportar' para injetar antes de </body> em toda página.

    `url` é o link do formulário hospedado (Google Forms/Tally etc.), com os
    tokens {URL} e {TICKER} onde a página e o ticker devem ser pré-preenchidos —
    substituídos no clique. Nada é carregado de terceiros até o usuário clicar
    (abre em nova aba); vazio = sem botão (build local/testes ficam limpos)."""
    url = (url or "").strip()
    if not url:
        return ""
    return (
        f'<button id="scout-reportar" data-url="{_e(url)}" type="button" '
        'onclick="scoutReportar(this)" title="Reportar um problema nesta página">'
        "🐞 Reportar</button>"
        "<style>#scout-reportar{position:fixed;right:16px;bottom:16px;z-index:60;"
        "background:#1B2225;color:#8FCB9B;border:1px solid #33434A;border-radius:99px;"
        "padding:9px 15px;font:600 13px system-ui,sans-serif;cursor:pointer;"
        "box-shadow:0 6px 20px rgba(0,0,0,.4)}"
        "#scout-reportar:hover{border-color:#8FCB9B;background:#232D31}"
        "@media print{#scout-reportar{display:none}}</style>"
        "<script>function scoutReportar(b){"
        "var tk=((document.querySelector('h1')||{}).textContent||'').trim().split(/\\s+/)[0];"
        "var u=b.dataset.url.replace('{URL}',encodeURIComponent(location.href))"
        ".replace('{TICKER}',encodeURIComponent(tk));"
        "window.open(u,'_blank','noopener');}</script>"
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
    _fonte = Path(__file__).parent / "assets" / "scout-display.ttf"
    if _fonte.exists() and not (destino / "scout-display.ttf").exists():
        (destino / "scout-display.ttf").write_bytes(_fonte.read_bytes())
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
body {{ background:#0F1416; color:#EAEEF0; font-family:system-ui,-apple-system,sans-serif; line-height:1.5; }}
.pagina {{ max-width:960px; margin:0 auto; padding:28px 20px 40px; }}
a {{ color:#8FCB9B; text-decoration:none; }} a:hover {{ color:#B9E2C1; }}
.topo {{ display:flex; flex-wrap:wrap; align-items:baseline; gap:10px 14px; }}
.marca {{ color:#9AA7B2; font-size:14px; letter-spacing:.14em; text-transform:uppercase; }}
h1 {{ font-family:'Scout Display',system-ui,sans-serif; font-size:34px; font-weight:700; letter-spacing:-.02em; }} h1 small {{ font-family:system-ui,sans-serif; color:#9AA7B2; font-size:17px; font-weight:400; letter-spacing:0; }}
.selo {{ display:inline-flex; align-items:center; gap:8px; padding:6px 14px; border-radius:99px; font-weight:700; font-size:13.5px; color:#0F1416; white-space:nowrap; }}
.selo-dot {{ display:inline-flex; align-items:center; gap:6px; font-size:12px; font-weight:600; white-space:nowrap; }}
.selo-dot .pt {{ width:7px; height:7px; border-radius:50%; flex-shrink:0; }}
.btn-topo {{ margin-left:auto; background:#161D20; border:1px solid #263034; color:#8FCB9B; text-decoration:none; padding:6px 14px; border-radius:8px; font-size:13px; font-weight:600; }}
.btn-topo:hover {{ border-color:#8FCB9B; }}
.nav-site {{ display:flex; gap:12px; align-items:center; flex-wrap:wrap; margin-top:12px; }}
.nav-site a {{ color:#8FCB9B; text-decoration:none; font-size:13.5px; font-weight:600; }}
.nav-site input {{ background:#161D20; color:#EAEEF0; border:1px solid #263034; border-radius:9px;
  padding:8px 13px; font-size:13.5px; width:280px; }}
.meta {{ color:#9AA7B2; font-size:13px; margin-top:6px; }}
.cards {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(150px,1fr)); gap:12px; margin:22px 0; }}
.card {{ background:#161D20; border:1px solid #263034; border-radius:12px; padding:14px 16px; }}
.card .nome {{ color:#9AA7B2; font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:.06em; }}
.card .valor {{ font-family:'Scout Display',system-ui,sans-serif; font-size:23px; font-weight:700; letter-spacing:-.01em; margin-top:4px; font-variant-numeric:tabular-nums; }}
.card .extra {{ color:#6B7681; font-size:11.5px; margin-top:3px; }}
.card.alerta {{ border-color:#4a3f24; }}
h2 {{ font-family:'Scout Display',system-ui,sans-serif; font-size:22px; font-weight:700; letter-spacing:-.01em; margin:34px 0 10px; }}
.flag {{ background:#161D20; border:1px solid #263034; border-left:3px solid; border-radius:12px; padding:14px 18px; margin-bottom:10px; }}
.flag .sev {{ font-size:12px; font-weight:800; letter-spacing:.08em; }}
.flag h3 {{ font-size:16px; margin:2px 0 6px; }}
.flag .evid {{ background:#0F1416; border:1px solid #263034; border-radius:8px; padding:8px 11px;
  font-family:ui-monospace,Consolas,monospace; font-size:12.5px; color:#9AA7B2; margin-top:8px; }}
.flag .fonte {{ color:#6B7681; font-size:12px; margin-top:5px; }}
.ok {{ color:#7BD69A; font-size:14px; }} .na {{ color:#9AA7B2; font-size:13px; }}
ul {{ padding-left:20px; }} li {{ margin:3px 0; }}
ul.ok {{ list-style:none; padding-left:6px; }}
ul.ok li {{ color:#9AA7B2; }}
ul.ok li::before {{ content:'✓  '; color:#7BD69A; font-weight:700; }}
.grafico {{ background:#161D20; border:1px solid #263034; border-radius:14px; padding:16px 18px 10px; margin-bottom:14px; }}
.grafico h3 {{ font-size:15px; color:#9AA7B2; margin-bottom:8px; }}
.grafico .nota {{ color:#6B7681; font-size:11px; }}
.grafico .cab {{ display:flex; justify-content:space-between; align-items:center; gap:10px; flex-wrap:wrap; }}
.abas button {{ background:#1E272B; color:#9AA7B2; border:1px solid #263034; border-radius:7px; padding:4px 12px; font-size:12px; cursor:pointer; }}
.abas button.ativo {{ background:#8FCB9B; color:#0F1416; border-color:#8FCB9B; font-weight:700; }}
.ajuda {{ display:inline-flex; align-items:center; justify-content:center; width:15px; height:15px;
  border-radius:50%; background:#1E272B; color:#6B7681; font-size:10px; font-weight:700;
  cursor:help; position:relative; vertical-align:middle; margin-left:5px; }}
.ajuda .dica, .termo .dica {{ visibility:hidden; opacity:0; transition:opacity .15s; position:absolute; z-index:10;
  bottom:135%; left:50%; transform:translateX(-50%); width:270px; background:#1E272B;
  border:1px solid #33434A; border-radius:9px; padding:10px 12px; color:#EAEEF0;
  font-size:12.5px; font-weight:400; line-height:1.45; text-transform:none; letter-spacing:0;
  text-align:left; box-shadow:0 6px 20px rgba(0,0,0,.45); white-space:normal; }}
.ajuda:hover .dica, .ajuda:focus .dica, .termo:hover .dica, .termo:focus .dica {{ visibility:visible; opacity:1; }}
.termo {{ border-bottom:1px dotted #6B7681; cursor:help; position:relative; }}
.calc {{ background:#161D20; border:1px solid #263034; border-radius:14px; padding:16px; margin-bottom:14px; }}
.calc h3 {{ font-family:'Scout Display',system-ui,sans-serif; font-size:16px; font-weight:700; color:#EAEEF0; margin-bottom:4px; }}
.calc .desc {{ color:#9AA7B2; font-size:13px; margin-bottom:12px; }}
.calc .campos {{ display:flex; flex-wrap:wrap; gap:10px; align-items:end; }}
.calc label {{ display:block; color:#9AA7B2; font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:.05em; margin-bottom:4px; }}
.calc input[type=number] {{ background:#0F1416; color:#EAEEF0; border:1px solid #33434A; border-radius:9px; padding:9px 11px; width:130px; font-size:15px; font-variant-numeric:tabular-nums; }}
.calc input[type=number]:focus, .calc select:focus {{ outline:2px solid #8FCB9B; outline-offset:1px; border-color:#8FCB9B; }}
.calc select {{ background:#0F1416; color:#EAEEF0; border:1px solid #33434A; border-radius:9px; padding:9px 11px; font-size:15px; }}
.calc .check {{ display:flex; align-items:center; gap:6px; color:#9AA7B2; font-size:13px; padding-bottom:8px; }}
.calc .resultado {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(170px,1fr)); gap:10px; margin-top:14px; }}
.calc .res {{ background:#0F1416; border:1px solid #263034; border-radius:10px; padding:11px 13px; }}
.calc .res .rotulo {{ color:#9AA7B2; font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:.05em; }}
.calc .res .num {{ font-family:'Scout Display',system-ui,sans-serif; font-size:19px; font-weight:700; margin-top:3px; color:#8FCB9B; font-variant-numeric:tabular-nums; }}
.calc .aviso {{ color:#6B7681; font-size:11.5px; margin-top:10px; }}
.calc .gd-base {{ display:flex; flex-wrap:wrap; align-items:center; gap:8px; margin:0 0 12px; color:#9AA7B2; font-size:12px; }}
.calc .gd-base button {{ background:#1E272B; color:#9AA7B2; border:1px solid #263034; border-radius:7px; padding:4px 12px; font-size:12px; cursor:pointer; }}
.calc .gd-base button:hover {{ border-color:#8FCB9B; }}
.calc .gd-base button.ativo {{ background:#8FCB9B; color:#0F1416; border-color:#8FCB9B; font-weight:700; }}
.calc .campos.gordon {{ align-items:flex-start; }}
.calc .gd-cap {{ margin-top:5px; max-width:150px; font-size:11px; color:#9AA7B2; line-height:1.5; }}
table.imoveis {{ width:100%; border-collapse:collapse; font-size:13.5px; font-variant-numeric:tabular-nums; }}
table.imoveis th {{ color:#9AA7B2; font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:.06em; text-align:left; padding:9px 10px; border-bottom:1px solid #33434A; }}
table.imoveis td {{ padding:9px 10px; border-bottom:1px solid #1B2225; }}
table.imoveis tbody tr:hover td {{ background:#12171A; }}
table.imoveis td:not(:first-child), table.imoveis th:not(:first-child) {{ text-align:right; }}
table.imoveis td.col-selo, table.imoveis th.col-selo {{ text-align:left; }}
.ver-mais {{ background:#161D20; color:#8FCB9B; border:1px solid #263034; border-radius:9px;
  padding:8px 18px; font-size:13px; font-weight:600; cursor:pointer; margin-top:12px; }}
.ver-mais:hover {{ border-color:#8FCB9B; }}
.rodape {{ color:#6B7681; font-size:12.5px; border-top:1px solid #1B2225; margin-top:30px; padding-top:16px; }}
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
    {_e(raiox.cnpj)} · {_e(raiox.classificacao)}{_tipo_selo(raiox)} · Gestão {_e(raiox.gestao.lower())}<br>
    informes CVM até <b>{_e(raiox.dados_ate)}</b>{_cotacao_em(raiox, agora)} · relatório gerado em {agora.strftime("%d/%m/%Y %H:%M")}
  </div>

  <div class="cards">{_cards_indicadores(raiox)}</div>

  <h2>🚩 Red flags{_ajuda("Red flags")}</h2>
  {_secao_flags(raiox)}

  {_secao_parecer(leitura)}

  {_secao_posicoes(raiox, publicados=publicados)}

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
  const inp = document.getElementById('gd-div');
  const cap = document.getElementById('gd-cap');
  // no modo "último" o campo é o dividendo MENSAL: anualiza × 12 internamente
  const modo = inp ? inp.dataset.modo : '12m';
  let d = num('gd-div');
  if (modo === 'ult') {{
    d = d * 12;
    if (cap) cap.textContent = '× 12 = ' + d.toLocaleString('pt-BR', {{style: 'currency', currency: 'BRL', minimumFractionDigits: 2}}) + ' por ano';
  }} else if (cap) {{
    cap.textContent = inp && inp.dataset.periodo ? 'dividendos de ' + inp.dataset.periodo : '';
  }}
  const r = num('gd-r') / 100, g = num('gd-g') / 100;
  if (d <= 0 || r <= g) {{ el.textContent = (r <= g ? 'r precisa ser > g' : '—'); return; }}
  el.textContent = (d * (1 + g) / (r - g)).toLocaleString('pt-BR', {{style: 'currency', currency: 'BRL', minimumFractionDigits: 2}});
}}

function gordonBase(modo, botao) {{
  const inp = document.getElementById('gd-div');
  if (!inp) return;
  inp.dataset.modo = modo;
  inp.value = modo === 'ult' ? inp.dataset.vult : inp.dataset.v12m;
  if (botao) botao.parentElement.querySelectorAll('button').forEach(b => b.classList.toggle('ativo', b === botao));
  calcGordon();
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
{JS_GRAFICO_HOVER}
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
    cor = _COR_SELO.get(raiox.selo.nivel, "#7C8894")
    return (
        f'<span class="selo" style="background:{cor}" title="{_e(raiox.selo.descricao)}">'
        f"{_e(raiox.selo.rotulo)}</span>"
    )


def _tipo_selo(raiox: RaioX) -> str:
    """Badge do tipo do FII (papel/tijolo/híbrido/FoF) no cabeçalho, com a
    composição da carteira CVM no tooltip. Vazio quando não há classificação."""
    if not raiox.tipo:
        return ""
    return (
        ' · <span style="display:inline-block;background:#182420;border:1px solid #2E4A38;'
        'color:#8FCB9B;border-radius:99px;padding:1px 9px;font-size:11.5px;font-weight:700;'
        f'vertical-align:middle" title="{_e(raiox.tipo_fonte)}">{_e(raiox.tipo)}</span>'
    )


def _cotacao_em(raiox: RaioX, agora: datetime) -> str:
    if not raiox.cotacao_em:
        return ""
    idade = formato.idade_legivel(raiox.cotado_em_iso, agora)
    if not idade:
        return f" · cotação de <b>{_e(raiox.cotacao_em)}</b>"
    defasada = "dia" in idade  # mais de 48h: fim de semana/feriado/cache antigo
    cor = "#E3C25C" if defasada else "#9AA7B2"
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


def _secao_posicoes(raiox: RaioX, publicados: set[str] | None = None, limite: int = 10) -> str:
    """O que o fundo tem DENTRO (FoF: cotas de outros fundos; papel: CRIs) —
    relação de ativos declarada no informe anual, com link e selo cruzados
    quando o ativo é um fundo que o Scout também analisa."""
    if not raiox.posicoes:
        return ""

    linhas = []
    for indice, posicao in enumerate(raiox.posicoes):
        oculta = ' class="posicao-extra" hidden' if indice >= limite else ""
        if posicao.ticker and publicados and posicao.ticker in publicados:
            nome = f'<a href="{_e(posicao.ticker)}.html">{_e(posicao.ticker)}</a>'
        else:
            nome = _e(posicao.nome[:52])
        valor = formato.moeda_compacta(posicao.valor) if posicao.valor else "—"
        pct = formato.percentual(posicao.pct) if posicao.pct is not None else "—"
        linhas.append(
            f"<tr{oculta}><td>{nome}</td><td>{valor}</td><td>{pct}</td>"
            f"<td>{_selo_tabela(posicao.selo, posicao.motivos)}</td></tr>"
        )
    botao = ""
    if len(raiox.posicoes) > limite:
        botao = (
            f'<button class="ver-mais" onclick="verMais(this, \'posicao-extra\')" '
            f'data-mais="ver todos os {len(raiox.posicoes)} ativos" data-menos="mostrar menos">'
            f"ver todos os {len(raiox.posicoes)} ativos</button>"
        )
    return f"""
  <h2>O que o fundo tem dentro ({len(raiox.posicoes)})</h2>
  <div class="grafico" style="overflow-x:auto">
  <table class="imoveis">
    <thead><tr><th>ativo</th><th>valor contábil</th><th>% do declarado</th><th>alerta</th></tr></thead>
    <tbody>{"".join(linhas)}</tbody>
  </table>
  {botao}
  <div class="nota">relação de ativos do informe ANUAL (CVM), exercício encerrado em {_e(raiox.posicoes_em)} —
  a carteira de hoje pode estar diferente · valores contábeis declarados pelo próprio fundo ·
  quando o ativo é um fundo que o Scout também analisa, o link leva ao raio-x dele e a coluna
  <b>alerta</b> mostra o selo daquela página</div>
  </div>
"""


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
            f'<td style="white-space:nowrap">{taxa}</td><td class="col-selo">{selo}</td></tr>'
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
  <p class="desc" style="color:#9AA7B2;font-size:13.5px;margin-bottom:10px">{descricao_html}</p>
  <table class="imoveis">
    <thead><tr><th>ticker</th><th>fundo</th><th>idade</th><th>segmento</th><th>taxa</th><th class="col-selo">selo</th></tr></thead>
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
    cor = _COR_SELO.get(selo.nivel, "#7C8894")
    dica = "Alertas: " + "; ".join(motivos) if motivos else selo.descricao
    return (
        f'<span class="selo-dot" style="color:{cor}" title="{_e(dica)}">'
        f'<span class="pt" style="background:{cor}"></span>{_e(selo.rotulo)}</span>'
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
            f'<td class="col-selo">{_selo_tabela(par.selo, par.motivos)}</td></tr>'
        )
    media = raiox.pares_media
    linhas.append(
        f'<tr style="border-top:2px solid #263034"><td colspan="2"><b>média do segmento '
        f"({media.get('n', 0)} fundos)</b></td>"
        f"<td><b>{_celula(media.get('dy'), formato.percentual)}</b></td>"
        f"<td><b>{_celula(media.get('pvp'), formato.decimal)}</b></td>"
        f"<td><b>{_celula(media.get('pl'), formato.moeda_compacta)}</b></td><td class=\"col-selo\"></td></tr>"
    )
    return f"""
  <h2>Pares do segmento — {_e(raiox.classificacao)}{_ajuda("Pares do segmento")}</h2>
  <div class="grafico" style="overflow-x:auto">
  <table class="imoveis">
    <thead><tr><th>ticker</th><th>fundo</th><th>DY 12m</th><th>P/VP</th><th>PL</th><th class="col-selo">selo</th></tr></thead>
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
        cor = "#8FCB9B" if osc.variacao >= 0 else "#DB7A7A"
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
        cor, icone = "#DB7A7A", "⚠"
    elif continuidade:
        cor, icone = "#E3C25C", "⚠"
    elif tipo == "sem_ressalva":
        cor, icone = "#7BD69A", "✓"
    else:
        cor, icone = "#9AA7B2", "—"
    data = parecer.get("data_entrega", "")[:10]
    aviso_continuidade = (
        '<p style="color:#E3C25C;font-size:13.5px;margin-top:6px">⚠ o auditor apontou '
        "<b>incerteza relevante quanto à continuidade operacional</b> do fundo.</p>"
        if continuidade
        else ""
    )
    trecho = (
        f'<p class="evid" style="background:#0F1416;border:1px solid #1B2225;border-radius:7px;'
        f'padding:6px 10px;font-family:ui-monospace,Consolas,monospace;font-size:12.5px;'
        f'color:#9AA7B2;margin-top:8px">“{_e(parecer["trecho"])}”</p>'
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
        f'<h3 style="font-size:15px;color:#9AA7B2;margin:16px 0 8px">{titulo}'
        f' <span style="color:#9AA7B2;font-weight:400">({links})</span></h3>'
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
        f'<div class="nota" style="font-size:13px;margin-top:12px;border-top:1px solid #1B2225;'
        f'padding-top:10px"><b>Evolução desde a leitura anterior</b> ({_e(quando)}, relatório de '
        f"{_e(anterior.get('relatorio_data', '')[:10])}): {'; '.join(partes)}.{detalhe_alertas}"
        f"<br>Comparação factual entre duas fotos no tempo — o selo constata, não prevê; "
        f"variação de cota não valida nem invalida alerta.</div>"
    )


def _secao_ia(
    leitura: dict | None,
    agora: datetime,
    completo: AnaliseCompleta | None = None,
    classe: str = "fundo",
) -> str:
    if leitura and leitura.get("sem_relatorio"):
        verificado = leitura.get("verificado_em", "")[:10]
        bloco_fatos = _bloco_fatos_ia(leitura)
        quem = "pela empresa" if classe == "empresa" else "pelo fundo"
        nota_fatos = (
            f" Os <b>fatos relevantes e comunicados</b> publicados {quem} foram lidos pela IA e estão abaixo."
            if bloco_fatos
            else " Sem documentos novos, não há o que a IA ler."
        )
        # empresas não publicam relatório gerencial (isso é coisa de fundo/FNET):
        # a introdução explica a fonte certa de cada classe
        intro = (
            "Companhias abertas não publicam relatório gerencial — os documentos que assustam são os "
            "<b>fatos relevantes e comunicados ao mercado</b> (sistema IPE/CVM), e são eles que a IA lê aqui."
            if classe == "empresa"
            else "Este fundo <b>não publicou relatório gerencial</b> no FNET (é um documento opcional — "
            "muitos fundos divulgam apenas os informes obrigatórios da CVM, que já alimentam os "
            "indicadores e alertas desta página)."
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
  <div class="nota" style="font-size:13px">{intro}{nota_fatos}
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
                f' <span style="color:#E3C25C">⚠ documento de {idade_dias} dias atrás — '
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
    # duas bases para o dividendo anual do Gordon:
    #  - soma REAL dos últimos 12 meses (fiel, mas subestima quando há < 12 meses)
    #  - último dividendo × 12 (anualiza o mês corrente; vira o padrão quando faltam meses)
    div_12m = sum(v for v in dados.rend_por_mes[-12:] if v)
    ultimo_x12 = rendimento * 12
    n_meses = len(dados.dy_por_mes)
    div_padrao = div_12m if n_meses >= 12 else ultimo_x12
    dy_anual = (100 * div_padrao / preco) if preco else 0  # r inicial: com g=0 o justo parte da cotação
    # janela exata da soma de 12m: rend_por_mes e dy_por_mes são paralelos e já
    # cortados em [-12:], então as competências saem do dy_por_mes
    meses = [comp for comp, _ in dados.dy_por_mes]
    periodo = (
        f"{formato.competencia_br(meses[0])} e {formato.competencia_br(meses[-1])}"
        if meses
        else ""
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

  {_calculadora_gordon(preco, div_12m, ultimo_x12, dy_anual, rendimento, periodo, n_meses)}
"""


def _calculadora_gordon(
    preco: float,
    div_12m: float,
    ultimo_x12: float,
    dy_anual: float,
    ultimo_rend: float,
    periodo: str = "",
    n_meses: int = 12,
) -> str:
    """Preço justo pelo Modelo de Gordon — EXTRA opt-in: só abre se o usuário
    clicar, e o aviso de "não é recomendação" fica sempre visível ANTES do botão.
    r (desconto) e g (crescimento) são premissas DO USUÁRIO — o Scout nunca
    afirma um preço justo; oferece a ferramenta e mostra os fatos ao lado.

    O dividendo anual tem duas bases, escolhidas por rádio (sem o usuário abrir
    conta): a SOMA real dos últimos 12 meses e o ÚLTIMO dividendo × 12. Quando o
    fundo tem menos de 12 meses de histórico, a soma subestimaria o ano, então o
    padrão passa a ser o último × 12. `periodo` mostra a janela (mm/aaaa a mm/aaaa)
    da soma de 12 meses; `n_meses` é quantos meses realmente compõem essa soma.
    r começa no DY do próprio fundo — assim, com g=0, o preço justo parte da cotação."""
    tem_12m = n_meses >= 12
    div_padrao = div_12m if tem_12m else ultimo_x12
    if not preco or not div_padrao:
        return ""
    r_seed = f"{dy_anual:.1f}" if dy_anual else "10"
    # o campo mostra: no modo 12m, o dividendo ANUAL (soma real); no modo último,
    # o valor MENSAL — o × 12 é feito no calcGordon e exibido no caption gd-cap
    modo_padrao = "12m" if tem_12m else "ult"
    val_padrao = div_12m if tem_12m else ultimo_rend
    ativo12 = "ativo" if tem_12m else ""
    ativo_ult = "" if tem_12m else "ativo"
    btn_12m = "Soma dos últimos 12 meses" if tem_12m else f"Soma dos {n_meses} meses"
    base_padrao = "soma real dos últimos 12 meses" if tem_12m else "último dividendo × 12"
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
      <p class="desc">Modelo de Gordon: <b>preço justo = dividendo × (1 + g) / (r − g)</b>. As letras:
      <b>dividendo</b> = quanto o fundo paga por cota no ano; <b>r</b> = retorno anual que <b>VOCÊ</b>
      exige do fundo (a “taxa de desconto” — <b>não</b> é a taxa de administração); <b>g</b> = crescimento
      anual esperado dos dividendos. Tudo editável.</p>
      <div class="gd-base">Base do dividendo:
        <button type="button" class="{ativo12}" onclick="gordonBase('12m', this)">{btn_12m}</button>
        <button type="button" class="{ativo_ult}" onclick="gordonBase('ult', this)">Só o último dividendo mensal (× 12)</button>
      </div>
      <div class="campos gordon">
        <div><label for="gd-div">Dividendo por cota (R$)</label>
        <input type="number" id="gd-div" value="{val_padrao:.2f}" data-modo="{modo_padrao}" data-v12m="{div_12m:.2f}" data-vult="{ultimo_rend:.2f}" data-periodo="{periodo}" step="0.01" min="0" oninput="calcGordon()">
        <div id="gd-cap" class="gd-cap"></div></div>
        <div><label for="gd-r">Taxa de desconto — r (% a.a.)</label>
        <input type="number" id="gd-r" value="{r_seed}" step="0.5" min="0.1" oninput="calcGordon()">
        <div class="gd-cap">retorno que você exige ao ano — <b>não</b> é a taxa de administração; padrão = DY atual do fundo</div></div>
        <div><label for="gd-g">Crescimento — g (% a.a.)</label>
        <input type="number" id="gd-g" value="0" step="0.5" oninput="calcGordon()">
        <div class="gd-cap">quanto os dividendos crescem por ano (0 = sem crescimento)</div></div>
      </div>
      <div class="resultado">
        <div class="res"><div class="rotulo">Preço justo (com suas premissas)</div><div class="num" id="gd-justo">—</div></div>
        <div class="res"><div class="rotulo">Cotação atual (D-1)</div><div class="num">R$ {preco:.2f}</div></div>
      </div>
      <p class="aviso">Base padrão do dividendo: <b>{base_padrao}</b> — troque no botão acima (o
      último × 12 anualiza o mês corrente, útil quando o fundo tem menos de 12 meses). r começa no
      <b>DY atual do fundo</b> e g em 0 (por isso o preço justo parte da cotação) — ajuste r e g com as
      SUAS premissas. Modelo teórico (crescimento perpétuo constante), sensível às premissas: não é
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
    <label for="rent-reinvestir" style="all:unset;cursor:pointer;color:#9AA7B2;font-size:13px">
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
