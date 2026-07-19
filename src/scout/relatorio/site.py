"""Gera o site estático completo: índice buscável + página de cada FII.

Pensado para rodar no GitHub Actions e publicar no GitHub Pages, mas
funciona igual localmente: `scout site` gera tudo em uma pasta.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from .. import analise, armazenamento, formato, ranking
from . import apoio
from . import html as relatorio_html
from .html import CSS_MENU, JS_MENU, _e, menu_html

_COR_SELO = relatorio_html._COR_SELO
_URL_WORKFLOW = "https://github.com/Ruamms/scout/actions/workflows/site.yml"
_URL_API_RUNS = (
    "https://api.github.com/repos/Ruamms/scout/actions/workflows/site.yml/runs?per_page=1"
)


def gerar(
    con: sqlite3.Connection,
    destino: Path,
    com_cotacoes: bool = True,
    limite: int | None = None,
    ao_progredir: Callable[[str], None] | None = None,
    ao_item: Callable[[str, int, int], None] | None = None,
    agora: datetime | None = None,
    leituras_dir: Path | None = None,
    analytics: str = "",
) -> dict:
    """`ao_progredir(msg)` = log textual esporádico; `ao_item(fase, atual, total)`
    = callback por item, para barras de progresso. `analytics` = código
    GoatCounter (analytics sem cookie); vazio = nenhum rastreio (padrão)."""
    destino.mkdir(parents=True, exist_ok=True)
    progresso = ao_progredir or (lambda mensagem: None)
    item = ao_item or (lambda fase, atual, total: None)

    base = ranking.varrer(con)
    fundos = sorted(
        (resumo for resumo in base if resumo.ticker),
        key=lambda resumo: resumo.pl or 0,
        reverse=True,
    )
    # dois CNPJs podem derivar o mesmo ticker (fundo e classe pós-RCVM 175);
    # fica o de maior PL, que é o registro vivo
    vistos: set[str] = set()
    fundos = [f for f in fundos if not (f.ticker in vistos or vistos.add(f.ticker))]
    if limite:
        fundos = fundos[:limite]

    if com_cotacoes:
        from ..coleta import b3, b3rf, indices

        indices.garantir_atualizados(con)
        # UM arquivo da B3 cobre a base inteira (antes: 1 requisição por ticker)
        aviso = b3.garantir_mes_corrente(con)
        progresso(aviso or "cotações oficiais da B3 atualizadas (arquivo do mês corrente)")
        aviso_rf = b3rf.atualizar_diaria(con)
        if aviso_rf:
            progresso(aviso_rf)
        item("cotações", len(fundos), len(fundos))
        # re-varre para os resumos (P/VP dos rankings/pares) enxergarem os preços
        base = ranking.varrer(con)
        por_ticker = {resumo.ticker: resumo for resumo in base if resumo.ticker}
        fundos = [por_ticker.get(resumo.ticker, resumo) for resumo in fundos]

    from .. import leituras as modulo_leituras

    todas_leituras = (
        modulo_leituras.carregar_todas(leituras_dir) if leituras_dir else {}
    )
    tickers_no_site = {resumo.ticker for resumo in fundos}
    publicados = []
    for posicao, resumo in enumerate(fundos, start=1):
        completo = analise.montar_completo(con, resumo.ticker, varredura=base)
        if completo is None:
            continue
        relatorio_html.salvar(
            completo,
            destino,
            agora=agora,
            publicados=tickers_no_site,
            leitura=todas_leituras.get(resumo.ticker),
        )
        publicados.append(resumo)
        item("páginas", posicao, len(fundos))
        if posicao % 50 == 0:
            progresso(f"páginas: {posicao}/{len(fundos)}")

    # páginas de ETF (classe própria — ver docs/ETFS.md)
    from ..coleta import cda as coleta_cda
    from . import etf_html

    classificacoes = coleta_cda.carregar_classificacoes()
    etfs_publicados = []
    for etf in armazenamento.etfs_listados(con):
        dados_etf = etf_html.montar_dados_etf(con, etf["ticker"], classificacoes)
        if dados_etf is None or not (dados_etf["cotacao"] or dados_etf["pl"]):
            continue  # sem preço nem carteira: página vazia não ajuda ninguém
        (destino / f"{etf['ticker']}.html").write_text(
            etf_html.gerar(
                dados_etf,
                agora=agora,
                com_menu=True,
                leitura=todas_leituras.get(etf["ticker"]),
                publicados=tickers_no_site | {e["ticker"] for e in armazenamento.etfs_listados(con)},
            ),
            encoding="utf-8",
        )
        etfs_publicados.append(dados_etf)
        item("etfs", len(etfs_publicados), len(etfs_publicados))
    (destino / "etfs.html").write_text(
        _indice_etfs(etfs_publicados, agora or datetime.now()), encoding="utf-8"
    )
    progresso(f"etfs: {len(etfs_publicados)} páginas")

    apoio.salvar(destino, analytics)
    momento = agora or datetime.now()
    import json as _json

    (destino / "busca.json").write_text(
        _json.dumps(_ativos_busca(publicados, etfs_publicados), ensure_ascii=False),
        encoding="utf-8",
    )
    (destino / "fiis.html").write_text(_indice(publicados, base, momento), encoding="utf-8")
    (destino / "index.html").write_text(
        _home(publicados, etfs_publicados, momento), encoding="utf-8"
    )
    (destino / "comparar.html").write_text(
        _pagina_comparar(publicados), encoding="utf-8"
    )
    total_analytics = _injetar_analytics(destino, analytics)
    if total_analytics:
        progresso(f"analytics sem cookie (GoatCounter) em {total_analytics} páginas")
    return {"paginas": len(publicados), "etfs": len(etfs_publicados), "destino": str(destino)}


def _injetar_analytics(destino: Path, codigo: str) -> int:
    """Injeta o snippet de analytics antes de `</head>` em TODAS as páginas —
    um único ponto cobre home, listagens, páginas de ativo e apoio. Vazio
    quando não há código: nada é injetado (build local/testes ficam limpos)."""
    snippet = relatorio_html.analytics_script(codigo)
    if not snippet:
        return 0
    total = 0
    for caminho in destino.glob("*.html"):
        conteudo = caminho.read_text(encoding="utf-8")
        if "goatcounter" in conteudo or "</head>" not in conteudo:
            continue  # idempotente; página sem <head> (não deve acontecer) é pulada
        caminho.write_text(conteudo.replace("</head>", snippet + "\n</head>", 1), encoding="utf-8")
        total += 1
    return total


def _ativos_busca(fundos: list, etfs: list[dict]) -> list[dict]:
    """Índice compacto da busca viva (home embutida + busca.json das páginas)."""
    ativos = []
    for resumo in fundos:
        ativos.append(
            {
                "t": resumo.ticker,
                "n": resumo.nome[:48],
                "c": "FII",
                "s": resumo.selo.nivel,
                "r": resumo.selo.rotulo,
            }
        )
    for dados in etfs:
        ativos.append(
            {
                "t": dados["etf"]["ticker"],
                "n": (dados["etf"]["denominacao"] or "")[:48],
                "c": dados["classe"] or "ETF",
                "s": dados["selo"].nivel if dados["selo"] else "",
                "r": dados["selo"].rotulo if dados["selo"] else "",
            }
        )
    return ativos


def _home(fundos: list, etfs: list[dict], agora: datetime) -> str:
    """Home multi-classe: busca ao vivo em TUDO que temos + resumo por classe."""
    import json as _json

    ativos = _ativos_busca(fundos, etfs)
    json_ativos = _json.dumps(ativos, ensure_ascii=False).replace("</", "<\\/")
    cores_selo = _json.dumps(_COR_SELO)

    classes_etf: dict[str, int] = {}
    for dados in etfs:
        chave = dados["classe"] or "?"
        classes_etf[chave] = classes_etf.get(chave, 0) + 1
    pills = " ".join(
        f'<a class="pill" href="etfs.html?classe={_e(classe)}">{_e(classe)} <b>{total}</b></a>'
        for classe, total in sorted(classes_etf.items(), key=lambda kv: -kv[1])
    )

    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Scout — fatos, não dicas</title>
{relatorio_html.TAG_FAVICON}
<style>
:root {{ color-scheme: dark; }}
* {{ box-sizing:border-box; margin:0; }}
body {{ background:#101415; color:#F4F5F6; font-family:system-ui,sans-serif; line-height:1.5; }}
.pagina {{ max-width:1020px; margin:0 auto; padding:28px 20px 40px; }}
h1 {{ font-size:30px; margin:14px 0 6px; }}
.meta {{ color:#8b98a9; font-size:14px; }}
a {{ color:#8FCB9B; }}
.busca-caixa {{ position:relative; margin:22px 0 8px; }}
input#busca {{ width:100%; background:#182024; color:#F4F5F6; border:1px solid #314045;
  border-radius:12px; padding:14px 18px; font-size:17px; }}
#resultados {{ position:absolute; top:100%; left:0; right:0; z-index:30; background:#182024;
  border:1px solid #314045; border-radius:12px; margin-top:6px; overflow:hidden;
  box-shadow:0 16px 44px rgba(0,0,0,.55); }}
#resultados a {{ display:flex; align-items:center; gap:10px; padding:10px 14px;
  color:#F4F5F6; text-decoration:none; border-bottom:1px solid #232D31; }}
#resultados a:last-child {{ border-bottom:none; }}
#resultados a:hover, #resultados a.foco {{ background:#232D31; }}
#resultados .tk {{ font-weight:800; min-width:74px; }}
#resultados .nm {{ color:#8b98a9; font-size:13px; flex:1; overflow:hidden; white-space:nowrap; text-overflow:ellipsis; }}
#resultados .badge {{ font-size:10.5px; font-weight:700; letter-spacing:.05em; text-transform:uppercase;
  background:#232D31; color:#8FCB9B; border:1px solid #314045; border-radius:99px; padding:2px 9px; white-space:nowrap; }}
#resultados .ponto {{ width:9px; height:9px; border-radius:50%; flex-shrink:0; }}
.blocos {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:14px; margin-top:22px; }}
.bloco {{ background:#182024; border:1px solid #232D31; border-radius:12px; padding:18px; }}
.bloco h2 {{ font-size:18px; margin-bottom:4px; }}
.bloco .num {{ font-size:30px; font-weight:800; color:#8FCB9B; }}
.bloco p {{ color:#8b98a9; font-size:13.5px; margin:6px 0 10px; }}
.pill {{ display:inline-block; background:#232D31; border:1px solid #314045; color:#aeb9c7;
  border-radius:99px; padding:3px 12px; font-size:12px; text-decoration:none; margin:2px 2px 2px 0; }}
.pill:hover {{ border-color:#8FCB9B; color:#8FCB9B; }}
.pill b {{ color:#8FCB9B; }}
.btn {{ display:inline-block; background:#3E8E7E; color:#F4F5F6; border-radius:8px; padding:8px 18px;
  font-size:13.5px; font-weight:700; text-decoration:none; }}
.rodape {{ color:#8b98a9; font-size:12.5px; border-top:1px solid #232D31; margin-top:30px; padding-top:14px; }}
#aviso-beta {{ position:fixed; inset:0; background:rgba(16,20,21,.75); z-index:50;
  display:flex; align-items:center; justify-content:center; padding:20px; }}
#aviso-beta[hidden] {{ display:none; }}
.beta-caixa {{ background:#182024; border:1px solid #314045; border-radius:12px; padding:22px 24px;
  max-width:440px; font-size:14px; box-shadow:0 12px 40px rgba(0,0,0,.5); }}
.beta-caixa p {{ color:#aeb9c7; margin:10px 0 14px; }}
.beta-caixa button {{ background:#3E8E7E; color:#F4F5F6; border:none; border-radius:8px;
  padding:8px 22px; font-size:13.5px; font-weight:700; cursor:pointer; }}
{CSS_MENU}
{relatorio_html.CSS_MARCA}
</style>
</head>
<body>
<div id="aviso-beta" hidden>
  <div class="beta-caixa">
    <b>🧭 O Scout está em beta.</b>
    <p>Os dados vêm de fontes oficiais, mas o site é novo e pode conter falhas. Encontrou algo estranho?
    Reporte em <a href="https://github.com/Ruamms/scout/issues" target="_blank" rel="noopener">github.com/Ruamms/scout/issues</a>
    ou por e-mail: <a href="mailto:ruamms3@gmail.com">ruamms3@gmail.com</a>.</p>
    <button onclick="fecharBeta()">Entendi</button>
  </div>
</div>
<div class="pagina">
  {relatorio_html.marca_html()}
  {menu_html()}
  <h1>Lemos os documentos oficiais para que você não precise</h1>
  <div class="meta">Raio-x com dados públicos oficiais (CVM, B3, Banco Central), alertas com a conta
  e a fonte, e IA local lendo os relatórios — fatos, não dicas. A decisão é sua.</div>

  <div class="busca-caixa">
    <input id="busca" type="search" autocomplete="off"
     placeholder="Digite um ticker ou nome… (ex.: MXRF11, BOVA, shopping)"
     oninput="buscar()" onkeydown="navegar(event)">
    <div id="resultados" hidden></div>
  </div>
  <div class="meta" style="font-size:12px">a busca cobre tudo o que já analisamos: {len(fundos)} FIIs e {len(etfs)} ETFs</div>

  <div class="blocos">
    <div class="bloco">
      <h2>🏢 Fundos Imobiliários</h2>
      <div class="num">{len(fundos)}</div>
      <p>Raio-x completo: red flags com evidência, parecer do auditor, imóveis com vacância,
      gestora, leitura por IA dos relatórios e comunicados.</p>
      <a class="btn" href="fiis.html">ver todos os FIIs</a>
      <a class="pill" href="fiis.html#rankings" style="margin-left:8px">rankings do dia</a>
      <a class="pill" href="comparar.html">⚖ comparar</a>
    </div>
    <div class="bloco">
      <h2>📊 ETFs</h2>
      <div class="num">{len(etfs)}</div>
      <p>Cada página traz as REGRAS do tipo (distribuição, tributação) que quase ninguém conta,
      a carteira oficial e o selo com alertas próprios da classe.</p>
      <a class="btn" href="etfs.html">ver todos os ETFs</a>
      <div style="margin-top:10px">{pills}</div>
    </div>
  </div>

  <div class="rodape">Não é recomendação de investimento. Fontes: dados abertos da CVM, B3 (COTAHIST
  e fundos listados) e Banco Central. Critérios públicos e auditáveis:
  <a href="https://github.com/Ruamms/scout">github.com/Ruamms/scout</a> ·
  <a href="apoie.html">☕ apoie o projeto</a> · atualizado em {agora.strftime("%d/%m/%Y %H:%M")}</div>
</div>
<script>
const ATIVOS = {json_ativos};
const CORES_SELO = {cores_selo};
let indiceFoco = -1;

function buscar() {{
  const termo = document.getElementById('busca').value.trim().toLowerCase();
  const caixa = document.getElementById('resultados');
  indiceFoco = -1;
  if (termo.length < 2) {{ caixa.hidden = true; caixa.innerHTML = ''; return; }}
  const achados = ATIVOS.filter(a =>
    a.t.toLowerCase().includes(termo) || a.n.toLowerCase().includes(termo) || a.c.toLowerCase().includes(termo)
  ).slice(0, 8);
  if (window.scoutBusca) scoutBusca(termo, achados.length > 0);
  if (!achados.length) {{
    caixa.innerHTML = '<a><span class="nm">nada encontrado — cobrimos FIIs e ETFs da B3</span></a>';
    caixa.hidden = false;
    return;
  }}
  caixa.innerHTML = achados.map(a =>
    `<a href="${{a.t}}.html"><span class="tk">${{a.t}}</span><span class="nm">${{a.n}}</span>` +
    (a.s ? `<span class="ponto" style="background:${{CORES_SELO[a.s] || '#94a3b8'}}" title="${{a.r}}"></span>` : '') +
    `<span class="badge">${{a.c}}</span></a>`
  ).join('');
  caixa.hidden = false;
}}

function navegar(evento) {{
  const links = document.querySelectorAll('#resultados a[href]');
  if (!links.length) return;
  if (evento.key === 'ArrowDown' || evento.key === 'ArrowUp') {{
    evento.preventDefault();
    indiceFoco = (indiceFoco + (evento.key === 'ArrowDown' ? 1 : -1) + links.length) % links.length;
    links.forEach((l, i) => l.classList.toggle('foco', i === indiceFoco));
  }} else if (evento.key === 'Enter') {{
    (links[Math.max(indiceFoco, 0)]).click();
  }} else if (evento.key === 'Escape') {{
    document.getElementById('resultados').hidden = true;
  }}
}}

if (!localStorage.getItem('scout-beta-visto')) {{
  document.getElementById('aviso-beta').hidden = false;
}}
function fecharBeta() {{
  localStorage.setItem('scout-beta-visto', '1');
  document.getElementById('aviso-beta').hidden = true;
}}
{JS_MENU}
</script>
</body>
</html>
"""


