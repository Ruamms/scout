"""Página de BANCO emissor de CDB (R3 da Renda Fixa) — raio-x do conglomerado.

CDB/LCI/LCA não têm página própria (são produtos bilaterais): o ativo
analisável é o EMISSOR. A unidade é o conglomerado prudencial — é nele que a
Basileia é apurada e é por ele que o FGC conta o teto. Tudo factual, com
fonte (IF.data/BCB) — nunca recomendação.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from .. import banco_flags, formato, redflags
from . import graficos
from .html import CSS_MARCA, TAG_FAVICON, _e, marca_html

# carteirinha de regras da classe — linguagem de leigo, fatos com fonte
REGRAS_RF = (
    "CDB/LCI/LCA são EMPRÉSTIMOS que você faz ao banco — o risco é o banco, "
    "não a corretora que vendeu.",
    "O FGC cobre até R$ 250 mil por CPF **por conglomerado financeiro** (não é "
    "por corretora, nem por CDB!) e há um teto global de R$ 1 milhão renovável "
    "a cada 4 anos (Res. CMN 4.222).",
    "Se o banco quebrar, o FGC paga — mas a liquidação leva SEMANAS ou MESES, "
    "e nesse meio-tempo o valor NÃO rende nada.",
    "A adesão ao FGC é obrigatória por lei para bancos que captam depósitos — "
    "não existe 'CDB sem FGC' de banco; cooperativas têm um fundo próprio (FGCoop).",
    "IR regressivo sobre o rendimento do CDB: 22,5% (até 180 dias) caindo até "
    "15% (acima de 720 dias); IOF nos primeiros 30 dias. LCI/LCA são isentas "
    "de IR para pessoa física.",
    "Taxa alta é preço do risco: banco pagando muito acima dos pares costuma "
    "estar pagando caro porque PRECISA captar — confira a saúde nesta página.",
)

_RODAPE = (
    "Isto não é recomendação de investimento. Fonte: IF.data (Banco Central do "
    "Brasil, dados públicos trimestrais por conglomerado prudencial). Regras do "
    "FGC citadas em caráter informativo — confirme em fgc.org.br."
)

_TCB = {"b1": "banco comercial/múltiplo", "b2": "banco de câmbio/investimento"}


def _rotulo_tri(anomes: int) -> str:
    return f"T{anomes % 100 // 3}/{anomes // 100 % 100:02d}"


def nome_curto(nome: str) -> str:
    return (nome or "").replace(" - PRUDENCIAL", "").strip()


def slug(cod_inst: str) -> str:
    return f"banco-{cod_inst}"


def montar_dados_banco(con: sqlite3.Connection, cod_inst: str) -> dict | None:
    banco = con.execute("SELECT * FROM bancos WHERE cod_inst = ?", (cod_inst,)).fetchone()
    if banco is None:
        return None
    serie = [
        dict(l) for l in con.execute(
            "SELECT * FROM bancos_tri WHERE cod_inst = ? ORDER BY anomes", (cod_inst,)
        )
    ]
    if not serie:
        return None  # sem série no IF.data não há o que mostrar
    resultado = banco_flags.avaliar(serie)
    return {
        "banco": banco,
        "serie": serie,
        "atual": serie[-1],
        "flags": resultado,
        "selo": redflags.selo(resultado),
    }


def gerar(dados: dict, agora: datetime | None = None, com_menu: bool = False) -> str:
    from .html import (
        CSS_BUSCA_TOPO,
        CSS_MENU,
        JS_BUSCA_TOPO,
        JS_GRAFICO_HOVER,
        JS_MENU,
        _COR_SELO,
        _COR_SEVERIDADE,
        menu_html,
    )

    agora = agora or datetime.now()
    menu = menu_html() if com_menu else ""
    css_menu = (CSS_MENU + CSS_BUSCA_TOPO) if com_menu else ""
    js_menu = (JS_MENU + JS_BUSCA_TOPO) if com_menu else ""
    banco = dados["banco"]
    atual = dados["atual"]
    nome = nome_curto(banco["nome"])
    trimestre = _rotulo_tri(atual["anomes"])

    cards = []

    def _card(titulo: str, valor: str, extra: str = "") -> None:
        extra_html = f'<div class="extra">{extra}</div>' if extra else ""
        cards.append(
            f'<div class="card"><div class="nome">{titulo}</div>'
            f'<div class="valor">{valor}</div>{extra_html}</div>'
        )

    if atual.get("basileia") is not None:
        _card("Índice de Basileia", formato.percentual(atual["basileia"]),
              f"capital ÷ ativos de risco · mínimo ~10,5% com adicionais · {trimestre}")
    if atual.get("captacoes"):
        _card("Captações", formato.moeda_compacta(atual["captacoes"]),
              "inclui os CDBs/LCIs que o público comprou")
    if atual.get("carteira"):
        _card("Carteira de crédito", formato.moeda_compacta(atual["carteira"]),
              "o que o banco emprestou (classificada)")
    if atual.get("caixa") is not None and atual.get("ativo"):
        pct_caixa = 100 * atual["caixa"] / atual["ativo"]
        _card("Liquidez imediata", formato.moeda_compacta(atual["caixa"]),
              f"{formato.percentual(pct_caixa)} do ativo · caixa + interfinanceiras — "
              "títulos NÃO entram aqui")
    if atual.get("lucro") is not None:
        rotulo_lucro = "Lucro no ano" if atual["lucro"] >= 0 else "Prejuízo no ano"
        _card(rotulo_lucro, formato.moeda_compacta(abs(atual["lucro"])),
              f"acumulado até {trimestre}")
    if atual.get("pl"):
        _card("Patrimônio líquido", formato.moeda_compacta(atual["pl"]), "")
    if atual.get("ativo"):
        _card("Ativo total", formato.moeda_compacta(atual["ativo"]), "")

    # selo + flags (mesmo padrão FII/ETF/Ações)
    selo_html = ""
    if dados.get("selo"):
        cor = _COR_SELO.get(dados["selo"].nivel, "#7C8894")
        selo_html = (
            f'<span class="selo" style="background:{cor}" title="{_e(dados["selo"].descricao)}">'
            f"{_e(dados['selo'].rotulo)}</span>"
        )
    partes_flags = []
    resultado = dados["flags"]
    for flag in resultado.flags:
        cor = _COR_SEVERIDADE[flag.severidade]
        partes_flags.append(
            f'<div class="flag" style="border-left-color:{cor}">'
            f'<span class="sev" style="color:{cor}">{_e(flag.severidade.value)}</span>'
            f"<h3>{_e(flag.titulo)}</h3><p>{_e(flag.fato)}</p>"
            f'<p class="evid">evidência: {_e(flag.evidencia)}</p>'
            f'<p class="fonte">fonte: {_e(flag.fonte)}</p></div>'
        )
    if not partes_flags and resultado.aprovadas:
        partes_flags.append('<p class="ok">✓ nenhum alerta disparado</p>')
    if resultado.aprovadas:
        itens_ok = "".join(f"<li>{_e(t)}</li>" for t in resultado.aprovadas)
        partes_flags.append(
            '<p class="ok">✓ Verificações que rodaram e passaram sem alerta:</p>'
            f'<ul class="ok">{itens_ok}</ul>'
        )
    for pendente in resultado.nao_avaliadas:
        partes_flags.append(f'<p class="na">· não avaliada: {_e(pendente)}</p>')

    # série trimestral: tabela + gráfico da Basileia
    linhas_serie = "".join(
        f"<tr><td>{_rotulo_tri(l['anomes'])}</td>"
        f"<td>{formato.percentual(l['basileia']) if l.get('basileia') is not None else '—'}</td>"
        f"<td>{formato.moeda_compacta(l['captacoes']) if l.get('captacoes') else '—'}</td>"
        f"<td>{formato.moeda_compacta(l['carteira']) if l.get('carteira') else '—'}</td>"
        f"<td>{formato.moeda_compacta(l['lucro']) if l.get('lucro') is not None else '—'}</td>"
        f"<td>{formato.moeda_compacta(l['pl']) if l.get('pl') else '—'}</td></tr>"
        for l in reversed(dados["serie"])
    )
    # rótulo SORTÁVEL (AAAA-Tn): o eixo X do grafico_linhas ordena os rótulos
    # como string — "T1/25" embaralharia a cronologia (T1/24, T1/26, T2/25...)
    pontos_basileia = [
        (f"{l['anomes'] // 100}-T{l['anomes'] % 100 // 3}", l["basileia"])
        for l in dados["serie"]
        if l.get("basileia") is not None
    ]
    grafico_basileia = ""
    if len(pontos_basileia) >= 3:
        svg = graficos.grafico_linhas(
            [("Basileia", pontos_basileia)], formatador=lambda v: formato.percentual(v)
        )
        if svg:
            grafico_basileia = (
                f'<div class="grafico"><h3>Basileia por trimestre</h3>{svg}'
                '<div class="nota">o mínimo regulatório é 8% de PR/RWA + adicionais (~10,5%) · fonte: IF.data/BCB</div></div>'
            )

    itens_regras = "".join(f"<li>{_e(r).replace('**', '')}</li>" for r in REGRAS_RF)
    calculadoras = _calculadora_grossup() + _calculadora_fgc()

    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(nome)} — Scout</title>
{TAG_FAVICON}
<style>
:root {{ color-scheme: dark; }}
* {{ box-sizing:border-box; margin:0; }}
body {{ background:#0F1416; color:#EAEEF0; font-family:system-ui,sans-serif; line-height:1.5; }}
.pagina {{ max-width:960px; margin:0 auto; padding:28px 20px 40px; }}
h1 {{ font-family:'Scout Display',system-ui,sans-serif; font-size:28px; font-weight:700; letter-spacing:-.02em; margin:6px 0 2px; }}
h2 {{ font-family:'Scout Display',system-ui,sans-serif; font-size:22px; font-weight:700; letter-spacing:-.01em; margin:26px 0 10px; }}
a {{ color:#8FCB9B; }}
.meta {{ color:#9AA7B2; font-size:13px; }}
.cards {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(170px,1fr)); gap:10px; margin:20px 0; }}
.card {{ background:#161D20; border:1px solid #1B2225; border-radius:10px; padding:12px 14px; }}
.card .nome {{ color:#9AA7B2; font-size:12px; text-transform:uppercase; letter-spacing:.06em; }}
.card .valor {{ font-family:'Scout Display',system-ui,sans-serif; font-size:23px; font-weight:700; letter-spacing:-.01em; margin-top:4px; font-variant-numeric:tabular-nums; }}
.card .extra {{ color:#9AA7B2; font-size:12px; margin-top:2px; }}
.selo {{ display:inline-block; padding:3px 12px; border-radius:999px; font-weight:700;
  font-size:12px; color:#0F1416; white-space:nowrap; vertical-align:middle; }}
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
.calc {{ background:#161D20; border:1px solid #1B2225; border-radius:10px; padding:16px; margin-bottom:14px; }}
.calc h3 {{ font-size:15px; color:#9AA7B2; margin-bottom:4px; }}
.calc .desc {{ color:#9AA7B2; font-size:13px; margin-bottom:12px; }}
.calc .campos {{ display:flex; flex-wrap:wrap; gap:10px; align-items:flex-start; }}
.calc label {{ display:block; color:#9AA7B2; font-size:11.5px; text-transform:uppercase; letter-spacing:.05em; margin-bottom:3px; }}
.calc input[type=number] {{ background:#0F1416; color:#EAEEF0; border:1px solid #33434A; border-radius:8px; padding:8px 10px; width:130px; font-size:15px; }}
.calc .resultado {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(170px,1fr)); gap:10px; margin-top:14px; }}
.calc .res {{ background:#0F1416; border:1px solid #1B2225; border-radius:9px; padding:10px 12px; }}
.calc .res .rotulo {{ color:#9AA7B2; font-size:11.5px; text-transform:uppercase; letter-spacing:.05em; }}
.calc .res .num {{ font-size:19px; font-weight:700; margin-top:2px; color:#8FCB9B; }}
.calc .aviso {{ color:#6B7681; font-size:11.5px; margin-top:10px; }}
.calc .gd-cap {{ margin-top:5px; max-width:170px; font-size:11px; color:#6B7681; line-height:1.5; }}
.btn-topo {{ background:#1B2225; border:1px solid #33434A; color:#8FCB9B; padding:6px 14px; border-radius:8px; font-size:13px; font-weight:600; cursor:pointer; }}
.btn-topo:hover {{ border-color:#8FCB9B; }}
.rodape {{ color:#9AA7B2; font-size:12.5px; border-top:1px solid #1B2225; margin-top:30px; padding-top:14px; }}
{css_menu}
{CSS_MARCA}
</style>
</head>
<body>
<div class="pagina">
  {marca_html("index.html", com_busca_ticker=com_menu)}
  {menu}
  <h1>{_e(nome)} {selo_html}</h1>
  <div class="meta">Banco emissor (CDB/LCI/LCA) · {_e(_TCB.get(banco["tcb"], banco["tcb"] or ""))}
  {f"· porte {_e(banco['segmento'])}" if banco["segmento"] else ""} · conglomerado prudencial ·
  dados IF.data/BCB até <b>{trimestre}</b> · página gerada em {agora.strftime("%d/%m/%Y %H:%M")}</div>

  <div class="cards">{"".join(cards)}</div>

  <h2>🚩 Red flags</h2>
  {''.join(partes_flags)}

  <div class="regras">
  <h2>As regras desta classe (renda fixa bancária)</h2>
  <ul>{itens_regras}</ul>
  </div>

  <h2>Série trimestral</h2>
  <div class="grafico">
  <table class="imoveis">
    <thead><tr><th>trimestre</th><th>Basileia</th><th>captações</th><th>carteira</th><th>lucro no ano</th><th>PL</th></tr></thead>
    <tbody>{linhas_serie}</tbody>
  </table>
  <div class="nota">IF.data publica por trimestre com ~90 dias de atraso · lucro é o ACUMULADO no ano até o trimestre</div>
  </div>
  {grafico_basileia}

  <h2 id="calculadoras">Calculadoras</h2>
{calculadoras}

  <div class="rodape">{_RODAPE}<br>
  Projeto open source: <a href="https://github.com/Ruamms/scout">github.com/Ruamms/scout</a>
  · <a href="apoie.html">apoie o projeto</a>
  · <a href="bancos.html">todos os bancos</a> · <a href="index.html">início</a></div>
</div>
<script>
const num = id => {{ const el = document.getElementById(id); return el ? (parseFloat(el.value) || 0) : 0; }};
const brl2 = v => v.toLocaleString('pt-BR', {{style: 'currency', currency: 'BRL', minimumFractionDigits: 2}});

function calcGross() {{
  const el = document.getElementById('gs-eq');
  if (!el) return;
  const taxa = num('gs-taxa'), meses = num('gs-prazo');
  if (taxa <= 0 || meses <= 0) {{ el.textContent = '—'; return; }}
  const dias = meses * 30;
  const ir = dias <= 180 ? 22.5 : dias <= 360 ? 20 : dias <= 720 ? 17.5 : 15;
  el.textContent = (taxa * (1 - ir / 100)).toFixed(2).replace('.', ',') + '% do CDI';
  document.getElementById('gs-ir').textContent = 'alíquota de IR no prazo: ' + ir + '%';
}}

function calcFgc() {{
  const el = document.getElementById('fg-coberto');
  if (!el) return;
  const valor = num('fg-valor');
  const coberto = Math.min(valor, 250000);
  el.textContent = brl2(coberto);
  document.getElementById('fg-fora').textContent = brl2(Math.max(0, valor - 250000));
}}

function abrirCalc(botao, calc) {{
  botao.hidden = true;
  botao.nextElementSibling.hidden = false;
  if (calc) calc();
}}
{JS_GRAFICO_HOVER}
{js_menu}
</script>
</body>
</html>
"""


