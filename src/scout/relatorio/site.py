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
    reportar: str = "",
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

    # páginas de AÇÃO (uma página por PAPEL, mostrando a empresa) — montadas
    # ANTES dos ETFs: as "Principais posições" do ETF linkam qualquer ativo
    # que o Scout publica e mostram o selo dele (as páginas conversam)
    from . import acao_html

    tickers_acoes = {
        papel["ticker"]
        for empresa in armazenamento.empresas_listadas(con)
        for papel in armazenamento.papeis_da_empresa(con, empresa["cod_cvm"])
    }
    # comparação setorial: medianas por setor calculadas 1× para o build inteiro
    medianas = acao_html.medianas_setor(con)
    acoes_publicadas = []
    for empresa in armazenamento.empresas_listadas(con):
        papeis_empresa = armazenamento.papeis_da_empresa(con, empresa["cod_cvm"])
        # a leitura por IA é da EMPRESA (o lote grava no 1º papel): toda página
        # de papel da mesma empresa exibe a mesma leitura
        leitura_empresa = next(
            (todas_leituras[p["ticker"]] for p in papeis_empresa if p["ticker"] in todas_leituras),
            None,
        )
        for papel in papeis_empresa:
            dados_acao = acao_html.montar_dados_acao(con, papel["ticker"], medianas=medianas)
            if dados_acao is None or not dados_acao["cotacao"]:
                continue  # papel sem pregão na base não gera página
            (destino / f"{papel['ticker']}.html").write_text(
                acao_html.gerar(
                    dados_acao,
                    agora=agora,
                    com_menu=True,
                    leitura=leitura_empresa,
                    publicados=tickers_acoes,
                ),
                encoding="utf-8",
            )
            acoes_publicadas.append(dados_acao)
            item("ações", len(acoes_publicadas), len(acoes_publicadas))
    (destino / "acoes.html").write_text(
        _indice_acoes(acoes_publicadas, agora or datetime.now()), encoding="utf-8"
    )

    # páginas de ETF (classe própria — ver docs/ETFS.md), em duas passadas:
    # montar tudo primeiro para saber quais páginas existirão e o selo de cada
    # uma, e só então gerar — as posições linkam FII/ETF/ação com o selo do alvo
    from ..coleta import cda as coleta_cda
    from . import etf_html

    classificacoes = coleta_cda.carregar_classificacoes()
    etfs_montados = []
    for etf in armazenamento.etfs_listados(con):
        dados_etf = etf_html.montar_dados_etf(con, etf["ticker"], classificacoes)
        if dados_etf is None or not (dados_etf["cotacao"] or dados_etf["pl"]):
            continue  # sem preço nem carteira: página vazia não ajuda ninguém
        etfs_montados.append(dados_etf)
    selos_cruzados = {resumo.ticker: resumo.selo for resumo in publicados if resumo.selo}
    selos_cruzados.update(
        {dados["ticker"]: dados["selo"] for dados in acoes_publicadas if dados.get("selo")}
    )
    selos_cruzados.update(
        {dados["etf"]["ticker"]: dados["selo"] for dados in etfs_montados if dados.get("selo")}
    )
    publicados_cruzados = (
        tickers_no_site
        | {dados["etf"]["ticker"] for dados in etfs_montados}
        | {dados["ticker"] for dados in acoes_publicadas}
    )
    etfs_publicados = []
    for dados_etf in etfs_montados:
        ticker_etf = dados_etf["etf"]["ticker"]
        (destino / f"{ticker_etf}.html").write_text(
            etf_html.gerar(
                dados_etf,
                agora=agora,
                com_menu=True,
                leitura=todas_leituras.get(ticker_etf),
                publicados=publicados_cruzados,
                selos=selos_cruzados,
            ),
            encoding="utf-8",
        )
        etfs_publicados.append(dados_etf)
        item("etfs", len(etfs_publicados), len(etfs_publicados))
    (destino / "etfs.html").write_text(
        _indice_etfs(etfs_publicados, agora or datetime.now()), encoding="utf-8"
    )
    if etfs_publicados:
        (destino / "comparar-etfs.html").write_text(
            _pagina_comparar_etfs(etfs_publicados), encoding="utf-8"
        )
    progresso(f"etfs: {len(etfs_publicados)} páginas")

    # páginas de BANCO emissor (R3 Renda Fixa): só conglomerados com série IF.data
    from . import banco_html

    bancos_publicados = []
    for linha in con.execute("SELECT cod_inst FROM bancos ORDER BY cod_inst"):
        dados_banco = banco_html.montar_dados_banco(con, linha["cod_inst"])
        if dados_banco is None:
            continue
        (destino / f"{banco_html.slug(linha['cod_inst'])}.html").write_text(
            banco_html.gerar(dados_banco, agora=agora, com_menu=True), encoding="utf-8"
        )
        bancos_publicados.append(dados_banco)
    if bancos_publicados:
        (destino / "bancos.html").write_text(
            _indice_bancos(bancos_publicados, agora or datetime.now()), encoding="utf-8"
        )
        (destino / "comparar-bancos.html").write_text(
            _pagina_comparar_bancos(bancos_publicados), encoding="utf-8"
        )
    progresso(f"bancos: {len(bancos_publicados)} páginas")
    if acoes_publicadas:
        (destino / "comparar-acoes.html").write_text(
            _pagina_comparar_acoes(acoes_publicadas), encoding="utf-8"
        )
    progresso(f"ações: {len(acoes_publicadas)} páginas")

    (destino / "metodologia.html").write_text(
        _pagina_metodologia(agora or datetime.now()), encoding="utf-8"
    )
    # fonte display auto-hospedada (sem CDN, sem fetch externo) — um único
    # arquivo no destino, cacheado pelo navegador; @font-face aponta para ela
    _fonte = Path(__file__).parent / "assets" / "scout-display.ttf"
    if _fonte.exists() and not (destino / "scout-display.ttf").exists():
        (destino / "scout-display.ttf").write_bytes(_fonte.read_bytes())
    momento = agora or datetime.now()
    import json as _json

    (destino / "busca.json").write_text(
        _json.dumps(
            _ativos_busca(publicados, etfs_publicados, acoes_publicadas, bancos_publicados),
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    # tipo do FII (papel/tijolo/híbrido/FoF) derivado da carteira oficial (CVM)
    tipos_fii = armazenamento.tipos_fii(con)
    (destino / "fiis.html").write_text(
        _indice(publicados, base, momento, tipos_fii), encoding="utf-8"
    )
    (destino / "index.html").write_text(
        _home(publicados, etfs_publicados, momento, tipos_fii, acoes_publicadas, bancos_publicados), encoding="utf-8"
    )
    (destino / "comparar.html").write_text(
        _pagina_comparar(publicados), encoding="utf-8"
    )
    total_analytics = _injetar_analytics(destino, analytics)
    if total_analytics:
        progresso(f"analytics sem cookie (GoatCounter) em {total_analytics} páginas")
    total_reportar = _injetar_reportar(destino, reportar)
    if total_reportar:
        progresso(f"botão de reportar em {total_reportar} páginas")
    return {
        "paginas": len(publicados),
        "etfs": len(etfs_publicados),
        "acoes": len(acoes_publicadas),
        "destino": str(destino),
    }


def _injetar_reportar(destino: Path, url: str) -> int:
    """Injeta o botão flutuante de reportar antes de `</body>` em TODAS as
    páginas — um ponto só cobre home, listagens e páginas de ativo. Vazio
    quando não há URL do formulário (build local/testes ficam limpos)."""
    snippet = relatorio_html.botao_reportar_html(url)
    if not snippet:
        return 0
    total = 0
    for caminho in destino.glob("*.html"):
        conteudo = caminho.read_text(encoding="utf-8")
        if 'id="scout-reportar"' in conteudo or "</body>" not in conteudo:
            continue  # idempotente; página sem <body> (não deve acontecer) é pulada
        caminho.write_text(conteudo.replace("</body>", snippet + "\n</body>", 1), encoding="utf-8")
        total += 1
    return total


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


def _ativos_busca(
    fundos: list,
    etfs: list[dict],
    acoes: list[dict] | None = None,
    bancos: list[dict] | None = None,
) -> list[dict]:
    """Índice compacto da busca viva (home embutida + busca.json das páginas).

    Entradas sem ticker (bancos) trazem a URL explícita em `u`; o JS usa
    `a.u || a.t + '.html'` para montar o link."""
    from . import banco_html

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
    for dados in acoes or []:
        empresa = dados["empresa"]
        ativos.append(
            {
                "t": dados["ticker"],
                "n": (empresa["nome_pregao"] or empresa["nome"] or "")[:48],
                "c": "Ação",
                "s": dados["selo"].nivel if dados.get("selo") else "",
                "r": dados["selo"].rotulo if dados.get("selo") else "",
            }
        )
    for dados in bancos or []:
        banco = dados["banco"]
        ativos.append(
            {
                "t": "",
                "n": banco_html.nome_curto(banco["nome"])[:48],
                "c": "Banco",
                "s": dados["selo"].nivel if dados.get("selo") else "",
                "r": dados["selo"].rotulo if dados.get("selo") else "",
                "u": f"{banco_html.slug(banco['cod_inst'])}.html",
            }
        )
    return ativos


def _home(
    fundos: list,
    etfs: list[dict],
    agora: datetime,
    tipos_fii: dict | None = None,
    acoes: list[dict] | None = None,
    bancos: list[dict] | None = None,
) -> str:
    """Home multi-classe: busca ao vivo em TUDO que temos + resumo por classe."""
    import json as _json

    from .. import tipo_fii as _tipo

    tipos_fii = tipos_fii or {}
    acoes = acoes or []
    bancos = bancos or []
    n_bancos = len(bancos)
    ativos = _ativos_busca(fundos, etfs, acoes, bancos)
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
    # pills de SETOR das ações (mesmo padrão das classes de ETF): linkam a
    # acoes.html?setor=X, que pré-seleciona o filtro
    from .acao_html import _setor_curto

    setores_acoes: dict[str, int] = {}
    for dados in acoes:
        setor = _setor_curto(dados["empresa"])
        if setor and setor != "—":
            setores_acoes[setor] = setores_acoes.get(setor, 0) + 1
    pills_acoes = " ".join(
        f'<a class="pill" href="acoes.html?setor={_e(setor)}">{_e(setor)} <b>{total}</b></a>'
        for setor, total in sorted(setores_acoes.items(), key=lambda kv: -kv[1])
    )
    partes_busca = [f"{len(fundos)} FIIs", f"{len(etfs)} ETFs"]
    if acoes:
        partes_busca.append(f"{len(acoes)} ações")
    if bancos:
        partes_busca.append(f"{n_bancos} bancos")
    cobertura_busca = " e ".join(x for x in (", ".join(partes_busca[:-1]), partes_busca[-1]) if x)

    # chips de tipo do FII (papel/tijolo/híbrido/FoF), na ordem de relevância
    tipos_fii_contagem: dict[str, int] = {}
    for resumo in fundos:
        tipo = tipos_fii.get(resumo.cnpj)
        if tipo:
            tipos_fii_contagem[tipo] = tipos_fii_contagem.get(tipo, 0) + 1
    pills_fii = " ".join(
        f'<a class="pill" href="fiis.html?tipo={_e(tipo)}">{_e(tipo)} <b>{tipos_fii_contagem[tipo]}</b></a>'
        for tipo in _tipo.ORDEM
        if tipos_fii_contagem.get(tipo)
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
body {{ background:#0F1416; color:#EAEEF0; font-family:system-ui,sans-serif; line-height:1.5; }}
.pagina {{ max-width:1020px; margin:0 auto; padding:28px 20px 40px; }}
h1 {{ font-family:'Scout Display',system-ui,sans-serif; font-size:38px; font-weight:700; letter-spacing:-.02em; line-height:1.1; margin:14px 0 10px; }}
.meta {{ color:#9AA7B2; font-size:14px; }}
a {{ color:#8FCB9B; text-decoration:none; }} a:hover {{ color:#B9E2C1; }}
.busca-caixa {{ position:relative; margin:22px 0 8px; }}
input#busca {{ width:100%; background:#161D20; color:#EAEEF0; border:1px solid #33434A;
  border-radius:14px; padding:15px 18px; font-size:17px; }}
input#busca:focus {{ outline:2px solid #8FCB9B; outline-offset:1px; border-color:#8FCB9B; }}
#resultados {{ position:absolute; top:100%; left:0; right:0; z-index:30; background:#161D20;
  border:1px solid #263034; border-radius:12px; margin-top:6px; overflow:hidden;
  box-shadow:0 16px 44px rgba(0,0,0,.55); }}
#resultados a {{ display:flex; align-items:center; gap:10px; padding:10px 14px;
  color:#EAEEF0; text-decoration:none; border-bottom:1px solid #1B2225; }}
#resultados a:last-child {{ border-bottom:none; }}
#resultados a:hover, #resultados a.foco {{ background:#1E272B; }}
#resultados .tk {{ font-weight:800; min-width:74px; }}
#resultados .nm {{ color:#9AA7B2; font-size:13px; flex:1; overflow:hidden; white-space:nowrap; text-overflow:ellipsis; }}
#resultados .badge {{ font-size:10.5px; font-weight:700; letter-spacing:.05em; text-transform:uppercase;
  background:#1E272B; color:#8FCB9B; border:1px solid #263034; border-radius:99px; padding:2px 9px; white-space:nowrap; }}
#resultados .ponto {{ width:9px; height:9px; border-radius:50%; flex-shrink:0; }}
.blocos {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:16px; margin-top:24px; }}
.bloco {{ background:#161D20; border:1px solid #263034; border-radius:16px; padding:22px 24px; }}
.bloco h2 {{ font-family:'Scout Display',system-ui,sans-serif; font-size:20px; font-weight:700; margin-bottom:4px; }}
.bloco .num {{ font-family:'Scout Display',system-ui,sans-serif; font-size:40px; font-weight:700; letter-spacing:-.02em; color:#EAEEF0; font-variant-numeric:tabular-nums; }}
.bloco p {{ color:#9AA7B2; font-size:13.5px; margin:6px 0 14px; line-height:1.55; }}
.pill {{ display:inline-flex; align-items:center; background:#161D20; border:1px solid #263034; color:#9AA7B2;
  border-radius:99px; padding:5px 13px; font-size:12.5px; text-decoration:none; }}
.pill b {{ margin-left:5px; }}
.bloco .linha-acoes {{ display:flex; align-items:center; flex-wrap:wrap; gap:8px; }}
.bloco .chips {{ display:flex; flex-wrap:wrap; gap:6px; margin-top:10px; }}
.pill:hover {{ border-color:#8FCB9B; color:#8FCB9B; }}
.pill b {{ color:#EAEEF0; }}
.btn {{ display:inline-block; background:#8FCB9B; color:#0F1416; border-radius:9px; padding:9px 18px;
  font-size:13.5px; font-weight:700; text-decoration:none; }}
.btn:hover {{ background:#B9E2C1; color:#0F1416; }}
.rodape {{ color:#6B7681; font-size:12.5px; border-top:1px solid #1B2225; margin-top:30px; padding-top:16px; }}
#aviso-beta {{ position:fixed; inset:0; background:rgba(11,15,16,.78); z-index:50;
  display:flex; align-items:center; justify-content:center; padding:20px; }}
#aviso-beta[hidden] {{ display:none; }}
.beta-caixa {{ background:#161D20; border:1px solid #263034; border-radius:14px; padding:22px 24px;
  max-width:440px; font-size:14px; box-shadow:0 12px 40px rgba(0,0,0,.5); }}
.beta-caixa p {{ color:#9AA7B2; margin:10px 0 14px; }}
.beta-caixa button {{ background:#8FCB9B; color:#0F1416; border:none; border-radius:9px;
  padding:9px 22px; font-size:13.5px; font-weight:700; cursor:pointer; }}
{CSS_MENU}{_CSS_RK_MAIS}
{relatorio_html.CSS_MARCA}
</style>
</head>
<body>
<div id="aviso-beta" hidden>
  <div class="beta-caixa">
    <b>O Scout está em beta.</b>
    <p>Os dados vêm de fontes oficiais, mas o site é novo e pode conter falhas. Encontrou algo estranho?
    Reporte em <a href="https://github.com/Ruamms/scout/issues" target="_blank" rel="noopener">github.com/Ruamms/scout/issues</a>
    ou por e-mail: <a href="mailto:ruamms3@gmail.com">ruamms3@gmail.com</a>.</p>
    <button onclick="fecharBeta()">Entendi</button>
  </div>
</div>
<div class="pagina">
  {relatorio_html.marca_html()}
  {menu_html()}
  <h1>Exploramos os relatórios oficiais para você não se perder neles</h1>
  <div class="meta">Percorremos os dados públicos oficiais (CVM, B3, Banco Central), marcamos cada alerta
  com a conta e a fonte, e uma IA local vasculha os relatórios — fatos, não dicas. A decisão é sua.</div>
  <div class="meta" style="margin-top:6px">🎓 O Scout é um <b>projeto particular, de cunho educacional</b> —
  um estudo aberto de desenvolvimento de software sobre dados públicos do mercado. Não é um serviço de
  análise nem recomendação de investimento · <a href="metodologia.html">metodologia e aviso legal</a></div>

  <div class="busca-caixa">
    <input id="busca" type="search" autocomplete="off"
     placeholder="Digite um ticker ou nome… (ex.: MXRF11, BOVA, Daycoval)"
     oninput="buscar()" onkeydown="navegar(event)">
    <div id="resultados" hidden></div>
  </div>
  <div class="meta" style="font-size:12px">a busca cobre tudo o que já analisamos: {cobertura_busca}</div>

  <div class="blocos">
    <div class="bloco">
      <h2>Fundos Imobiliários</h2>
      <div class="num">{len(fundos)}</div>
      <p>Reconhecimento completo: red flags com evidência, parecer do auditor, imóveis com vacância,
      gestora, e a IA local vasculhando relatórios e comunicados.</p>
      <div class="linha-acoes"><a class="btn" href="fiis.html">ver todos os FIIs</a></div>
      <div class="linha-acoes" style="margin-top:8px"><a class="pill" href="fiis.html#rankings">rankings do dia</a>
      <a class="pill" href="comparar.html">comparar</a></div>
      <div class="chips">{pills_fii}</div>
    </div>
    <div class="bloco">
      <h2>ETFs</h2>
      <div class="num">{len(etfs)}</div>
      <p>Cada página traz as REGRAS do tipo (distribuição, tributação) que quase ninguém conta,
      a carteira oficial e o selo com alertas próprios da classe.</p>
      <div class="linha-acoes"><a class="btn" href="etfs.html">ver todos os ETFs</a></div>
      <div class="chips">{pills}</div>
    </div>
    {f'''<div class="bloco">
      <h2>Ações</h2>
      <div class="num">{len(acoes)}</div>
      <p>Balanço oficial (DFP/CVM), múltiplos por papel (P/L, P/VP, DY), ROE, EBITDA,
      proventos e red flags societárias — e as regras da classe explicadas para leigo.</p>
      <p style="color:#6B7681;font-size:12px;margin-top:-6px">todas as companhias listadas em
      bolsa na B3 — onde falta dado oficial, mostramos "—", nunca número inventado.</p>
      <div class="linha-acoes"><a class="btn" href="acoes.html">ver todas as ações</a></div>
      <div class="chips">{pills_acoes}</div>
    </div>''' if acoes else ""}
    {f'''<div class="bloco">
      <h2>Bancos (CDB)</h2>
      <div class="num">{n_bancos}</div>
      <p>O CDB da corretora é um empréstimo AO BANCO — aqui está a saúde de quem emite:
      Basileia, captações, lucro e red flags, com dados oficiais do Banco Central (IF.data).</p>
      <p style="color:#6B7681;font-size:12px;margin-top:-6px">o FGC cobre R$ 250 mil por CPF
      por CONGLOMERADO (não por corretora) — as regras explicadas em cada página.</p>
      <div class="linha-acoes"><a class="btn" href="bancos.html">ver todos os bancos</a></div>
    </div>''' if n_bancos else ""}
  </div>

  <div class="rodape">Não é recomendação de investimento. Fontes: dados abertos da CVM, B3 (COTAHIST
  e fundos listados) e Banco Central. Critérios públicos e auditáveis:
  <a href="https://github.com/Ruamms/scout">github.com/Ruamms/scout</a> ·
  atualizado em {agora.strftime("%d/%m/%Y %H:%M")}</div>
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
    caixa.innerHTML = '<a><span class="nm">nada encontrado — cobrimos FIIs, ETFs, ações e bancos emissores de CDB</span></a>';
    caixa.hidden = false;
    return;
  }}
  caixa.innerHTML = achados.map(a =>
    `<a href="${{a.u || (a.t + '.html')}}">` +
    (a.t ? `<span class="tk">${{a.t}}</span>` : '') +
    `<span class="nm">${{a.n}}</span>` +
    (a.s ? `<span class="ponto" style="background:${{CORES_SELO[a.s] || '#7C8894'}}" title="${{a.r}}"></span>` : '') +
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
{_JS_RK_MAIS}{JS_MENU}
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
    # abre com o TOP 10 por patrimônio (rankings logo abaixo); o resto sob demanda
    ordenados = sorted(etfs, key=lambda d: (d["pl"]["pl"] if d.get("pl") else 0), reverse=True)
    for posicao, dados in enumerate(ordenados):
        etf = dados["etf"]
        classe = dados["classe"] or "?"
        preco = f"R$ {formato.decimal(dados['preco_atual'])}" if dados["preco_atual"] else "—"
        variacao = (
            formato.percentual(dados["variacao_12m"], sinal=True)
            if dados["variacao_12m"] is not None
            else "—"
        )
        pl = formato.moeda_compacta(dados["pl"]["pl"]) if dados["pl"] else "—"
        taxa = (
            f'{formato.percentual(dados["taxa_adm"]["taxa_adm_aa"])} a.a.'
            if dados.get("taxa_adm")
            else "—"
        )
        selo_html = "—"
        if dados.get("selo"):
            cor = _COR_SELO.get(dados["selo"].nivel, "#7C8894")
            motivos = "; ".join(flag.titulo for flag in dados["flags"].flags) or dados["selo"].descricao
            selo_html = (
                f'<span class="selo-dot" style="color:{cor}" title="{_e(motivos)}"><span class="pt" style="background:{cor}"></span>'
                f"{_e(dados['selo'].rotulo)}</span>"
            )
        from .etf_html import _trunca

        busca = f"{etf['ticker']} {etf['denominacao'] or ''} {classe}".lower().replace('"', "")
        oculta = ' class="etf-extra" hidden' if posicao >= 10 else ""
        linhas.append(
            f'<tr data-busca="{busca}" data-classe="{_e(classe)}"{oculta}>'
            f'<td><a href="{etf["ticker"]}.html">{etf["ticker"]}</a></td>'
            f'<td title="{_e(etf["denominacao"] or "")}">{_e(_trunca(etf["denominacao"] or "", 48))}</td>'
            f"<td>{_e(classe)}</td><td>{preco}</td><td>{variacao}</td><td>{pl}</td>"
            f"<td>{taxa}</td>"
            f'<td class="col-selo">{selo_html}</td></tr>'
        )

    def _rk_etf(titulo, chave, rotulo, reverso=True):
        cand = [d for d in etfs if chave(d) is not None]
        cand.sort(key=chave, reverse=reverso)
        itens = "".join(
            f'<li{_rk_oculto(i)}><span class="pos">{i}</span>'
            f'<a href="{d["etf"]["ticker"]}.html">{d["etf"]["ticker"]}</a>'
            f'<span class="val">{rotulo(d)}</span></li>'
            for i, d in enumerate(cand[:20], 1)
        )
        return (
            f'<div class="bloco"><h3>{titulo}</h3><ol>{itens or "<li>—</li>"}</ol>'
            f"{_rk_botao(min(len(cand), 20))}</div>"
        )

    rankings_etf = (
        _rk_etf(
            "Maior retorno 12 meses",
            lambda d: d["variacao_12m"],
            lambda d: formato.percentual(d["variacao_12m"], sinal=True),
        )
        + _rk_etf(
            "Menor taxa de administração",
            lambda d: d["taxa_adm"]["taxa_adm_aa"] if d.get("taxa_adm") else None,
            lambda d: f'{formato.percentual(d["taxa_adm"]["taxa_adm_aa"])} a.a.',
            reverso=False,
        )
        + _rk_etf(
            "Maiores patrimônios",
            lambda d: d["pl"]["pl"] if d.get("pl") else None,
            lambda d: formato.moeda_compacta(d["pl"]["pl"]),
        )
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
body {{ background:#0F1416; color:#EAEEF0; font-family:system-ui,sans-serif; line-height:1.5; }}
.pagina {{ max-width:1020px; margin:0 auto; padding:28px 20px 40px; }}
h1 {{ font-family:'Scout Display',system-ui,sans-serif; font-size:30px; font-weight:700; letter-spacing:-.02em; margin:8px 0 4px; }}
.meta {{ color:#9AA7B2; font-size:13px; margin-bottom:12px; }}
a {{ color:#8FCB9B; }}
input#busca {{ width:100%; background:#161D20; color:#EAEEF0; border:1px solid #263034;
  border-radius:10px; padding:11px 15px; font-size:15px; margin:8px 0 10px; }}
.filtros {{ display:flex; gap:8px; flex-wrap:wrap; margin-bottom:12px; }}
.filtro {{ background:#1B2225; color:#9AA7B2; border:1px solid #263034; border-radius:99px;
  padding:4px 14px; font-size:12.5px; cursor:pointer; }}
.filtro.ativo {{ background:#8FCB9B; color:#0F1416; border-color:#8FCB9B; font-weight:700; }}
.btn-todos {{ display:block; margin:12px auto 0; background:#1B2225; border:1px solid #263034;
  color:#8FCB9B; padding:8px 22px; border-radius:8px; font-size:13.5px; font-weight:600; cursor:pointer; }}
.btn-todos:hover {{ border-color:#8FCB9B; }}
table {{ width:100%; border-collapse:collapse; font-size:13.5px; font-variant-numeric:tabular-nums; }}
th {{ color:#9AA7B2; font-size:11.5px; text-transform:uppercase; letter-spacing:.05em;
  text-align:left; padding:8px 10px;
  position:sticky; top:0; z-index:2; background:#0F1416;
  box-shadow:inset 0 -1px 0 #263034; }}
td {{ padding:7px 10px; border-bottom:1px solid #1B2225; }}
td:nth-child(n+4), th:nth-child(n+4) {{ text-align:right; }}
.rk-titulo {{ font-family:'Scout Display',system-ui,sans-serif; font-size:22px; font-weight:700; letter-spacing:-.01em; margin:34px 0 4px; }}
.blocos {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:14px; margin-top:8px; }}
.bloco {{ background:#161D20; border:1px solid #263034; border-radius:14px; padding:16px 18px; }}
.bloco h3 {{ font-size:11px; font-weight:700; letter-spacing:.05em; text-transform:uppercase; color:#9AA7B2; margin:0 0 12px; }}
.bloco ol {{ margin:0; padding:0; list-style:none; display:flex; flex-direction:column; gap:9px; }}
.bloco li {{ display:flex; align-items:baseline; gap:10px; }}
.bloco .pos {{ color:#6B7681; font-size:12px; width:16px; }}
.bloco a {{ font-weight:700; min-width:66px; }}
.bloco .val {{ margin-left:auto; color:#EAEEF0; font-weight:600; font-variant-numeric:tabular-nums; }}
tbody tr:hover td {{ background:#161D20; }}
.selo {{ display:inline-block; padding:2px 10px; border-radius:999px; font-weight:700;
  font-size:11px; color:#0F1416; white-space:nowrap; }}
.rodape {{ color:#9AA7B2; font-size:12.5px; border-top:1px solid #1B2225; margin-top:26px; padding-top:12px; }}
{CSS_MENU}{_CSS_RK_MAIS}
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
    <thead><tr><th>ticker</th><th>fundo</th><th>classe</th><th>preço (D-1)</th><th>12 meses</th><th>PL</th><th>taxa</th><th class="col-selo">selo</th></tr></thead>
    <tbody>{"".join(linhas)}</tbody>
  </table>
  <button id="ver-todos" class="btn-todos" onclick="mostrarTodos()"
   {"hidden" if len(etfs) <= 10 else ""}>Mostrar todos os {len(etfs)} ETFs
   (acima: os {min(len(etfs), 10)} maiores por patrimônio)</button>
  <h2 class="rk-titulo">Rankings do dia</h2>
  <div class="meta" style="margin:0 0 14px">fatos ordenados com critério explícito — não recomendação · retorno passado não garante futuro</div>
  <div class="blocos">{rankings_etf}</div>
  <div class="rodape">Não é recomendação de investimento. Fontes: B3 e CVM — critérios públicos:
  <a href="https://github.com/Ruamms/scout">github.com/Ruamms/scout</a></div>
</div>
<script>
let classeAtiva = '';
let todosVisiveis = false;
function filtrar() {{
  const termo = document.getElementById('busca').value.trim().toLowerCase();
  const filtrando = termo !== '' || classeAtiva !== '';
  document.querySelectorAll('#etfs tbody tr').forEach(tr => {{
    const casaTermo = termo === '' || tr.dataset.busca.includes(termo);
    const casaClasse = classeAtiva === '' || tr.dataset.classe === classeAtiva;
    const recolhida = !filtrando && !todosVisiveis && tr.classList.contains('etf-extra');
    tr.hidden = !(casaTermo && casaClasse) || recolhida;
  }});
  const botao = document.getElementById('ver-todos');
  if (botao) botao.hidden = todosVisiveis || filtrando || !document.querySelector('.etf-extra');
}}
function mostrarTodos() {{
  todosVisiveis = true;
  filtrar();
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
{_JS_RK_MAIS}{JS_MENU}
</script>
</body>
</html>
"""


def _indice_acoes(acoes: list[dict], agora) -> str:
    """Listagem das ações publicadas (v1 = IBrX-100) — filtro por setor + busca."""
    from .. import formato
    from .acao_html import _setor_curto, _trunca

    setores = sorted({_setor_curto(d["empresa"]) for d in acoes})
    botoes = "".join(
        f'<button class="filtro" onclick="filtraClasse(this, \'{_e(setor)}\')">{_e(setor)}</button>'
        for setor in setores
    )

    def _mult(d):
        return d["multiplos"].get(d["ticker"], {})

    linhas = []
    # abre com o TOP 10 por liquidez (rankings logo abaixo); o resto sob demanda
    ordenados = sorted(acoes, key=lambda d: d.get("liquidez") or 0, reverse=True)
    for posicao, dados in enumerate(ordenados):
        empresa = dados["empresa"]
        setor = _setor_curto(empresa)
        m = _mult(dados)
        fmt = lambda v, f=formato.decimal: f(v) if v is not None else "—"  # noqa: E731
        preco = f"R$ {formato.decimal(dados['preco_atual'])}" if dados["preco_atual"] else "—"
        variacao = (
            formato.percentual(dados["variacao_12m"], sinal=True)
            if dados["variacao_12m"] is not None
            else "—"
        )
        nome = empresa["nome_pregao"] or empresa["nome"] or ""
        selo_html = "—"
        if dados.get("selo"):
            cor = _COR_SELO.get(dados["selo"].nivel, "#7C8894")
            motivos = "; ".join(f.titulo for f in dados["flags"].flags) or dados["selo"].descricao
            selo_html = (
                f'<span class="selo-dot" style="color:{cor}" title="{_e(motivos)}">'
                f'<span class="pt" style="background:{cor}"></span>{_e(dados["selo"].rotulo)}</span>'
            )
        busca = f"{dados['ticker']} {nome} {setor}".lower().replace('"', "")
        oculta = ' class="acao-extra" hidden' if posicao >= 10 else ""
        linhas.append(
            f'<tr data-busca="{busca}" data-classe="{_e(setor)}"{oculta}>'
            f'<td><a href="{dados["ticker"]}.html">{dados["ticker"]}</a></td>'
            f'<td title="{_e(empresa["nome"] or "")}">{_e(_trunca(nome, 34))}</td>'
            f"<td>{_e(_trunca(setor, 26))}</td><td>{preco}</td><td>{variacao}</td>"
            f"<td>{fmt(m.get('pl'))}</td><td>{fmt(m.get('pvp'))}</td>"
            f"<td>{fmt(m.get('dy'), formato.percentual)}</td>"
            f'<td class="col-selo">{selo_html}</td></tr>'
        )

    def _rk(titulo, chave, rotulo, reverso=True):
        cand = [d for d in acoes if chave(d) is not None]
        cand.sort(key=chave, reverse=reverso)
        itens = "".join(
            f'<li{_rk_oculto(i)}><span class="pos">{i}</span>'
            f'<a href="{d["ticker"]}.html">{d["ticker"]}</a>'
            f'<span class="val">{rotulo(d)}</span></li>'
            for i, d in enumerate(cand[:20], 1)
        )
        return (
            f'<div class="bloco"><h3>{titulo}</h3><ol>{itens or "<li>—</li>"}</ol>'
            f"{_rk_botao(min(len(cand), 20))}</div>"
        )

    rankings = (
        _rk(
            "Maior dividend yield 12m",
            lambda d: _mult(d).get("dy"),
            lambda d: formato.percentual(_mult(d)["dy"]),
        )
        + _rk(
            "Menor P/L (com lucro)",
            lambda d: _mult(d).get("pl"),
            lambda d: formato.decimal(_mult(d)["pl"]),
            reverso=False,
        )
        + _rk(
            "Maior ROE",
            lambda d: d["indicadores"].get("roe"),
            lambda d: formato.percentual(d["indicadores"]["roe"]),
        )
    )
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ações — Scout</title>
{relatorio_html.TAG_FAVICON}
<style>
:root {{ color-scheme: dark; }}
* {{ box-sizing:border-box; margin:0; }}
body {{ background:#0F1416; color:#EAEEF0; font-family:system-ui,sans-serif; line-height:1.5; }}
.pagina {{ max-width:1020px; margin:0 auto; padding:28px 20px 40px; }}
h1 {{ font-family:'Scout Display',system-ui,sans-serif; font-size:30px; font-weight:700; letter-spacing:-.02em; margin:8px 0 4px; }}
.meta {{ color:#9AA7B2; font-size:13px; margin-bottom:12px; }}
a {{ color:#8FCB9B; }}
input#busca {{ width:100%; background:#161D20; color:#EAEEF0; border:1px solid #263034;
  border-radius:10px; padding:11px 15px; font-size:15px; margin:8px 0 10px; }}
.filtros {{ display:flex; gap:8px; flex-wrap:wrap; margin-bottom:12px; }}
.filtro {{ background:#1B2225; color:#9AA7B2; border:1px solid #263034; border-radius:99px;
  padding:4px 14px; font-size:12.5px; cursor:pointer; }}
.filtro.ativo {{ background:#8FCB9B; color:#0F1416; border-color:#8FCB9B; font-weight:700; }}
.btn-todos {{ display:block; margin:12px auto 0; background:#1B2225; border:1px solid #263034;
  color:#8FCB9B; padding:8px 22px; border-radius:8px; font-size:13.5px; font-weight:600; cursor:pointer; }}
.btn-todos:hover {{ border-color:#8FCB9B; }}
table {{ width:100%; border-collapse:collapse; font-size:13.5px; font-variant-numeric:tabular-nums; }}
th {{ color:#9AA7B2; font-size:11.5px; text-transform:uppercase; letter-spacing:.05em;
  text-align:left; padding:8px 10px;
  position:sticky; top:0; z-index:2; background:#0F1416;
  box-shadow:inset 0 -1px 0 #263034; }}
td {{ padding:7px 10px; border-bottom:1px solid #1B2225; }}
td:nth-child(n+4), th:nth-child(n+4) {{ text-align:right; }}
.rk-titulo {{ font-family:'Scout Display',system-ui,sans-serif; font-size:22px; font-weight:700; letter-spacing:-.01em; margin:34px 0 4px; }}
.blocos {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:14px; margin-top:8px; }}
.bloco {{ background:#161D20; border:1px solid #263034; border-radius:14px; padding:16px 18px; }}
.bloco h3 {{ font-size:11px; font-weight:700; letter-spacing:.05em; text-transform:uppercase; color:#9AA7B2; margin:0 0 12px; }}
.bloco ol {{ margin:0; padding:0; list-style:none; display:flex; flex-direction:column; gap:9px; }}
.bloco li {{ display:flex; align-items:baseline; gap:10px; }}
.bloco .pos {{ color:#6B7681; font-size:12px; width:16px; }}
.bloco a {{ font-weight:700; min-width:66px; }}
.bloco .val {{ margin-left:auto; color:#EAEEF0; font-weight:600; font-variant-numeric:tabular-nums; }}
tbody tr:hover td {{ background:#161D20; }}
.rodape {{ color:#9AA7B2; font-size:12.5px; border-top:1px solid #1B2225; margin-top:26px; padding-top:12px; }}
{CSS_MENU}{_CSS_RK_MAIS}
{relatorio_html.CSS_MARCA}
</style>
</head>
<body>
<div class="pagina">
  {relatorio_html.marca_html("index.html")}
  {menu_html()}
  <h1>Ações</h1>
  <div class="meta">{len(acoes)} papéis de <b>todas as companhias listadas em bolsa na B3</b> · balanço
  (DFP/CVM), múltiplos e proventos com fonte oficial · <a href="comparar-acoes.html">comparar ações</a> ·
  <a href="index.html">início</a> · atualizado em {agora.strftime("%d/%m/%Y %H:%M")}</div>
  <div class="meta" style="background:#161D20;border:1px solid #263034;border-radius:10px;padding:10px 14px;margin-bottom:4px">
  Cobrimos <b>todas as companhias listadas em bolsa na B3</b> (BDRs ficam de fora por enquanto).
  Small caps têm mais buraco de dado — onde falta, mostramos "—" ou "não avaliada",
  <b>nunca número inventado</b>. Sentiu falta de uma empresa ou viu dado estranho?
  <a href="https://github.com/Ruamms/scout/issues">avise aqui</a>.</div>
  <input id="busca" type="search" placeholder="Busque por ticker, empresa ou setor… (ex.: PETR, bancos, energia)"
   oninput="filtrar()">
  <div class="filtros"><button class="filtro ativo" onclick="filtraClasse(this, '')">Todos</button>{botoes}</div>
  <table id="acoes">
    <thead><tr><th>papel</th><th>empresa</th><th>setor</th><th>preço (D-1)</th><th>12 meses</th><th>P/L</th><th>P/VP</th><th>DY 12m</th><th class="col-selo">selo</th></tr></thead>
    <tbody>{"".join(linhas)}</tbody>
  </table>
  <button id="ver-todos" class="btn-todos" onclick="mostrarTodos()"
   {"hidden" if len(acoes) <= 10 else ""}>Mostrar todos os {len(acoes)} papéis
   (acima: os {min(len(acoes), 10)} mais negociados por dia)</button>
  <h2 class="rk-titulo">Rankings do dia</h2>
  <div class="meta" style="margin:0 0 14px">fatos ordenados com critério explícito — não recomendação · retorno passado não garante futuro</div>
  <div class="blocos">{rankings}</div>
  <div class="rodape">Não é recomendação de investimento. Fontes: B3 e CVM — critérios públicos:
  <a href="https://github.com/Ruamms/scout">github.com/Ruamms/scout</a></div>
</div>
<script>
let classeAtiva = '';
let todosVisiveis = false;
function filtrar() {{
  const termo = document.getElementById('busca').value.trim().toLowerCase();
  const filtrando = termo !== '' || classeAtiva !== '';
  document.querySelectorAll('#acoes tbody tr').forEach(tr => {{
    const casaTermo = termo === '' || tr.dataset.busca.includes(termo);
    const casaClasse = classeAtiva === '' || tr.dataset.classe === classeAtiva;
    const recolhida = !filtrando && !todosVisiveis && tr.classList.contains('acao-extra');
    tr.hidden = !(casaTermo && casaClasse) || recolhida;
  }});
  const botao = document.getElementById('ver-todos');
  if (botao) botao.hidden = todosVisiveis || filtrando || !document.querySelector('.acao-extra');
}}
function mostrarTodos() {{
  todosVisiveis = true;
  filtrar();
}}
function filtraClasse(botao, classe) {{
  classeAtiva = classe;
  document.querySelectorAll('.filtro').forEach(b => b.classList.toggle('ativo', b === botao));
  filtrar();
}}
// ?setor=X na URL pré-seleciona o filtro
const classeUrl = new URLSearchParams(location.search).get('setor');
if (classeUrl) {{
  const botao = Array.from(document.querySelectorAll('.filtro')).find(b => b.textContent === classeUrl);
  if (botao) filtraClasse(botao, classeUrl);
}}
{_JS_RK_MAIS}{JS_MENU}
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
            "cor": _COR_SELO.get(resumo.selo.nivel, "#7C8894"),
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
body {{ background:#0F1416; color:#EAEEF0; font-family:system-ui,sans-serif; line-height:1.5; }}
.pagina {{ max-width:960px; margin:0 auto; padding:28px 20px 40px; }}
h1 {{ font-family:'Scout Display',system-ui,sans-serif; font-size:30px; font-weight:700; letter-spacing:-.02em; margin:8px 0 4px; }}
.meta {{ color:#9AA7B2; font-size:13px; margin-bottom:16px; }}
a {{ color:#8FCB9B; }}
select {{ background:#161D20; color:#EAEEF0; border:1px solid #263034; border-radius:8px;
  padding:9px 12px; font-size:15px; min-width:130px; }}
.seletores {{ display:flex; gap:10px; flex-wrap:wrap; margin-bottom:18px; }}
table {{ width:100%; border-collapse:collapse; font-size:14px; font-variant-numeric:tabular-nums; }}
th, td {{ padding:9px 10px; border-bottom:1px solid #1B2225; text-align:left; }}
th {{ color:#9AA7B2; font-size:11.5px; text-transform:uppercase; letter-spacing:.05em; }}
td:first-child {{ color:#9AA7B2; font-size:12.5px; text-transform:uppercase; letter-spacing:.04em; white-space:nowrap; }}
tbody tr:hover td {{ background:#161D20; }}
.selo {{ display:inline-block; padding:2px 10px; border-radius:999px; font-weight:700;
  font-size:11px; color:#0F1416; white-space:nowrap; }}
.rodape {{ color:#9AA7B2; font-size:12.5px; border-top:1px solid #1B2225; margin-top:26px; padding-top:12px; }}
{CSS_MENU}{_CSS_RK_MAIS}
{relatorio_html.CSS_MARCA}
</style>
</head>
<body>
<div class="pagina">
  {relatorio_html.marca_html("index.html")}
  {menu_html()}
  <h1>Comparar FIIs</h1>
  <div class="meta">os mesmos fatos, lado a lado — sem "vencedor": a decisão é sua ·
  <a href="index.html">voltar para todos os fundos</a></div>
  <div class="seletores">
    <select id="f1" onchange="renderiza()"><option value="">fundo 1…</option>{opcoes}</select>
    <select id="f2" onchange="renderiza()"><option value="">fundo 2…</option>{opcoes}</select>
    <select id="f3" onchange="renderiza()"><option value="">fundo 3 (opcional)…</option>{opcoes}</select>
  </div>
  <div id="tabela"></div>
  <div class="rodape">Comparação factual com dados públicos oficiais — não é recomendação de investimento.
  Critérios e código: <a href="https://github.com/Ruamms/scout">github.com/Ruamms/scout</a></div>
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
{_JS_RK_MAIS}{JS_MENU}
</script>
</body>
</html>
"""


def _indice_bancos(bancos: list[dict], agora) -> str:
    """Listagem dos bancos emissores (R3 Renda Fixa) — top 10 por captações,
    busca, selo; rankings de fatos logo abaixo."""
    from .. import formato
    from .banco_html import _rotulo_tri, nome_curto, slug

    ordenados = sorted(
        bancos, key=lambda d: d["atual"].get("captacoes") or 0, reverse=True
    )
    linhas = []
    for posicao, dados in enumerate(ordenados):
        banco, atual = dados["banco"], dados["atual"]
        nome = nome_curto(banco["nome"])
        selo_html = "—"
        if dados.get("selo"):
            cor = _COR_SELO.get(dados["selo"].nivel, "#7C8894")
            motivos = "; ".join(f.titulo for f in dados["flags"].flags) or dados["selo"].descricao
            selo_html = (
                f'<span class="selo-dot" style="color:{cor}" title="{_e(motivos)}">'
                f'<span class="pt" style="background:{cor}"></span>{_e(dados["selo"].rotulo)}</span>'
            )
        fmt = lambda v: formato.moeda_compacta(v) if v else "—"  # noqa: E731
        basileia = formato.percentual(atual["basileia"]) if atual.get("basileia") is not None else "—"
        busca = f"{nome} {banco['tcb'] or ''}".lower().replace('"', "")
        oculta = ' class="banco-extra" hidden' if posicao >= 10 else ""
        linhas.append(
            f'<tr data-busca="{busca}"{oculta}>'
            f'<td><a href="{slug(banco["cod_inst"])}.html">{_e(nome[:38])}</a></td>'
            f"<td>{basileia}</td><td>{fmt(atual.get('captacoes'))}</td>"
            f"<td>{fmt(atual.get('carteira'))}</td><td>{fmt(atual.get('lucro'))}</td>"
            f'<td class="col-selo">{selo_html}</td></tr>'
        )

    def _rk(titulo, chave, rotulo, reverso=True, minimo_capt=1e9):
        cand = [d for d in bancos if chave(d) is not None and (d["atual"].get("captacoes") or 0) > minimo_capt]
        cand.sort(key=chave, reverse=reverso)
        itens = "".join(
            f'<li{_rk_oculto(i)}><span class="pos">{i}</span>'
            f'<a href="{slug(d["banco"]["cod_inst"])}.html">{_e(nome_curto(d["banco"]["nome"])[:22])}</a>'
            f'<span class="val">{rotulo(d)}</span></li>'
            for i, d in enumerate(cand[:20], 1)
        )
        return (
            f'<div class="bloco"><h3>{titulo}</h3><ol>{itens or "<li>—</li>"}</ol>'
            f"{_rk_botao(min(len(cand), 20))}</div>"
        )

    rankings = (
        _rk("Maior Basileia (captações > R$ 1 bi)",
            lambda d: d["atual"].get("basileia"),
            lambda d: formato.percentual(d["atual"]["basileia"]))
        + _rk("Maiores captações",
              lambda d: d["atual"].get("captacoes"),
              lambda d: formato.moeda_compacta(d["atual"]["captacoes"]))
        + _rk("Menor Basileia (captações > R$ 1 bi)",
              lambda d: d["atual"].get("basileia"),
              lambda d: formato.percentual(d["atual"]["basileia"]), reverso=False)
    )
    trimestre = _rotulo_tri(ordenados[0]["atual"]["anomes"]) if ordenados else "—"
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bancos emissores — Scout</title>
{relatorio_html.TAG_FAVICON}
<style>
:root {{ color-scheme: dark; }}
* {{ box-sizing:border-box; margin:0; }}
body {{ background:#0F1416; color:#EAEEF0; font-family:system-ui,sans-serif; line-height:1.5; }}
.pagina {{ max-width:1020px; margin:0 auto; padding:28px 20px 40px; }}
h1 {{ font-family:'Scout Display',system-ui,sans-serif; font-size:30px; font-weight:700; letter-spacing:-.02em; margin:8px 0 4px; }}
.meta {{ color:#9AA7B2; font-size:13px; margin-bottom:12px; }}
a {{ color:#8FCB9B; }}
input#busca {{ width:100%; background:#161D20; color:#EAEEF0; border:1px solid #263034;
  border-radius:10px; padding:11px 15px; font-size:15px; margin:8px 0 10px; }}
.btn-todos {{ display:block; margin:12px auto 0; background:#1B2225; border:1px solid #263034;
  color:#8FCB9B; padding:8px 22px; border-radius:8px; font-size:13.5px; font-weight:600; cursor:pointer; }}
.btn-todos:hover {{ border-color:#8FCB9B; }}
table {{ width:100%; border-collapse:collapse; font-size:13.5px; font-variant-numeric:tabular-nums; }}
th {{ color:#9AA7B2; font-size:11.5px; text-transform:uppercase; letter-spacing:.05em;
  text-align:left; padding:8px 10px; position:sticky; top:0; z-index:2; background:#0F1416;
  box-shadow:inset 0 -1px 0 #263034; }}
td {{ padding:7px 10px; border-bottom:1px solid #1B2225; }}
td:not(:first-child), th:not(:first-child) {{ text-align:right; }}
.rk-titulo {{ font-family:'Scout Display',system-ui,sans-serif; font-size:22px; font-weight:700; letter-spacing:-.01em; margin:34px 0 4px; }}
.blocos {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:14px; margin-top:8px; }}
.bloco {{ background:#161D20; border:1px solid #263034; border-radius:14px; padding:16px 18px; }}
.bloco h3 {{ font-size:11px; font-weight:700; letter-spacing:.05em; text-transform:uppercase; color:#9AA7B2; margin:0 0 12px; }}
.bloco ol {{ margin:0; padding:0; list-style:none; display:flex; flex-direction:column; gap:9px; }}
.bloco li {{ display:flex; align-items:baseline; gap:10px; }}
.bloco .pos {{ color:#6B7681; font-size:12px; width:16px; }}
.bloco a {{ font-weight:700; }}
.bloco .val {{ margin-left:auto; color:#EAEEF0; font-weight:600; font-variant-numeric:tabular-nums; }}
tbody tr:hover td {{ background:#161D20; }}
.rodape {{ color:#9AA7B2; font-size:12.5px; border-top:1px solid #1B2225; margin-top:26px; padding-top:12px; }}
{CSS_MENU}{_CSS_RK_MAIS}
{relatorio_html.CSS_MARCA}
</style>
</head>
<body>
<div class="pagina">
  {relatorio_html.marca_html("index.html")}
  {menu_html()}
  <h1>Bancos emissores de CDB</h1>
  <div class="meta">{len(bancos)} conglomerados com dados no IF.data (BCB) até <b>{trimestre}</b> ·
  Basileia, captações e red flags de quem emite o CDB/LCI/LCA que a corretora te oferece ·
  <a href="index.html">início</a> · atualizado em {agora.strftime("%d/%m/%Y %H:%M")}</div>
  <div class="meta" style="background:#161D20;border:1px solid #263034;border-radius:10px;padding:10px 14px;margin-bottom:4px">
  CDB não tem página própria — <b>o risco é o banco emissor</b>. O FGC cobre até R$ 250 mil por CPF
  <b>por conglomerado</b> (não por corretora), e a saúde de quem emite está toda aqui, com fonte oficial.
  Sem comparação de taxas: taxa de prateleira é dado comercial — fato sobre o emissor, nunca "vale a pena".</div>
  <input id="busca" type="search" placeholder="Busque pelo nome do banco… (ex.: Inter, Daycoval, C6)"
   oninput="filtrar()">
  <table id="bancos">
    <thead><tr><th>banco</th><th>Basileia</th><th>captações</th><th>carteira</th><th>lucro no ano</th><th class="col-selo">selo</th></tr></thead>
    <tbody>{"".join(linhas)}</tbody>
  </table>
  <button id="ver-todos" class="btn-todos" onclick="mostrarTodos()"
   {"hidden" if len(bancos) <= 10 else ""}>Mostrar todos os {len(bancos)} bancos
   (acima: os {min(len(bancos), 10)} maiores por captações)</button>
  <h2 class="rk-titulo">Rankings do dia</h2>
  <div class="meta" style="margin:0 0 14px">fatos ordenados com critério explícito — não recomendação ·
  Basileia alta não é "seguro" nem baixa é "vai quebrar": é o colchão de capital, leia a página do banco</div>
  <div class="blocos">{rankings}</div>
  <div class="rodape">Não é recomendação de investimento. Fonte: IF.data (Banco Central) — critérios públicos:
  <a href="https://github.com/Ruamms/scout">github.com/Ruamms/scout</a></div>
</div>
<script>
let todosVisiveis = false;
function filtrar() {{
  const termo = document.getElementById('busca').value.trim().toLowerCase();
  document.querySelectorAll('#bancos tbody tr').forEach(tr => {{
    const casa = termo === '' || tr.dataset.busca.includes(termo);
    const recolhida = termo === '' && !todosVisiveis && tr.classList.contains('banco-extra');
    tr.hidden = !casa || recolhida;
  }});
  const botao = document.getElementById('ver-todos');
  if (botao) botao.hidden = todosVisiveis || termo !== '' || !document.querySelector('.banco-extra');
}}
function mostrarTodos() {{
  todosVisiveis = true;
  filtrar();
}}
{_JS_RK_MAIS}{JS_MENU}
</script>
</body>
</html>
"""


def _pagina_comparar_acoes(acoes: list[dict]) -> str:
    """Comparador de AÇÕES lado a lado (fecha o A6): os mesmos fatos por papel,
    sem 'vencedor'. Quando os setores diferem, um aviso factual lembra que
    múltiplos não se comparam entre setores (P/L de banco ≠ P/L de varejo)."""
    import json as _json

    from .. import formato
    from .acao_html import _setor_curto

    def _ou_traco(valor, formatador):
        return formatador(valor) if valor is not None else "—"

    dados = {}
    for d in sorted(acoes, key=lambda x: x["ticker"]):
        empresa = d["empresa"]
        m = d["multiplos"].get(d["ticker"], {})
        ind = d["indicadores"]
        ultimo = d["balancos"][-1] if d["balancos"] else None
        motivos = [f.titulo for f in d["flags"].flags] if d.get("flags") else []
        dados[d["ticker"]] = {
            "nome": (empresa["nome_pregao"] or empresa["nome"] or "")[:60],
            "setor": _setor_curto(empresa),
            "selo": d["selo"].rotulo if d.get("selo") else "—",
            "cor": _COR_SELO.get(d["selo"].nivel, "#7C8894") if d.get("selo") else "#7C8894",
            "motivos": motivos,
            "cotacao": _ou_traco(d["preco_atual"], lambda v: f"R$ {formato.decimal(v)}"),
            "pl": _ou_traco(m.get("pl"), formato.decimal),
            "pvp": _ou_traco(m.get("pvp"), formato.decimal),
            "dy": _ou_traco(m.get("dy"), formato.percentual),
            "roe": _ou_traco(ind.get("roe"), formato.percentual),
            "margem": _ou_traco(ind.get("margem_liquida"), formato.percentual),
            "ebitda": _ou_traco(ind.get("ebitda"), formato.moeda_compacta),
            "divida_pl": _ou_traco(ind.get("divida_liquida_pl"), lambda v: f"{formato.decimal(v)}×"),
            "lucro": _ou_traco(ultimo["lucro_liquido"] if ultimo else None, formato.moeda_compacta),
            "receita": _ou_traco(ultimo["receita"] if ultimo else None, formato.moeda_compacta),
            "ano": ultimo["ano"] if ultimo else "—",
        }
    json_dados = _json.dumps(dados, ensure_ascii=False).replace("</", "<\\/")
    opcoes = "".join(
        f'<option value="{t}">{t} — {_e(v["nome"][:32])}</option>' for t, v in dados.items()
    )
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Comparar ações — Scout</title>
{relatorio_html.TAG_FAVICON}
<style>
:root {{ color-scheme: dark; }}
* {{ box-sizing:border-box; margin:0; }}
body {{ background:#0F1416; color:#EAEEF0; font-family:system-ui,sans-serif; line-height:1.5; }}
.pagina {{ max-width:960px; margin:0 auto; padding:28px 20px 40px; }}
h1 {{ font-family:'Scout Display',system-ui,sans-serif; font-size:30px; font-weight:700; letter-spacing:-.02em; margin:8px 0 4px; }}
.meta {{ color:#9AA7B2; font-size:13px; margin-bottom:16px; }}
a {{ color:#8FCB9B; }}
select {{ background:#161D20; color:#EAEEF0; border:1px solid #263034; border-radius:8px;
  padding:9px 12px; font-size:14px; min-width:180px; max-width:280px; }}
.seletores {{ display:flex; gap:10px; flex-wrap:wrap; margin-bottom:14px; }}
#aviso-setor {{ background:#2a2320; border:1px solid #6b5a2a; color:#e8d9a8; padding:9px 12px;
  border-radius:8px; font-size:13px; margin-bottom:14px; }}
table {{ width:100%; border-collapse:collapse; font-size:14px; font-variant-numeric:tabular-nums; }}
th, td {{ padding:9px 10px; border-bottom:1px solid #1B2225; text-align:left; }}
th {{ color:#9AA7B2; font-size:11.5px; text-transform:uppercase; letter-spacing:.05em; }}
td:first-child {{ color:#9AA7B2; font-size:12.5px; text-transform:uppercase; letter-spacing:.04em; white-space:nowrap; }}
tbody tr:hover td {{ background:#161D20; }}
.selo {{ display:inline-block; padding:2px 10px; border-radius:999px; font-weight:700;
  font-size:11px; color:#0F1416; white-space:nowrap; }}
.rodape {{ color:#9AA7B2; font-size:12.5px; border-top:1px solid #1B2225; margin-top:26px; padding-top:12px; }}
{CSS_MENU}{_CSS_RK_MAIS}
{relatorio_html.CSS_MARCA}
</style>
</head>
<body>
<div class="pagina">
  {relatorio_html.marca_html("index.html")}
  {menu_html()}
  <h1>Comparar ações</h1>
  <div class="meta">os mesmos fatos, lado a lado — sem "vencedor": a decisão é sua ·
  <a href="acoes.html">voltar para todas as ações</a></div>
  <div class="seletores">
    <select id="f1" onchange="renderiza()"><option value="">papel 1…</option>{opcoes}</select>
    <select id="f2" onchange="renderiza()"><option value="">papel 2…</option>{opcoes}</select>
    <select id="f3" onchange="renderiza()"><option value="">papel 3 (opcional)…</option>{opcoes}</select>
  </div>
  <div id="aviso-setor" hidden>Atenção: os papéis escolhidos são de <b>setores diferentes</b> —
  múltiplos como P/L e P/VP têm réguas próprias por setor e não se comparam diretamente entre eles.</div>
  <div id="tabela"></div>
  <div class="rodape">Comparação factual com dados públicos oficiais (B3 + CVM) — não é recomendação
  de investimento. Critérios e código: <a href="https://github.com/Ruamms/scout">github.com/Ruamms/scout</a></div>
</div>
<script>
const DADOS = {json_dados};
const LINHAS = [
  ["Empresa", d => d.nome],
  ["Setor", d => d.setor],
  ["Selo", d => `<span class="selo" style="background:${{d.cor}}" title="${{(d.motivos || []).join('; ')}}">${{d.selo}}</span>`],
  ["Cotação (D-1)", d => d.cotacao],
  ["P/L", d => d.pl],
  ["P/VP", d => d.pvp],
  ["DY 12 meses", d => d.dy],
  ["ROE", d => d.roe],
  ["Margem líquida", d => d.margem],
  ["EBITDA", d => d.ebitda],
  ["Dívida líq. / PL", d => d.divida_pl],
  ["Lucro (anual)", d => `${{d.lucro}} <span style="color:#6B7681">(${{d.ano}})</span>`],
  ["Receita (anual)", d => d.receita],
  ["Alertas", d => (d.motivos && d.motivos.length) ? d.motivos.join("<br>") : "nenhum alerta disparado"],
];
function renderiza() {{
  const escolhidos = ["f1", "f2", "f3"]
    .map(id => document.getElementById(id).value)
    .filter(t => t && DADOS[t]);
  const alvo = document.getElementById("tabela");
  const aviso = document.getElementById("aviso-setor");
  if (escolhidos.length < 2) {{ alvo.innerHTML = '<p class="meta">escolha pelo menos dois papéis acima.</p>'; aviso.hidden = true; return; }}
  aviso.hidden = new Set(escolhidos.map(t => DADOS[t].setor)).size <= 1;
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
{_JS_RK_MAIS}{JS_MENU}
</script>
</body>
</html>
"""


def _comparador(
    titulo: str,
    volta_href: str,
    volta_texto: str,
    dados: dict,
    opcoes: str,
    linhas_js: str,
    aviso_id: str,
    aviso_html: str,
    aviso_js: str,
    rotulo_opcao: str,
) -> str:
    """Esqueleto compartilhado dos comparadores (FII tem o seu próprio, legado)."""
    import json as _json

    json_dados = _json.dumps(dados, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{titulo} — Scout</title>
{relatorio_html.TAG_FAVICON}
<style>
:root {{ color-scheme: dark; }}
* {{ box-sizing:border-box; margin:0; }}
body {{ background:#0F1416; color:#EAEEF0; font-family:system-ui,sans-serif; line-height:1.5; }}
.pagina {{ max-width:960px; margin:0 auto; padding:28px 20px 40px; }}
h1 {{ font-family:'Scout Display',system-ui,sans-serif; font-size:30px; font-weight:700; letter-spacing:-.02em; margin:8px 0 4px; }}
.meta {{ color:#9AA7B2; font-size:13px; margin-bottom:16px; }}
a {{ color:#8FCB9B; }}
select {{ background:#161D20; color:#EAEEF0; border:1px solid #263034; border-radius:8px;
  padding:9px 12px; font-size:14px; min-width:180px; max-width:280px; }}
.seletores {{ display:flex; gap:10px; flex-wrap:wrap; margin-bottom:14px; }}
#{aviso_id} {{ background:#2a2320; border:1px solid #6b5a2a; color:#e8d9a8; padding:9px 12px;
  border-radius:8px; font-size:13px; margin-bottom:14px; }}
table {{ width:100%; border-collapse:collapse; font-size:14px; font-variant-numeric:tabular-nums; }}
th, td {{ padding:9px 10px; border-bottom:1px solid #1B2225; text-align:left; }}
th {{ color:#9AA7B2; font-size:11.5px; text-transform:uppercase; letter-spacing:.05em; }}
td:first-child {{ color:#9AA7B2; font-size:12.5px; text-transform:uppercase; letter-spacing:.04em; white-space:nowrap; }}
tbody tr:hover td {{ background:#161D20; }}
.selo {{ display:inline-block; padding:2px 10px; border-radius:999px; font-weight:700;
  font-size:11px; color:#0F1416; white-space:nowrap; }}
.rodape {{ color:#9AA7B2; font-size:12.5px; border-top:1px solid #1B2225; margin-top:26px; padding-top:12px; }}
{CSS_MENU}{_CSS_RK_MAIS}
{relatorio_html.CSS_MARCA}
</style>
</head>
<body>
<div class="pagina">
  {relatorio_html.marca_html("index.html")}
  {menu_html()}
  <h1>{titulo}</h1>
  <div class="meta">os mesmos fatos, lado a lado — sem "vencedor": a decisão é sua ·
  <a href="{volta_href}">{volta_texto}</a></div>
  <div class="seletores">
    <select id="f1" onchange="renderiza()"><option value="">{rotulo_opcao} 1…</option>{opcoes}</select>
    <select id="f2" onchange="renderiza()"><option value="">{rotulo_opcao} 2…</option>{opcoes}</select>
    <select id="f3" onchange="renderiza()"><option value="">{rotulo_opcao} 3 (opcional)…</option>{opcoes}</select>
  </div>
  <div id="{aviso_id}" hidden>{aviso_html}</div>
  <div id="tabela"></div>
  <div class="rodape">Comparação factual com dados públicos oficiais — não é recomendação
  de investimento. Critérios e código: <a href="https://github.com/Ruamms/scout">github.com/Ruamms/scout</a></div>
</div>
<script>
const DADOS = {json_dados};
const LINHAS = [
{linhas_js}
];
function renderiza() {{
  const escolhidos = ["f1", "f2", "f3"]
    .map(id => document.getElementById(id).value)
    .filter(t => t && DADOS[t]);
  const alvo = document.getElementById("tabela");
  const aviso = document.getElementById("{aviso_id}");
  if (escolhidos.length < 2) {{ alvo.innerHTML = '<p class="meta">escolha pelo menos dois acima.</p>'; aviso.hidden = true; return; }}
  aviso.hidden = {aviso_js};
  const cabecalho = "<tr><th></th>" + escolhidos.map(t => `<th><a href="${{DADOS[t].url}}">${{DADOS[t].titulo_coluna}}</a></th>`).join("") + "</tr>";
  const corpo = LINHAS.map(([rotulo, extrator]) =>
    "<tr><td>" + rotulo + "</td>" + escolhidos.map(t => "<td>" + extrator(DADOS[t]) + "</td>").join("") + "</tr>"
  ).join("");
  alvo.innerHTML = "<table><thead>" + cabecalho + "</thead><tbody>" + corpo + "</tbody></table>";
}}
const parametros = new URLSearchParams(location.search);
["f1", "f2", "f3"].forEach(id => {{
  const escolhido = (parametros.get(id) || "").toUpperCase();
  if (escolhido && DADOS[escolhido]) document.getElementById(id).value = escolhido;
}});
renderiza();
{_JS_RK_MAIS}{JS_MENU}
</script>
</body>
</html>
"""


def _pagina_comparar_etfs(etfs: list[dict]) -> str:
    """Comparador de ETFs: fatos por fundo, com aviso quando as CLASSES
    diferem (renda fixa, cripto e ações têm regras e riscos próprios)."""
    from .. import formato

    def _ou_traco(valor, formatador):
        return formatador(valor) if valor is not None else "—"

    dados = {}
    for d in sorted(etfs, key=lambda x: x["etf"]["ticker"]):
        ticker = d["etf"]["ticker"]
        taxa = d.get("taxa_adm") or {}
        proventos = d.get("proventos") or []
        pl_row = d.get("pl")  # Row (pl, competencia) do CDA — não um número
        motivos = [f.titulo for f in d["flags"].flags] if d.get("flags") else []
        dados[ticker] = {
            "url": f"{ticker}.html",
            "titulo_coluna": ticker,
            "nome": (d["etf"]["denominacao"] or "")[:60],
            "classe": d["classe"] or "ETF",
            "selo": d["selo"].rotulo if d.get("selo") else "—",
            "cor": _COR_SELO.get(d["selo"].nivel, "#7C8894") if d.get("selo") else "#7C8894",
            "motivos": motivos,
            "cotacao": _ou_traco(d.get("preco_atual"), lambda v: f"R$ {formato.decimal(v)}"),
            "variacao": _ou_traco(d.get("variacao_12m"), formato.percentual),
            "pl": _ou_traco(pl_row["pl"] if pl_row else None, formato.moeda_compacta),
            "taxa": _ou_traco(taxa.get("taxa_adm_aa"), lambda v: f"{formato.percentual(v)} a.a."),
            "liquidez": _ou_traco(d.get("liquidez"), lambda v: f"{formato.moeda_compacta(v)}/dia"),
            "renda": (
                f"sim — R$ {formato.decimal(proventos[0]['valor'])}/cota (NÃO isento de IR)"
                if proventos
                else "não distribui (acumula no preço)"
            ),
        }
    opcoes = "".join(
        f'<option value="{t}">{t} — {_e(v["nome"][:32])}</option>' for t, v in dados.items()
    )
    linhas_js = """
  ["ETF", d => d.nome],
  ["Classe", d => d.classe],
  ["Selo", d => `<span class="selo" style="background:${d.cor}" title="${(d.motivos || []).join('; ')}">${d.selo}</span>`],
  ["Cotação (D-1)", d => d.cotacao],
  ["Variação 12 meses", d => d.variacao],
  ["Patrimônio (CDA)", d => d.pl],
  ["Taxa total", d => d.taxa],
  ["Liquidez média", d => d.liquidez],
  ["Distribui renda?", d => d.renda],
  ["Alertas", d => (d.motivos && d.motivos.length) ? d.motivos.join("<br>") : "nenhum alerta disparado"],
""".strip("\n")
    return _comparador(
        titulo="Comparar ETFs",
        volta_href="etfs.html",
        volta_texto="voltar para todos os ETFs",
        dados=dados,
        opcoes=opcoes,
        linhas_js=linhas_js,
        aviso_id="aviso-classe",
        aviso_html=(
            "Atenção: os ETFs escolhidos são de <b>classes diferentes</b> — renda fixa, ações e "
            "cripto têm regras, tributação e riscos próprios; os números não se comparam diretamente."
        ),
        aviso_js='new Set(escolhidos.map(t => DADOS[t].classe)).size <= 1',
        rotulo_opcao="ETF",
    )


def _pagina_comparar_bancos(bancos: list[dict]) -> str:
    """Comparador de emissores de CDB: a saúde de cada banco lado a lado.
    Números absolutos não se comparam entre portes — o aviso lembra isso."""
    from .. import formato
    from .banco_html import _TCB, _rotulo_tri, nome_curto, slug

    def _ou_traco(valor, formatador):
        return formatador(valor) if valor is not None else "—"

    dados = {}
    for d in sorted(bancos, key=lambda x: -(x["atual"].get("captacoes") or 0)):
        banco = d["banco"]
        cod = banco["cod_inst"]
        atual = d["atual"]
        motivos = [f.titulo for f in d["flags"].flags] if d.get("flags") else []
        dados[cod] = {
            "url": f"{slug(cod)}.html",
            "titulo_coluna": nome_curto(banco["nome"])[:22],
            "nome": nome_curto(banco["nome"])[:60],
            "tipo": _TCB.get(banco["tcb"], banco["tcb"] or "—"),
            "porte": banco["segmento"] or "—",
            "selo": d["selo"].rotulo if d.get("selo") else "—",
            "cor": _COR_SELO.get(d["selo"].nivel, "#7C8894") if d.get("selo") else "#7C8894",
            "motivos": motivos,
            "basileia": _ou_traco(atual.get("basileia"), formato.percentual),
            "caixa": (
                f"{formato.moeda_compacta(atual['caixa'])}"
                f" ({formato.percentual(100 * atual['caixa'] / atual['ativo'])} do ativo)"
                if atual.get("caixa") is not None and atual.get("ativo")
                else "—"
            ),
            "captacoes": _ou_traco(atual.get("captacoes"), formato.moeda_compacta),
            "carteira": _ou_traco(atual.get("carteira"), formato.moeda_compacta),
            "lucro": _ou_traco(atual.get("lucro"), formato.moeda_compacta),
            "pl": _ou_traco(atual.get("pl"), formato.moeda_compacta),
            "ate": _rotulo_tri(atual["anomes"]),
        }
    opcoes = "".join(
        f'<option value="{c}">{_e(v["nome"][:36])}</option>' for c, v in dados.items()
    )
    linhas_js = """
  ["Banco", d => d.nome],
  ["Tipo", d => d.tipo],
  ["Porte (BCB)", d => d.porte],
  ["Selo", d => `<span class="selo" style="background:${d.cor}" title="${(d.motivos || []).join('; ')}">${d.selo}</span>`],
  ["Índice de Basileia", d => d.basileia + ' <span style="color:#6B7681">(mínimo ~10,5%)</span>'],
  ["Liquidez imediata", d => d.caixa],
  ["Captações", d => d.captacoes],
  ["Carteira de crédito", d => d.carteira],
  ["Lucro no ano", d => d.lucro],
  ["Patrimônio líquido", d => d.pl],
  ["Dados até", d => d.ate],
  ["Alertas", d => (d.motivos && d.motivos.length) ? d.motivos.join("<br>") : "nenhum alerta disparado"],
""".strip("\n")
    return _comparador(
        titulo="Comparar bancos (CDB)",
        volta_href="bancos.html",
        volta_texto="voltar para todos os bancos",
        dados=dados,
        opcoes=opcoes,
        linhas_js=linhas_js,
        aviso_id="aviso-porte",
        aviso_html=(
            "Atenção: os bancos escolhidos têm <b>portes regulatórios diferentes</b> — números "
            "absolutos (captações, lucro, PL) não se comparam entre um banco sistêmico e um pequeno; "
            "o que se compara é o índice (Basileia) e os alertas. O FGC cobre R$ 250 mil por CPF "
            "por conglomerado, independentemente do tamanho do emissor."
        ),
        aviso_js='new Set(escolhidos.map(t => DADOS[t].porte)).size <= 1',
        rotulo_opcao="banco",
    )


_VISIVEIS_DE_INICIO = 10  # tabela abre com o TOP 10 (rankings logo abaixo); o resto sob demanda


def _indice(fundos: list, base: list, agora: datetime, tipos_fii: dict | None = None) -> str:
    from .. import tipo_fii as _tipo

    tipos_fii = tipos_fii or {}
    linhas = "".join(
        _linha_fundo(resumo, extra=posicao >= _VISIVEIS_DE_INICIO, tipo=tipos_fii.get(resumo.cnpj))
        for posicao, resumo in enumerate(fundos)
    )
    tipos_contagem: dict[str, int] = {}
    for resumo in fundos:
        tipo = tipos_fii.get(resumo.cnpj)
        if tipo:
            tipos_contagem[tipo] = tipos_contagem.get(tipo, 0) + 1
    filtros_tipo = "".join(
        f'<button class="filtro-tipo" data-tipo="{_e(tipo)}" onclick="filtraTipo(this, \'{_e(tipo)}\')">'
        f"{_e(tipo)} <b>{tipos_contagem[tipo]}</b></button>"
        for tipo in _tipo.ORDEM
        if tipos_contagem.get(tipo)
    )
    rankings = "".join(
        _bloco_ranking(titulo, ranking.montar(None, por=por, top=20, sem_alertas=sem_alertas, fundos=base))
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
body {{ background:#0F1416; color:#EAEEF0; font-family:system-ui,sans-serif; line-height:1.5; }}
.pagina {{ max-width:1020px; margin:0 auto; padding:28px 20px 40px; }}
.marca {{ color:#9AA7B2; font-size:14px; letter-spacing:.14em; text-transform:uppercase; }}
h1 {{ font-family:'Scout Display',system-ui,sans-serif; font-size:30px; font-weight:700; letter-spacing:-.02em; margin:4px 0 6px; }}
.meta {{ color:#9AA7B2; font-size:13px; }}
a {{ color:#8FCB9B; }}
input#busca {{ width:100%; background:#161D20; color:#EAEEF0; border:1px solid #263034;
  border-radius:10px; padding:12px 16px; font-size:16px; margin:18px 0 10px; }}
.atualizacao {{ display:flex; align-items:center; gap:12px; flex-wrap:wrap; margin-top:10px; }}
.btn-atu {{ background:#1B2225; border:1px solid #263034; color:#8FCB9B; text-decoration:none;
  padding:5px 13px; border-radius:8px; font-size:12.5px; font-weight:600; }}
.btn-atu:hover {{ border-color:#8FCB9B; }}
.barra {{ width:180px; height:6px; background:#1B2225; border-radius:99px; overflow:hidden; }}
.barra .preencher {{ width:40%; height:100%; background:#8FCB9B; border-radius:99px;
  animation: desliza 1.2s ease-in-out infinite; }}
@keyframes desliza {{ 0% {{ margin-left:-40%; }} 100% {{ margin-left:100%; }} }}
table {{ width:100%; border-collapse:collapse; font-size:13.5px; font-variant-numeric:tabular-nums; }}
th {{ color:#9AA7B2; font-size:11.5px; text-transform:uppercase; letter-spacing:.05em;
  text-align:left; padding:8px 10px; position:sticky; top:0; z-index:2; background:#0F1416;
  box-shadow:inset 0 -1px 0 #263034; }}
td {{ padding:7px 10px; border-bottom:1px solid #1B2225; }}
tbody tr:hover td {{ background:#161D20; }}
.btn-todos {{ display:block; margin:12px auto 0; background:#1B2225; border:1px solid #263034;
  color:#8FCB9B; padding:8px 22px; border-radius:8px; font-size:13.5px; font-weight:600; cursor:pointer; }}
.btn-todos:hover {{ border-color:#8FCB9B; }}
.filtros {{ display:flex; flex-wrap:wrap; align-items:center; gap:7px; margin:0 0 10px; }}
.filtros .rot {{ color:#9AA7B2; font-size:12px; }}
.filtro-tipo {{ background:#161D20; color:#9AA7B2; border:1px solid #263034; border-radius:99px;
  padding:5px 13px; font-size:12.5px; cursor:pointer; }}
.filtro-tipo:hover {{ border-color:#8FCB9B; color:#8FCB9B; }}
.filtro-tipo.ativo {{ background:#8FCB9B; color:#0F1416; border-color:#8FCB9B; font-weight:700; }}
.filtro-tipo b {{ color:inherit; }}
td:not(:first-child):not(:nth-child(2)):not(:nth-child(3)):not(:last-child), th:not(:first-child):not(:nth-child(2)):not(:nth-child(3)):not(:last-child) {{ text-align:right; }}
th.col-selo, td.col-selo {{ text-align:left; }}
.selo {{ display:inline-block; padding:2px 10px; border-radius:999px; font-weight:700;
  font-size:11px; color:#0F1416; white-space:nowrap; }}
h2 {{ font-family:'Scout Display',system-ui,sans-serif; font-size:22px; font-weight:700; letter-spacing:-.01em; margin:28px 0 10px; }}
.blocos {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:14px; }}
.bloco {{ background:#161D20; border:1px solid #1B2225; border-radius:10px; padding:14px 16px; }}
.bloco h3 {{ font-size:14px; color:#9AA7B2; margin-bottom:8px; }}
.bloco ol {{ padding-left:22px; font-size:13.5px; }}
.bloco li {{ margin:4px 0; }}
.rodape {{ color:#9AA7B2; font-size:12.5px; border-top:1px solid #1B2225; margin-top:30px; padding-top:14px; }}
#aviso-beta {{ position:fixed; inset:0; background:rgba(16,20,21,.75); z-index:50;
  display:flex; align-items:center; justify-content:center; padding:20px; }}
#aviso-beta[hidden] {{ display:none; }}
.beta-caixa {{ background:#161D20; border:1px solid #263034; border-radius:12px; padding:22px 24px;
  max-width:440px; font-size:14px; box-shadow:0 12px 40px rgba(0,0,0,.5); }}
.beta-caixa p {{ color:#9AA7B2; margin:10px 0 14px; }}
.beta-caixa button {{ background:#8FCB9B; color:#0F1416; border:none; border-radius:9px;
  padding:8px 22px; font-size:13.5px; font-weight:700; cursor:pointer; }}
{CSS_MENU}{_CSS_RK_MAIS}
{relatorio_html.CSS_MARCA}
</style>
</head>
<body>
<div id="aviso-beta" hidden>
  <div class="beta-caixa">
    <b>O Scout está em beta.</b>
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
  fonte de cada um. Informes da CVM, relatório gerencial e cotações, no reconhecimento de cada fundo.</div>
  <div class="meta">{len(fundos)} fundos negociáveis analisados com dados públicos oficiais ·
  atualizado em {agora.strftime("%d/%m/%Y %H:%M")} ·
  <a href="etfs.html">ETFs</a> ·
  <a href="comparar.html">comparar fundos</a></div>

  <div class="atualizacao">
    <span id="atu-texto" class="meta">verificando status da atualização…</span>
    <div id="atu-barra" class="barra" hidden><div class="preencher"></div></div>
    <a class="btn-atu" href="{_URL_WORKFLOW}" target="_blank" rel="noopener"
     title="Abre o GitHub Actions — clique em 'Run workflow' para atualizar agora (requer permissão no repositório)">
    🔄 Atualizar agora</a>
  </div>

  <input id="busca" type="search" placeholder="Busque por ticker, nome, segmento ou tipo… (ex.: HGLG, shopping, papel)"
   oninput="filtrar(this.value)">

  {f'<div class="filtros"><span class="rot">tipo (pela carteira CVM):</span> {filtros_tipo}</div>' if filtros_tipo else ""}

  <table id="fundos">
    <thead><tr><th>ticker</th><th>fundo</th><th>segmento</th><th>DY 12m</th><th>P/VP</th><th>PL</th><th class="col-selo">selo</th></tr></thead>
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
  <a href="https://github.com/Ruamms/scout">github.com/Ruamms/scout</a></div>
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
let termoAtivo = '';
let tipoAtivo = '';

function aplicar() {{
  const filtrando = termoAtivo !== '' || tipoAtivo !== '';
  document.querySelectorAll('#fundos tbody tr').forEach(tr => {{
    const casaTexto = termoAtivo === '' || tr.dataset.busca.includes(termoAtivo);
    const casaTipo = tipoAtivo === '' || tr.dataset.tipo === tipoAtivo;
    const recolhida = !filtrando && !todosVisiveis && tr.classList.contains('fundo-extra');
    tr.hidden = !(casaTexto && casaTipo) || recolhida;
  }});
  const botao = document.getElementById('ver-todos');
  if (botao) botao.hidden = todosVisiveis || filtrando || !document.querySelector('.fundo-extra');
}}

function filtrar(texto) {{
  termoAtivo = texto.trim().toLowerCase();
  aplicar();
}}

function filtraTipo(botao, tipo) {{
  tipoAtivo = tipoAtivo === tipo ? '' : tipo;  // clicar no ativo desmarca
  document.querySelectorAll('.filtro-tipo').forEach(b =>
    b.classList.toggle('ativo', b === botao && tipoAtivo !== ''));
  aplicar();
}}

function mostrarTodos() {{
  todosVisiveis = true;
  aplicar();
}}

// ?tipo=X na URL (vindo dos chips da home) pré-seleciona o filtro
const tipoUrl = new URLSearchParams(location.search).get('tipo');
if (tipoUrl) {{
  const botao = Array.from(document.querySelectorAll('.filtro-tipo')).find(b => b.dataset.tipo === tipoUrl);
  if (botao) filtraTipo(botao, tipoUrl);
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
{_JS_RK_MAIS}{JS_MENU}
</script>
</body>
</html>
"""


def _linha_fundo(resumo, extra: bool = False, tipo: str | None = None) -> str:
    def _ou_traco(valor, formatador):
        return formatador(valor) if valor is not None else "—"

    cor = _COR_SELO.get(resumo.selo.nivel, "#7C8894")
    dica = "Alertas: " + "; ".join(resumo.motivos) if resumo.motivos else resumo.selo.descricao
    # o tipo também entra na busca livre (ex.: digitar "papel" filtra os de papel)
    partes = [resumo.ticker, resumo.nome, resumo.segmento, *([tipo] if tipo else [])]
    busca = " ".join(partes).lower().replace('"', "")
    oculta = ' class="fundo-extra" hidden' if extra else ""
    return (
        f'<tr data-busca="{busca}" data-tipo="{_e(tipo or "")}"{oculta}>'
        f'<td><a href="{resumo.ticker}.html">{resumo.ticker}</a></td>'
        f"<td>{resumo.nome[:42]}</td><td>{resumo.segmento}</td>"
        f"<td>{_ou_traco(resumo.dy_12m, formato.percentual)}</td>"
        f"<td>{_ou_traco(resumo.pvp, formato.decimal)}</td>"
        f"<td>{_ou_traco(resumo.pl, formato.moeda_compacta)}</td>"
        f'<td class="col-selo"><span class="selo-dot" style="color:{cor}" title="{dica}"><span class="pt" style="background:{cor}"></span>{resumo.selo.rotulo}</span></td></tr>'
    )


def _pagina_metodologia(agora: datetime) -> str:
    """Metodologia + aviso legal + dados pessoais — a blindagem pública: o que
    o Scout é (dados públicos organizados com critérios abertos) e o que NÃO é
    (análise, consultoria ou recomendação)."""
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Metodologia e aviso legal — Scout</title>
{relatorio_html.TAG_FAVICON}
<style>
:root {{ color-scheme: dark; }}
* {{ box-sizing:border-box; margin:0; }}
body {{ background:#0F1416; color:#EAEEF0; font-family:system-ui,sans-serif; line-height:1.65; }}
.pagina {{ max-width:780px; margin:0 auto; padding:28px 20px 40px; }}
h1 {{ font-family:'Scout Display',system-ui,sans-serif; font-size:30px; font-weight:700; letter-spacing:-.02em; margin:8px 0 4px; }}
h2 {{ font-family:'Scout Display',system-ui,sans-serif; font-size:19px; font-weight:700; margin:26px 0 8px; }}
p, li {{ color:#C7CFD4; font-size:14.5px; }}
ul {{ padding-left:22px; margin:8px 0; }}
a {{ color:#8FCB9B; }}
.destaque {{ background:#161D20; border:1px solid #8FCB9B; border-radius:10px; padding:14px 18px; margin:14px 0; }}
.rodape {{ color:#9AA7B2; font-size:12.5px; border-top:1px solid #1B2225; margin-top:26px; padding-top:12px; }}
{CSS_MENU}{_CSS_RK_MAIS}
{relatorio_html.CSS_MARCA}
</style>
</head>
<body>
<div class="pagina">
  {relatorio_html.marca_html("index.html")}
  {menu_html()}
  <h1>Metodologia e aviso legal</h1>

  <div class="destaque"><p><b>O Scout é um projeto particular, de cunho educacional</b> — um estudo
  aberto de desenvolvimento de software sobre dados públicos do mercado, sem fins comerciais.
  <b>Não é recomendação de investimento.</b> Não somos analistas nem
  consultores de valores mobiliários (Resoluções CVM 20/2021 e 19/2021) e não recomendamos comprar,
  vender ou manter nenhum ativo. O que fazemos: organizar DADOS PÚBLICOS OFICIAIS com critérios
  abertos e auditáveis. A decisão é sempre sua — e retorno passado não garante futuro.</p></div>

  <h2>De onde vêm os números</h2>
  <p>Todo número exibido sai de documento público oficial, citado na própria página:</p>
  <ul>
    <li><b>FIIs</b> — informes mensais/trimestrais/anuais e registro de fundos (dados abertos da CVM),
    documentos do FNET (B3), cotação = fechamento oficial D-1 (B3, série histórica);</li>
    <li><b>ETFs</b> — carteiras (CDA/CVM), listagem e preços (B3), proventos e regulamentos (FNET);</li>
    <li><b>Ações</b> — DFP/ITR/FRE/FCA e fatos relevantes (dados abertos da CVM), eventos e proventos (B3);</li>
    <li><b>Bancos (CDB)</b> — IF.data do Banco Central (<a href="https://www3.bcb.gov.br/ifdata/"
    target="_blank" rel="noopener">ifdata.bcb.gov.br</a>), conglomerado prudencial, com o relatório e o
    trimestre citados em cada alerta;</li>
    <li>índices e renda fixa — Banco Central (SGS) e ANBIMA (dados públicos).</li>
  </ul>

  <h2>Como nascem selos e red flags</h2>
  <p>O selo é uma <b>síntese mecânica</b>: regras determinísticas, publicadas em
  <a href="https://github.com/Ruamms/scout">código aberto</a>, rodam sobre os dados oficiais e o selo
  reflete a maior severidade disparada. Cada alerta carrega o fato, a evidência numérica e a fonte —
  nunca uma opinião nossa sobre o ativo, e <b>nunca uma acusação</b>: são retratos de dados públicos,
  que podem ter explicações legítimas próprias de cada negócio. Regra sem dado suficiente aparece como
  "não avaliada" — nunca vira aprovação nem alerta silencioso.</p>

  <h2>Calculadoras</h2>
  <p>Graham, Bazin, Gordon, gross-up de CDB e cobertura do FGC são <b>ferramentas aritméticas</b> de
  fórmulas públicas: os resultados dependem das premissas que VOCÊ digita e não são preço-alvo nem
  recomendação nossa. Elas ficam fechadas até você optar por abri-las.</p>

  <h2>Leituras por IA</h2>
  <p>Uma IA local resume documentos oficiais (relatórios, fatos relevantes, atas) apenas EXTRAINDO
  fatos com citação do trecho — é proibida de criar números ou opinar. Ainda assim <b>pode conter
  erros de leitura</b>: todos os links para os documentos originais ficam na página para conferência.</p>

  <h2>Dados pessoais (LGPD)</h2>
  <p>A seção "Quem manda na empresa" exibe nome, cargo e experiência de administradores exatamente
  como publicados pela CVM no Formulário de Referência — documento público obrigatório cuja finalidade
  legal é informar o público investidor. Identificadores pessoais presentes na fonte são usados
  <b>somente</b> para cruzar a mesma pessoa entre companhias e <b>nunca são exibidos</b>. Visitantes:
  não usamos cookies nem identificamos ninguém — a medição de audiência é anônima e agregada.
  Titulares de dados podem falar conosco pelo canal abaixo.</p>

  <h2>Erros e correções</h2>
  <p>Trabalhamos com melhor esforço sobre fontes oficiais, sem garantia de exatidão, completude ou
  atualidade — a fonte pode errar, atrasar ou mudar de formato, e nosso processamento também pode
  falhar. Encontrou erro? Use o botão <b>"reportar"</b> presente em todas as páginas ou abra uma issue
  no <a href="https://github.com/Ruamms/scout/issues">GitHub</a>: corrigimos e o histórico fica público.</p>

  <div class="rodape">Não é recomendação de investimento · critérios e código:
  <a href="https://github.com/Ruamms/scout">github.com/Ruamms/scout</a> ·
  atualizado em {agora.strftime("%d/%m/%Y")}</div>
</div>
<script>
{_JS_RK_MAIS}{JS_MENU}
</script>
</body>
</html>
"""


def _bloco_ranking(titulo: str, resultado) -> str:
    itens = "".join(
        f'<li{_rk_oculto(posicao)}><a href="{linha.ticker}.html">{linha.ticker}</a> — '
        f"{_valor_criterio(resultado.criterio, linha)}</li>"
        for posicao, linha in enumerate(resultado.linhas, 1)
    )
    return (
        f'<div class="bloco"><h3>{titulo}</h3><ol>{itens or "<li>—</li>"}</ol>'
        f"{_rk_botao(len(resultado.linhas))}</div>"
    )


# rankings abrem no top 5; o "ver mais" revela até o 20º (pedido do dono)
_RK_VISIVEIS = 5


def _rk_oculto(posicao: int) -> str:
    return ' class="rk-extra" hidden' if posicao > _RK_VISIVEIS else ""


def _rk_botao(total: int) -> str:
    if total <= _RK_VISIVEIS:
        return ""
    return f'<button class="rk-mais" onclick="rkMais(this)">ver top {total}</button>'


_CSS_RK_MAIS = """
.rk-mais { background:#1B2225; border:1px solid #33434A; color:#8FCB9B; border-radius:8px;
  padding:4px 12px; font-size:12px; font-weight:600; cursor:pointer; margin-top:8px; }
.rk-mais:hover { border-color:#8FCB9B; }
"""

_JS_RK_MAIS = """
function rkMais(botao) {
  botao.parentElement.querySelectorAll('.rk-extra').forEach(li => li.hidden = false);
  botao.remove();
}
"""


def _valor_criterio(criterio: str, linha) -> str:
    if criterio == "dy":
        return f"DY {formato.percentual(linha.dy_12m)}"
    if criterio == "pvp":
        return f"P/VP {formato.decimal(linha.pvp)}"
    if criterio == "pl":
        return f"PL {formato.moeda_compacta(linha.pl)}"
    return ""