def _indice_etfs(etfs: list[dict], agora) -> str:
    """Listagem dos ETFs publicados — filtro por classe + busca simples."""
    from .. import formato

    classes = sorted({dados["classe"] or "?" for dados in etfs})
    botoes = "".join(
        f'<button class="filtro" onclick="filtraClasse(this, \'{_e(classe)}\')">{_e(classe)}</button>'
        for classe in classes
    )
    linhas = []
    for dados in sorted(etfs, key=lambda d: d["etf"]["ticker"]):
        etf = dados["etf"]
        classe = dados["classe"] or "?"
        preco = f"R$ {formato.decimal(dados['preco_atual'])}" if dados["preco_atual"] else "—"
        variacao = (
            formato.percentual(dados["variacao_12m"], sinal=True)
            if dados["variacao_12m"] is not None
            else "—"
        )
        pl = formato.moeda_compacta(dados["pl"]["pl"]) if dados["pl"] else "—"
        selo_html = "—"
        if dados.get("selo"):
            cor = _COR_SELO.get(dados["selo"].nivel, "#94a3b8")
            motivos = "; ".join(flag.titulo for flag in dados["flags"].flags) or dados["selo"].descricao
            selo_html = (
                f'<span class="selo" style="background:{cor}" title="{_e(motivos)}">'
                f"{_e(dados['selo'].rotulo)}</span>"
            )
        from .etf_html import _trunca

        busca = f"{etf['ticker']} {etf['denominacao'] or ''} {classe}".lower().replace('"', "")
        linhas.append(
            f'<tr data-busca="{busca}" data-classe="{_e(classe)}">'
            f'<td><a href="{etf["ticker"]}.html">{etf["ticker"]}</a></td>'
            f'<td title="{_e(etf["denominacao"] or "")}">{_e(_trunca(etf["denominacao"] or "", 48))}</td>'
            f"<td>{_e(classe)}</td><td>{preco}</td><td>{variacao}</td><td>{pl}</td>"
            f"<td>{selo_html}</td></tr>"
        )
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ETFs — Scout</title>
{relatorio_html.TAG_FAVICON}
<style>
:root {{ color-scheme: dark; }}
* {{ box-sizing:border-box; margin:0; }}
body {{ background:#101415; color:#F4F5F6; font-family:system-ui,sans-serif; line-height:1.5; }}
.pagina {{ max-width:1020px; margin:0 auto; padding:28px 20px 40px; }}
h1 {{ font-size:24px; margin:8px 0 4px; }}
.meta {{ color:#8b98a9; font-size:13px; margin-bottom:12px; }}
a {{ color:#8FCB9B; }}
input#busca {{ width:100%; background:#182024; color:#F4F5F6; border:1px solid #314045;
  border-radius:10px; padding:11px 15px; font-size:15px; margin:8px 0 10px; }}
.filtros {{ display:flex; gap:8px; flex-wrap:wrap; margin-bottom:12px; }}
.filtro {{ background:#232D31; color:#8b98a9; border:1px solid #314045; border-radius:99px;
  padding:4px 14px; font-size:12.5px; cursor:pointer; }}
.filtro.ativo {{ background:#8FCB9B; color:#101415; border-color:#8FCB9B; font-weight:700; }}
table {{ width:100%; border-collapse:collapse; font-size:13.5px; }}
th {{ color:#8b98a9; font-size:11.5px; text-transform:uppercase; letter-spacing:.05em;
  text-align:left; padding:8px 10px;
  position:sticky; top:0; z-index:2; background:#101415;
  box-shadow:inset 0 -1px 0 #314045; }}
td {{ padding:7px 10px; border-bottom:1px solid #232D31; }}
td:nth-child(n+4), th:nth-child(n+4) {{ text-align:right; }}
tbody tr:hover td {{ background:#182024; }}
.selo {{ display:inline-block; padding:2px 10px; border-radius:999px; font-weight:700;
  font-size:11px; color:#101415; white-space:nowrap; }}
.rodape {{ color:#8b98a9; font-size:12.5px; border-top:1px solid #232D31; margin-top:26px; padding-top:12px; }}
{CSS_MENU}
{relatorio_html.CSS_MARCA}
</style>
</head>
<body>
<div class="pagina">
  {relatorio_html.marca_html("index.html")}
  {menu_html()}
  <h1>ETFs</h1>
  <div class="meta">{len(etfs)} ETFs com dados oficiais (B3 + CVM) · cada página traz as
  REGRAS do tipo (distribuição, tributação) que quase ninguém conta ·
  <a href="index.html">ver FIIs</a> · atualizado em {agora.strftime("%d/%m/%Y %H:%M")}</div>
  <input id="busca" type="search" placeholder="Busque por ticker, nome ou classe… (ex.: BOVA, cripto, renda fixa)"
   oninput="filtrar()">
  <div class="filtros"><button class="filtro ativo" onclick="filtraClasse(this, '')">Todas</button>{botoes}</div>
  <table id="etfs">
    <thead><tr><th>ticker</th><th>fundo</th><th>classe</th><th>preço (D-1)</th><th>12 meses</th><th>PL</th><th>selo</th></tr></thead>
    <tbody>{"".join(linhas)}</tbody>
  </table>
  <div class="rodape">Não é recomendação de investimento. Fontes: B3 e CVM — critérios públicos:
  <a href="https://github.com/Ruamms/scout">github.com/Ruamms/scout</a> ·
  <a href="apoie.html">☕ apoie o projeto</a></div>
</div>
<script>
let classeAtiva = '';
function filtrar() {{
  const termo = document.getElementById('busca').value.trim().toLowerCase();
  document.querySelectorAll('#etfs tbody tr').forEach(tr => {{
    const casaTermo = termo === '' || tr.dataset.busca.includes(termo);
    const casaClasse = classeAtiva === '' || tr.dataset.classe === classeAtiva;
    tr.hidden = !(casaTermo && casaClasse);
  }});
}}
function filtraClasse(botao, classe) {{
  classeAtiva = classe;
  document.querySelectorAll('.filtro').forEach(b => b.classList.toggle('ativo', b === botao));
  filtrar();
}}
// ?classe=X na URL (vindo do menu ou da home) pré-seleciona o filtro
const classeUrl = new URLSearchParams(location.search).get('classe');
if (classeUrl) {{
  const botao = Array.from(document.querySelectorAll('.filtro')).find(b => b.textContent === classeUrl);
  if (botao) filtraClasse(botao, classeUrl);
}}
{JS_MENU}
</script>
</body>
</html>
"""


def _pagina_comparar(fundos: list) -> str:
    """Comparador lado a lado: os MESMOS fatos de cada fundo, em colunas.
    Sem destaque de 'vencedor' — comparação de fatos, não recomendação."""
    import json as _json

    from .. import formato

    def _ou_traco(valor, formatador):
        return formatador(valor) if valor is not None else "—"

    dados = {
        resumo.ticker: {
            "nome": resumo.nome[:60],
            "segmento": resumo.segmento,
            "selo": resumo.selo.rotulo,
            "cor": _COR_SELO.get(resumo.selo.nivel, "#94a3b8"),
            "motivos": list(resumo.motivos),
            "cotacao": _ou_traco(resumo.cotacao, lambda v: f"R$ {formato.decimal(v)}"),
            "dy": _ou_traco(resumo.dy_12m, formato.percentual),
            "pvp": _ou_traco(resumo.pvp, formato.decimal),
            "pl": _ou_traco(resumo.pl, formato.moeda_compacta),
            "cotistas": _ou_traco(resumo.cotistas, lambda v: f"{v:,.0f}".replace(",", ".")),
            "idade": f"{resumo.meses / 12:.0f} anos" if resumo.meses >= 12 else f"{resumo.meses} meses",
        }
        for resumo in fundos
    }
    json_dados = _json.dumps(dados, ensure_ascii=False).replace("</", "<\\/")
    opcoes = "".join(f'<option value="{r.ticker}">{r.ticker}</option>' for r in fundos)
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Comparar FIIs — Scout</title>
{relatorio_html.TAG_FAVICON}
<style>
:root {{ color-scheme: dark; }}
* {{ box-sizing:border-box; margin:0; }}
body {{ background:#101415; color:#F4F5F6; font-family:system-ui,sans-serif; line-height:1.5; }}
.pagina {{ max-width:960px; margin:0 auto; padding:28px 20px 40px; }}
h1 {{ font-size:24px; margin:8px 0 4px; }}
.meta {{ color:#8b98a9; font-size:13px; margin-bottom:16px; }}
a {{ color:#8FCB9B; }}
select {{ background:#182024; color:#F4F5F6; border:1px solid #314045; border-radius:8px;
  padding:9px 12px; font-size:15px; min-width:130px; }}
.seletores {{ display:flex; gap:10px; flex-wrap:wrap; margin-bottom:18px; }}
table {{ width:100%; border-collapse:collapse; font-size:14px; }}
th, td {{ padding:9px 10px; border-bottom:1px solid #232D31; text-align:left; }}
th {{ color:#8b98a9; font-size:11.5px; text-transform:uppercase; letter-spacing:.05em; }}
td:first-child {{ color:#8b98a9; font-size:12.5px; text-transform:uppercase; letter-spacing:.04em; white-space:nowrap; }}
tbody tr:hover td {{ background:#182024; }}
.selo {{ display:inline-block; padding:2px 10px; border-radius:999px; font-weight:700;
  font-size:11px; color:#101415; white-space:nowrap; }}
.rodape {{ color:#8b98a9; font-size:12.5px; border-top:1px solid #232D31; margin-top:26px; padding-top:12px; }}
{CSS_MENU}
{relatorio_html.CSS_MARCA}
</style>
</head>
<body>
<div class="pagina">
  {relatorio_html.marca_html("index.html")}
  {menu_html()}
  <h1>⚖ Comparar FIIs</h1>
  <div class="meta">os mesmos fatos, lado a lado — sem "vencedor": a decisão é sua ·
  <a href="index.html">voltar para todos os fundos</a></div>
  <div class="seletores">
    <select id="f1" onchange="renderiza()"><option value="">fundo 1…</option>{opcoes}</select>
    <select id="f2" onchange="renderiza()"><option value="">fundo 2…</option>{opcoes}</select>
    <select id="f3" onchange="renderiza()"><option value="">fundo 3 (opcional)…</option>{opcoes}</select>
  </div>
  <div id="tabela"></div>
  <div class="rodape">Comparação factual com dados públicos oficiais — não é recomendação de investimento.
  Critérios e código: <a href="https://github.com/Ruamms/scout">github.com/Ruamms/scout</a> ·
  <a href="apoie.html">☕ apoie o projeto</a></div>
</div>
<script>
const DADOS = {json_dados};
const LINHAS = [
  ["Fundo", d => d.nome],
  ["Segmento", d => d.segmento],
  ["Selo", d => `<span class="selo" style="background:${{d.cor}}" title="${{(d.motivos || []).join('; ')}}">${{d.selo}}</span>`],
  ["Cotação", d => d.cotacao],
  ["DY 12 meses", d => d.dy],
  ["P/VP", d => d.pvp],
  ["Patrimônio", d => d.pl],
  ["Cotistas", d => d.cotistas],
  ["Idade na base", d => d.idade],
  ["Alertas", d => (d.motivos && d.motivos.length) ? d.motivos.join("<br>") : "nenhum alerta disparado"],
];
function renderiza() {{
  const escolhidos = ["f1", "f2", "f3"]
    .map(id => document.getElementById(id).value)
    .filter(t => t && DADOS[t]);
  const alvo = document.getElementById("tabela");
  if (escolhidos.length < 2) {{ alvo.innerHTML = '<p class="meta">escolha pelo menos dois fundos acima.</p>'; return; }}
  const cabecalho = "<tr><th></th>" + escolhidos.map(t => `<th><a href="${{t}}.html">${{t}}</a></th>`).join("") + "</tr>";
  const corpo = LINHAS.map(([rotulo, extrator]) =>
    "<tr><td>" + rotulo + "</td>" + escolhidos.map(t => "<td>" + extrator(DADOS[t]) + "</td>").join("") + "</tr>"
  ).join("");
  alvo.innerHTML = "<table><thead>" + cabecalho + "</thead><tbody>" + corpo + "</tbody></table>";
}}
renderiza();
const parametros = new URLSearchParams(location.search);
["f1", "f2", "f3"].forEach(id => {{
  const ticker = (parametros.get(id) || "").toUpperCase();
  if (ticker && DADOS[ticker]) document.getElementById(id).value = ticker;
}});
renderiza();
{JS_MENU}
</script>
</body>
</html>
"""


_VISIVEIS_DE_INICIO = 50  # tabela abre com os maiores por PL; o resto sob demanda


def _indice(fundos: list, base: list, agora: datetime) -> str:
    linhas = "".join(
        _linha_fundo(resumo, extra=posicao >= _VISIVEIS_DE_INICIO)
        for posicao, resumo in enumerate(fundos)
    )
    rankings = "".join(
        _bloco_ranking(titulo, ranking.montar(None, por=por, top=10, sem_alertas=sem_alertas, fundos=base))
        for titulo, por, sem_alertas in (
            ("Maior DY 12m, sem alertas de atenção", "dy", True),
            ("Menor P/VP, sem alertas de atenção", "pvp", True),
            ("Maiores patrimônios", "pl", False),
        )
    )
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FIIs — Scout</title>
{relatorio_html.TAG_FAVICON}
<style>
:root {{ color-scheme: dark; }}
* {{ box-sizing:border-box; margin:0; }}
body {{ background:#101415; color:#F4F5F6; font-family:system-ui,sans-serif; line-height:1.5; }}
.pagina {{ max-width:1020px; margin:0 auto; padding:28px 20px 40px; }}
.marca {{ color:#8b98a9; font-size:14px; letter-spacing:.14em; text-transform:uppercase; }}
h1 {{ font-size:30px; margin:4px 0 6px; }}
.meta {{ color:#8b98a9; font-size:13px; }}
a {{ color:#8FCB9B; }}
input#busca {{ width:100%; background:#182024; color:#F4F5F6; border:1px solid #314045;
  border-radius:10px; padding:12px 16px; font-size:16px; margin:18px 0 10px; }}
.atualizacao {{ display:flex; align-items:center; gap:12px; flex-wrap:wrap; margin-top:10px; }}
.btn-atu {{ background:#232D31; border:1px solid #314045; color:#8FCB9B; text-decoration:none;
  padding:5px 13px; border-radius:8px; font-size:12.5px; font-weight:600; }}
.btn-atu:hover {{ border-color:#8FCB9B; }}
.barra {{ width:180px; height:6px; background:#232D31; border-radius:99px; overflow:hidden; }}
.barra .preencher {{ width:40%; height:100%; background:#8FCB9B; border-radius:99px;
  animation: desliza 1.2s ease-in-out infinite; }}
@keyframes desliza {{ 0% {{ margin-left:-40%; }} 100% {{ margin-left:100%; }} }}
table {{ width:100%; border-collapse:collapse; font-size:13.5px; }}
th {{ color:#8b98a9; font-size:11.5px; text-transform:uppercase; letter-spacing:.05em;
  text-align:left; padding:8px 10px; position:sticky; top:0; z-index:2; background:#101415;
  box-shadow:inset 0 -1px 0 #314045; }}
td {{ padding:7px 10px; border-bottom:1px solid #232D31; }}
tbody tr:hover td {{ background:#182024; }}
.btn-todos {{ display:block; margin:12px auto 0; background:#232D31; border:1px solid #314045;
  color:#8FCB9B; padding:8px 22px; border-radius:8px; font-size:13.5px; font-weight:600; cursor:pointer; }}
.btn-todos:hover {{ border-color:#8FCB9B; }}
td:not(:first-child):not(:nth-child(2)):not(:nth-child(3)), th:not(:first-child):not(:nth-child(2)):not(:nth-child(3)) {{ text-align:right; }}
.selo {{ display:inline-block; padding:2px 10px; border-radius:999px; font-weight:700;
  font-size:11px; color:#101415; white-space:nowrap; }}
h2 {{ font-size:18px; margin:28px 0 10px; }}
.blocos {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:14px; }}
.bloco {{ background:#182024; border:1px solid #232D31; border-radius:10px; padding:14px 16px; }}
.bloco h3 {{ font-size:14px; color:#aeb9c7; margin-bottom:8px; }}
.bloco ol {{ padding-left:22px; font-size:13.5px; }}
.bloco li {{ margin:4px 0; }}
.rodape {{ color:#8b98a9; font-size:12.5px; border-top:1px solid #232D31; margin-top:30px; padding-top:14px; }}
#aviso-beta {{ position:fixed; inset:0; background:rgba(16,20,21,.75); z-index:50;
  display:flex; align-items:center; justify-content:center; padding:20px; }}
#aviso-beta[hidden] {{ display:none; }}
.beta-caixa {{ background:#182024; border:1px solid #314045; border-radius:12px; padding:22px 24px;
  max-width:440px; font-size:14px; box-shadow:0 12px 40px rgba(0,0,0,.5); }}
.beta-caixa p {{ color:#aeb9c7; margin:10px 0 14px; }}
.beta-caixa button {{ background:#3E8E7E; color:#F4F5F6; border:none; border-radius:8px;
  padding:8px 22px; font-size:13.5px; font-weight:700; cursor:pointer; }}
{CSS_MENU}
{relatorio_html.CSS_MARCA}
</style>
</head>
<body>
<div id="aviso-beta" hidden>
  <div class="beta-caixa">
    <b>🧭 O Scout está em beta.</b>
    <p>Os dados vêm de fontes oficiais, mas o site é novo e pode conter falhas de exibição ou
    leitura. Encontrou algo estranho? Ajude reportando em
    <a href="https://github.com/Ruamms/scout/issues" target="_blank" rel="noopener">github.com/Ruamms/scout/issues</a>
    ou por e-mail: <a href="mailto:ruamms3@gmail.com">ruamms3@gmail.com</a>.</p>
    <button onclick="fecharBeta()">Entendi</button>
  </div>
</div>
<div class="pagina">
  {relatorio_html.marca_html("index.html")}
  {menu_html()}
  <h1>Fundos Imobiliários</h1>
  <div class="meta" style="font-size:14.5px;margin-bottom:4px">"Será que tem algum problema
  escondido naquele relatório?" — essa dúvida vira uma lista de alertas com a conta e a
  fonte de cada um. Informes da CVM, relatório gerencial e cotações, num raio-x por fundo.</div>
  <div class="meta">{len(fundos)} fundos negociáveis analisados com dados públicos oficiais ·
  atualizado em {agora.strftime("%d/%m/%Y %H:%M")} ·
  <a href="etfs.html">📊 ETFs</a> ·
  <a href="comparar.html">⚖ comparar fundos</a> ·
  <a href="apoie.html">☕ apoie o projeto</a></div>

  <div class="atualizacao">
    <span id="atu-texto" class="meta">verificando status da atualização…</span>
    <div id="atu-barra" class="barra" hidden><div class="preencher"></div></div>
    <a class="btn-atu" href="{_URL_WORKFLOW}" target="_blank" rel="noopener"
     title="Abre o GitHub Actions — clique em 'Run workflow' para atualizar agora (requer permissão no repositório)">
    🔄 Atualizar agora</a>
  </div>

  <input id="busca" type="search" placeholder="Busque por ticker, nome ou segmento… (ex.: HGLG, shopping, logística)"
   oninput="filtrar(this.value)">

  <table id="fundos">
    <thead><tr><th>ticker</th><th>fundo</th><th>segmento</th><th>DY 12m</th><th>P/VP</th><th>PL</th><th>selo</th></tr></thead>
    <tbody>{linhas}</tbody>
  </table>
  <button id="ver-todos" class="btn-todos" onclick="mostrarTodos()"
   {"hidden" if len(fundos) <= _VISIVEIS_DE_INICIO else ""}>Mostrar todos os {len(fundos)} fundos
   (acima: os {min(len(fundos), _VISIVEIS_DE_INICIO)} maiores por patrimônio)</button>

  <h2 id="rankings">Rankings do dia</h2>
  <div class="blocos">{rankings}</div>
  <p class="meta" style="margin-top:8px">rankings são fatos ordenados com critério explícito — não recomendação ·
  só fundos negociáveis · "sem alertas de atenção" = selo verde ou amarelo</p>

  <div class="rodape">Isto não é recomendação de investimento. Fontes: dados abertos da CVM,
  Banco Central (SGS) e cotações oficiais da B3 (COTAHIST). Critérios de todos os alertas são públicos:
  <a href="https://github.com/Ruamms/scout">github.com/Ruamms/scout</a> ·
  <a href="apoie.html">☕ apoie o projeto</a></div>
</div>
<script>
// aviso de beta: aparece só na primeira visita (dispensado fica em localStorage)
if (!localStorage.getItem('scout-beta-visto')) {{
  document.getElementById('aviso-beta').hidden = false;
}}
function fecharBeta() {{
  localStorage.setItem('scout-beta-visto', '1');
  document.getElementById('aviso-beta').hidden = true;
}}

let todosVisiveis = false;

function filtrar(texto) {{
  const termo = texto.trim().toLowerCase();
  document.querySelectorAll('#fundos tbody tr').forEach(tr => {{
    const casa = termo === '' || tr.dataset.busca.includes(termo);
    const recolhida = termo === '' && !todosVisiveis && tr.classList.contains('fundo-extra');
    tr.hidden = !casa || recolhida;
  }});
  const botao = document.getElementById('ver-todos');
  if (botao) botao.hidden = todosVisiveis || termo !== '' || !document.querySelector('.fundo-extra');
}}

function mostrarTodos() {{
  todosVisiveis = true;
  document.querySelectorAll('.fundo-extra').forEach(tr => tr.hidden = false);
  document.getElementById('ver-todos').hidden = true;
}}

// status da atualização via API pública do GitHub (repo público: sem token)
async function statusAtualizacao() {{
  const texto = document.getElementById('atu-texto');
  const barra = document.getElementById('atu-barra');
  try {{
    const resposta = await fetch('{_URL_API_RUNS}');
    const dados = await resposta.json();
    const run = (dados.workflow_runs || [])[0];
    if (!run) {{ texto.textContent = ''; return; }}
    const quando = new Date(run.run_started_at).toLocaleString('pt-BR',
      {{day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit'}});
    if (run.status === 'completed') {{
      barra.hidden = true;
      texto.textContent = run.conclusion === 'success'
        ? `última atualização concluída em ${{quando}}`
        : `última atualização falhou (${{quando}}) — veja o log no GitHub`;
    }} else {{
      barra.hidden = false;
      texto.textContent = `atualização em andamento (iniciada ${{quando}})… a página recarrega ao concluir`;
      setTimeout(async () => {{
        const r2 = await fetch('{_URL_API_RUNS}');
        const d2 = await r2.json();
        if ((d2.workflow_runs || [])[0]?.status === 'completed') location.reload();
        else statusAtualizacao();
      }}, 30000);
    }}
  }} catch (e) {{ texto.textContent = ''; }}
}}
statusAtualizacao();
{JS_MENU}
</script>
</body>
</html>
"""


def _linha_fundo(resumo, extra: bool = False) -> str:
    def _ou_traco(valor, formatador):
        return formatador(valor) if valor is not None else "—"

    cor = _COR_SELO.get(resumo.selo.nivel, "#94a3b8")
    dica = "Alertas: " + "; ".join(resumo.motivos) if resumo.motivos else resumo.selo.descricao
    busca = f"{resumo.ticker} {resumo.nome} {resumo.segmento}".lower().replace('"', "")
    oculta = ' class="fundo-extra" hidden' if extra else ""
    return (
        f'<tr data-busca="{busca}"{oculta}>'
        f'<td><a href="{resumo.ticker}.html">{resumo.ticker}</a></td>'
        f"<td>{resumo.nome[:42]}</td><td>{resumo.segmento}</td>"
        f"<td>{_ou_traco(resumo.dy_12m, formato.percentual)}</td>"
        f"<td>{_ou_traco(resumo.pvp, formato.decimal)}</td>"
        f"<td>{_ou_traco(resumo.pl, formato.moeda_compacta)}</td>"
        f'<td><span class="selo" style="background:{cor}" title="{dica}">{resumo.selo.rotulo}</span></td></tr>'
    )


def _bloco_ranking(titulo: str, resultado) -> str:
    itens = "".join(
        f'<li><a href="{linha.ticker}.html">{linha.ticker}</a> — '
        f"{_valor_criterio(resultado.criterio, linha)}</li>"
        for linha in resultado.linhas
    )
    return f'<div class="bloco"><h3>{titulo}</h3><ol>{itens or "<li>—</li>"}</ol></div>'


def _valor_criterio(criterio: str, linha) -> str:
    if criterio == "dy":
        return f"DY {formato.percentual(linha.dy_12m)}"
    if criterio == "pvp":
        return f"P/VP {formato.decimal(linha.pvp)}"
    if criterio == "pl":
        return f"PL {formato.moeda_compacta(linha.pl)}"
    return ""