_AVISO_CALC = (
    '<div style="background:#2a2320;border:1px solid #6b5a2a;color:#e8d9a8;'
    'padding:10px 12px;border-radius:8px;font-size:13px;margin:6px 0">'
    "Esta calculadora está aqui para <b>facilitar sua análise</b> — <b>não é recomendação</b>. "
    "O resultado depende das premissas que <b>VOCÊ</b> define. É uma simulação sua, não um veredito do Scout.</div>"
)


def _calculadora_grossup() -> str:
    """Equivalência CDB (tributado) × LCI/LCA (isenta) — padrão opt-in da Gordon."""
    return f"""
  <div class="calc">
    <h3>🧮 CDB × LCI/LCA (equivalência com IR)</h3>
    {_AVISO_CALC}
    <button class="btn-topo" onclick="abrirCalc(this, calcGross)">Abrir a calculadora</button>
    <div hidden>
      <p class="desc">Um CDB paga IR (tabela regressiva); LCI/LCA não. Esta conta mostra
      <b>quanto do CDI uma LCI/LCA precisa pagar para empatar</b> com o CDB no prazo escolhido:
      equivalente = taxa do CDB × (1 − IR do prazo).</p>
      <div class="campos">
        <div><label for="gs-taxa">Taxa do CDB (% do CDI)</label>
        <input type="number" id="gs-taxa" value="110" step="1" min="1" oninput="calcGross()">
        <div class="gd-cap">a taxa oferecida pela corretora</div></div>
        <div><label for="gs-prazo">Prazo (meses)</label>
        <input type="number" id="gs-prazo" value="24" step="1" min="1" oninput="calcGross()">
        <div class="gd-cap">define a alíquota do IR regressivo (22,5% → 15%)</div></div>
      </div>
      <div class="resultado">
        <div class="res"><div class="rotulo">LCI/LCA equivalente</div><div class="num" id="gs-eq">—</div></div>
      </div>
      <p class="aviso"><span id="gs-ir"></span> · aproximação de comparação (mesmo indexador e prazo;
      não considera IOF de resgates em menos de 30 dias) — não é recomendação.</p>
    </div>
  </div>"""


def _calculadora_fgc() -> str:
    """Cobertura FGC por CPF por conglomerado — padrão opt-in."""
    return f"""
  <div class="calc">
    <h3>🧮 Cobertura do FGC</h3>
    {_AVISO_CALC}
    <button class="btn-topo" onclick="abrirCalc(this, calcFgc)">Abrir a calculadora</button>
    <div hidden>
      <p class="desc">O FGC cobre até <b>R$ 250 mil por CPF por conglomerado financeiro</b> —
      CDBs de bancos do MESMO conglomerado somam no mesmo teto, mesmo comprados em corretoras
      diferentes. Há ainda o teto global de R$ 1 milhão renovável a cada 4 anos.</p>
      <div class="campos">
        <div><label for="fg-valor">Total aplicado neste conglomerado (R$)</label>
        <input type="number" id="fg-valor" value="300000" step="10000" min="0" oninput="calcFgc()">
        <div class="gd-cap">principal + juros acumulados (a cobertura conta o total)</div></div>
      </div>
      <div class="resultado">
        <div class="res"><div class="rotulo">Coberto pelo FGC</div><div class="num" id="fg-coberto">—</div></div>
        <div class="res"><div class="rotulo">Fora da cobertura</div><div class="num" id="fg-fora">—</div></div>
      </div>
      <p class="aviso">Regra da Res. CMN 4.222 — e lembre: se o banco quebrar, o FGC paga, mas a
      liquidação leva semanas/meses sem o valor render nada nesse período. Não é recomendação.</p>
    </div>
  </div>"""
