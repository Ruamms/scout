"""Página de AÇÃO — raio-x da EMPRESA visto pelo papel consultado.

Decisão do roadmap (A4): página por EMPRESA com N papéis. Cada papel (PETR3,
PETR4…) tem a sua URL e mostra a mesma empresa — múltiplos do papel consultado
em destaque (P/L, P/VP e DY dependem do preço DAQUELE papel) e os papéis irmãos
com link. A carteirinha de regras explica a classe para leigo (isenção dos
R$ 20 mil, JCP tributado, ON vs PN vs unit). Tudo factual, com fonte — nunca
recomendação.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime

from .. import analise, armazenamento, formato, series
from . import graficos
from .html import CSS_MARCA, TAG_FAVICON, _e, marca_html

# carteirinha de regras da classe — linguagem de leigo, fatos com fonte
REGRAS_ACOES = (
    "Uma ação = um pedaço da empresa. O retorno vem de dois lugares: valorização "
    "do preço e proventos (dividendos e JCP).",
    "IR na venda: 15% sobre o ganho em operações comuns — mas vendas de até "
    "R$ 20 mil/MÊS (somando todas as ações) são ISENTAS (Lei 9.250/1995, art. 22). "
    "Day trade não tem isenção e paga 20%.",
    "Dividendos chegam LÍQUIDOS (isentos de IR hoje). JCP (juros sobre capital "
    "próprio) chega com 15% retido na fonte — o valor anunciado não é o valor "
    "que cai na conta.",
    "ON (final 3) = ação ordinária, dá direito a VOTO e ao tag along mínimo de "
    "80% em venda de controle. PN (final 4) = preferencial, prioridade nos "
    "proventos mas em geral sem voto. UNIT (final 11) = pacote com ON+PN juntas.",
    "O preço aqui é o fechamento oficial da B3 do último pregão (D-1) — não é "
    "cotação em tempo real.",
)

_RODAPE = (
    "Isto não é recomendação de investimento. Fontes: B3 (cotações oficiais "
    "COTAHIST, listagem, eventos e proventos) e CVM (cadastro de companhias e "
    "demonstrações financeiras padronizadas — DFP). Regras tributárias citadas "
    "em caráter informativo — confirme com um contador."
)


def montar_dados_acao(con: sqlite3.Connection, ticker: str, hoje: date | None = None) -> dict | None:
    """Reúne tudo que a página da ação precisa; None se o ticker não for um
    papel conhecido (escopo v1 = IBrX-100)."""
    from ..coleta import fundamentos as modulo_fundamentos

    hoje = hoje or date.today()
    ticker = ticker.strip().upper()
    empresa = armazenamento.empresa_por_ticker(con, ticker)
    if empresa is None:
        return None
    papeis = armazenamento.papeis_da_empresa(con, empresa["cod_cvm"])
    balancos = armazenamento.fundamentos_da_empresa(con, empresa["cod_cvm"])
    indicadores = modulo_fundamentos.indicadores(balancos[-1]) if balancos else {}

    cotacoes = armazenamento.serie_cotacoes(con, ticker)
    cotacao = [(l["competencia"], l["fechamento"]) for l in cotacoes if l["fechamento"]]
    ajustado = [
        (l["competencia"], l["fechamento_ajustado"]) for l in cotacoes if l["fechamento_ajustado"]
    ]
    indices = {nome: armazenamento.serie_indice(con, nome) for nome in ("CDI", "IPCA")}
    meta = armazenamento.cotacao_meta(con, ticker)

    # múltiplos de TODOS os papéis da empresa (cada um com o seu preço)
    multiplos_por_papel = {
        p["ticker"]: {
            **modulo_fundamentos.multiplos_do_papel(con, p["ticker"], hoje),
            "tipo": p["tipo"],
            "preco": (m["preco_atual"] if (m := armazenamento.cotacao_meta(con, p["ticker"])) else None),
            "proventos_12m": armazenamento.proventos_12m(con, p["ticker"], hoje),
        }
        for p in papeis
    }

    ultimo_provento = con.execute(
        "SELECT * FROM acao_proventos WHERE ticker = ? ORDER BY data_com DESC LIMIT 1",
        (ticker,),
    ).fetchone()
    proventos_ano = armazenamento.proventos_por_ano(con, ticker)
    # preço de referência por ano (fechamento do último mês disponível do ano):
    # base do DY histórico do gráfico de proventos
    preco_fim_ano: dict[int, float] = {}
    for competencia, valor in cotacao:
        preco_fim_ano[int(competencia[:4])] = valor

    # red flags societárias (A3, benchmarkadas) + selo — mesmos 5 níveis de FII/ETF
    from .. import acao_flags, redflags

    resultado_flags = acao_flags.avaliar(
        {
            "empresa": empresa,
            "balancos": balancos,
            "metas": armazenamento.dfp_meta_da_empresa(con, empresa["cod_cvm"]),
            "auditores": armazenamento.auditores_da_empresa(con, empresa["cod_cvm"]),
            "proventos_ano_por_ticker": {
                p["ticker"]: armazenamento.proventos_por_ano(con, p["ticker"]) for p in papeis
            },
            "eventos": con.execute(
                f"SELECT data, label, fator FROM acao_eventos WHERE ticker IN "
                f"({','.join('?' * len(papeis))})",
                [p["ticker"] for p in papeis],
            ).fetchall(),
        },
        hoje=hoje,
    )

    administradores = con.execute(
        "SELECT * FROM administradores WHERE cod_cvm = ? ORDER BY orgao, nome",
        (empresa["cod_cvm"],),
    ).fetchall()
    partes = con.execute(
        "SELECT * FROM partes_relacionadas WHERE cod_cvm = ?"
        " ORDER BY montante DESC NULLS LAST LIMIT 8",
        (empresa["cod_cvm"],),
    ).fetchall()

    return {
        "proventos_por_ano": proventos_ano,
        "preco_fim_ano": preco_fim_ano,
        "administradores": administradores,
        "partes_relacionadas": partes,
        "flags": resultado_flags,
        "selo": redflags.selo(resultado_flags),
        "ticker": ticker,
        "empresa": empresa,
        "papeis": papeis,
        "balancos": balancos,
        "indicadores": indicadores,
        "multiplos": multiplos_por_papel,
        "cotacao": cotacao,
        "preco_atual": meta["preco_atual"] if meta else None,
        "cotado_em": meta["cotado_em"] if meta else None,
        "variacao_12m": series.variacao_pct(
            [{"competencia": c, "fechamento": v} for c, v in ajustado], "fechamento", 12
        ),
        "rentabilidade": analise._rentabilidades(cotacao, ajustado, indices),
        "ultimo_provento": ultimo_provento,
        "liquidez": armazenamento.liquidez_recente(con, ticker),
    }


def _trunca(texto: str, limite: int) -> str:
    texto = (texto or "").strip()
    return texto if len(texto) <= limite else texto[: limite - 1] + "…"


def _setor_curto(empresa) -> str:
    """Setor legível: o setor_b3 vem como 'A / B / C' — o 1º nível já orienta."""
    bruto = (empresa["setor_b3"] or empresa["setor_cvm"] or "").strip()
    return bruto.split("/")[0].strip().rstrip(".") if bruto else "—"


_AVISO_CALC = (
    '<div style="background:#2a2320;border:1px solid #6b5a2a;color:#e8d9a8;'
    'padding:10px 12px;border-radius:8px;font-size:13px;margin:6px 0">'
    "Esta calculadora está aqui para <b>facilitar sua análise</b> — <b>não é recomendação</b> de "
    "compra ou venda. O resultado depende inteiramente das premissas que <b>VOCÊ</b> define. "
    "É uma simulação sua, não um veredito do Scout.</div>"
)


def _calculadora_graham(preco: float, lpa: float | None, vpa: float | None, ano: int) -> str:
    """Preço justo de Graham — EXTRA opt-in no mesmo padrão da Gordon dos FIIs:
    aviso antes do botão, prefill com os números REAIS (LPA/VPA do último anual)
    e premissa (multiplicador 22,5 = P/L 15 × P/VP 1,5) editável pelo usuário.
    Não se aplica com prejuízo ou PL negativo (raiz de número negativo)."""
    if not preco or lpa is None or vpa is None or lpa <= 0 or vpa <= 0:
        return ""
    return f"""
  <div class="calc">
    <h3>🧮 Preço justo (fórmula de Graham)</h3>
    {_AVISO_CALC}
    <button class="btn-topo" onclick="abrirCalc(this, calcGraham)">Abrir a calculadora</button>
    <div hidden>
      <p class="desc">Benjamin Graham: <b>preço justo = √(multiplicador × LPA × VPA)</b>. As letras:
      <b>LPA</b> = lucro por ação (lucro anual ÷ ações); <b>VPA</b> = valor patrimonial por ação
      (patrimônio ÷ ações); <b>multiplicador</b> = 22,5 no livro (P/L 15 × P/VP 1,5) — premissa SUA,
      ajuste à vontade. Tudo editável.</p>
      <div class="campos gordon">
        <div><label for="gr-lpa">LPA (R$)</label>
        <input type="number" id="gr-lpa" value="{lpa:.2f}" step="0.05" oninput="calcGraham()">
        <div class="gd-cap">lucro por ação do anual {ano} (DFP consolidada)</div></div>
        <div><label for="gr-vpa">VPA (R$)</label>
        <input type="number" id="gr-vpa" value="{vpa:.2f}" step="0.05" oninput="calcGraham()">
        <div class="gd-cap">valor patrimonial por ação do anual {ano}</div></div>
        <div><label for="gr-mult">Multiplicador</label>
        <input type="number" id="gr-mult" value="22.5" step="0.5" min="0.5" oninput="calcGraham()">
        <div class="gd-cap">22,5 = P/L 15 × P/VP 1,5 (os tetos que Graham considerava razoáveis)</div></div>
      </div>
      <div class="resultado">
        <div class="res"><div class="rotulo">Preço justo (com suas premissas)</div><div class="num" id="gr-justo">—</div></div>
        <div class="res"><div class="rotulo">Cotação atual (D-1)</div><div class="num">R$ {preco:.2f}</div></div>
      </div>
      <p class="aviso">A fórmula usa o valor PATRIMONIAL — funciona mal para empresas de ativo leve
      (tecnologia, serviços) e não se aplica a prejuízo. Modelo do livro "O Investidor Inteligente"
      (1949), sensível às premissas: não é recomendação nem promessa de retorno.</p>
    </div>
  </div>"""


def _calculadora_bazin(preco: float, media5: float, prov_12m: float, n_anos: int) -> str:
    """Preço-teto de Bazin — EXTRA opt-in no padrão da Gordon: base do dividendo
    escolhida por botão (média dos últimos anos CHEIOS × últimos 12 meses) e o
    DY mínimo (6% no método clássico) é premissa editável do usuário."""
    if not preco or (media5 <= 0 and prov_12m <= 0):
        return ""
    tem_media = media5 > 0
    val_padrao = media5 if tem_media else prov_12m
    modo_padrao = "med" if tem_media else "12m"
    ativo_med = "ativo" if tem_media else ""
    ativo_12m = "" if tem_media else "ativo"
    btn_media = f"Média dos últimos {n_anos} anos" if n_anos else "Média (sem anos cheios)"
    return f"""
  <div class="calc">
    <h3>🧮 Preço-teto (método Bazin)</h3>
    {_AVISO_CALC}
    <button class="btn-topo" onclick="abrirCalc(this, calcBazin)">Abrir a calculadora</button>
    <div hidden>
      <p class="desc">Décio Bazin: <b>preço-teto = dividendo anual por ação ÷ DY mínimo</b>. O
      preço-teto é o MÁXIMO que você pagaria para que os dividendos rendam pelo menos o DY que
      você exige (6% a.a. no método clássico). Tudo editável.</p>
      <div class="gd-base">Base do dividendo:
        <button type="button" class="{ativo_med}" onclick="bazinBase('med', this)">{btn_media}</button>
        <button type="button" class="{ativo_12m}" onclick="bazinBase('12m', this)">Últimos 12 meses</button>
      </div>
      <div class="campos gordon">
        <div><label for="bz-div">Dividendo anual por ação (R$)</label>
        <input type="number" id="bz-div" value="{val_padrao:.2f}" data-modo="{modo_padrao}" data-vmed="{media5:.2f}" data-v12m="{prov_12m:.2f}" step="0.05" min="0" oninput="calcBazin()">
        <div class="gd-cap">valores brutos com data-com no período (JCP tem 15% retido) · fonte: B3</div></div>
        <div><label for="bz-dy">DY mínimo desejado (% a.a.)</label>
        <input type="number" id="bz-dy" value="6" step="0.5" min="0.5" oninput="calcBazin()">
        <div class="gd-cap">o retorno em dividendos que VOCÊ exige — 6% é o número do método clássico</div></div>
      </div>
      <div class="resultado">
        <div class="res"><div class="rotulo">Preço-teto (com suas premissas)</div><div class="num" id="bz-teto">—</div></div>
        <div class="res"><div class="rotulo">Cotação atual (D-1)</div><div class="num">R$ {preco:.2f}</div></div>
      </div>
      <p class="aviso">Só faz sentido para empresas que PAGAM dividendos com constância — dividendo
      passado não garante dividendo futuro (a empresa pode cortar amanhã). Método do livro "Faça
      Fortuna com Ações" — não é recomendação nem promessa de retorno.</p>
    </div>
  </div>"""


def gerar(
    dados: dict,
    agora: datetime | None = None,
    com_menu: bool = False,
    leitura: dict | None = None,
    publicados: set[str] | None = None,
) -> str:
    from .html import (
        CSS_BUSCA_TOPO,
        CSS_MENU,
        JS_BUSCA_TOPO,
        JS_GRAFICO_HOVER,
        JS_MENU,
        _secao_ia,
        _secao_parecer,
        menu_html,
    )

    agora = agora or datetime.now()
    menu = menu_html() if com_menu else ""
    css_menu = (CSS_MENU + CSS_BUSCA_TOPO) if com_menu else ""
    js_menu = (JS_MENU + JS_BUSCA_TOPO) if com_menu else ""
    empresa = dados["empresa"]
    ticker = dados["ticker"]
    ind = dados["indicadores"]
    financeiro = bool(ind.get("setor_financeiro"))
    balancos = dados["balancos"]
    ultimo = balancos[-1] if balancos else None
    mult = dados["multiplos"].get(ticker, {})

    def _ajuda(_: str) -> str:  # glossário das ações entra num passo futuro
        return ""

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
              "preço ajustado por eventos e proventos")
    if mult.get("pl") is not None:
        _card("P/L", formato.decimal(mult["pl"]), "preço ÷ lucro por ação (último anual)")
    elif ultimo is not None and (ultimo["lucro_liquido"] or 0) <= 0:
        _card("P/L", "—", "empresa em prejuízo no último anual: P/L não se aplica")
    if mult.get("pvp") is not None:
        _card("P/VP", formato.decimal(mult["pvp"]), "preço ÷ valor patrimonial por ação")
    if mult.get("dy") is not None and mult.get("preco"):
        _card("Dividend yield 12m", formato.percentual(mult["dy"]),
              f"R$ {formato.decimal(mult.get('proventos_12m') or 0)}/ação em proventos (data-com)")
    if ind.get("roe") is not None:
        _card("ROE", formato.percentual(ind["roe"]), f"lucro ÷ patrimônio · anual {ultimo['ano']}")
    if ind.get("margem_liquida") is not None:
        _card("Margem líquida", formato.percentual(ind["margem_liquida"]),
              f"lucro ÷ receita · anual {ultimo['ano']}")
    if ind.get("ebitda") is not None:
        _card("EBITDA", formato.moeda_compacta(ind["ebitda"]),
              f"margem {formato.percentual(ind['margem_ebitda'])} · anual {ultimo['ano']}"
              if ind.get("margem_ebitda") is not None else f"anual {ultimo['ano']}")
    if ind.get("divida_liquida") is not None:
        rotulo_div = "caixa líquido" if ind["divida_liquida"] < 0 else "dívida líquida"
        extra_div = (
            f"{formato.decimal(ind['divida_liquida_pl'])}× o patrimônio líquido"
            if ind.get("divida_liquida_pl") is not None
            else ""
        )
        _card(rotulo_div.capitalize(), formato.moeda_compacta(abs(ind["divida_liquida"])), extra_div)
    if ultimo is not None and ultimo["lucro_liquido"] is not None:
        _card("Lucro líquido", formato.moeda_compacta(ultimo["lucro_liquido"]),
              f"anual {ultimo['ano']} (DFP consolidada)")
    if dados["liquidez"]:
        _card("Liquidez", f"{formato.moeda_compacta(dados['liquidez'])}/dia",
              "volume financeiro médio por pregão (3 meses)")
    if financeiro:
        _card("Setor financeiro", '<span class="compacto">banco/seguradora</span>',
              "margem bruta, EBITDA e dívida não se aplicam ao modelo contábil")

    # --- papéis da empresa (cada um com o seu preço e múltiplos) -------------
    linhas_papeis = []
    for p in dados["papeis"]:
        t = p["ticker"]
        m = dados["multiplos"].get(t, {})
        atual = " ◀" if t == ticker else ""
        nome_papel = (
            f"<b>{_e(t)}</b>{atual}"
            if t == ticker
            else (f'<a href="{_e(t)}.html">{_e(t)}</a>' if (publicados and t in publicados) else _e(t))
        )
        fmt = lambda v, f=formato.decimal: f(v) if v is not None else "—"  # noqa: E731
        linhas_papeis.append(
            f"<tr><td>{nome_papel}</td><td>{_e(p['tipo'] or '—')}</td>"
            f"<td>{'R$ ' + formato.decimal(m['preco']) if m.get('preco') else '—'}</td>"
            f"<td>{fmt(m.get('pl'))}</td><td>{fmt(m.get('pvp'))}</td>"
            f"<td>{fmt(m.get('dy'), formato.percentual)}</td></tr>"
        )
    secao_papeis = f"""
  <h2>Papéis da empresa</h2>
  <div class="grafico">
  <table class="imoveis">
    <thead><tr><th>papel</th><th>tipo</th><th>preço (D-1)</th><th>P/L</th><th>P/VP</th><th>DY 12m</th></tr></thead>
    <tbody>{''.join(linhas_papeis)}</tbody>
  </table>
  <div class="nota">mesma empresa, preços independentes por papel — P/L, P/VP e DY seguem o preço de cada um</div>
  </div>
"""

    # --- balanço anual (série de até 4 anos, DFP consolidada) ----------------
    secao_balanco = ""
    if balancos:
        from ..coleta import fundamentos as modulo_fundamentos

        def _dinheiro(v):
            return formato.moeda_compacta(v) if v is not None else "—"

        def _pct(v):
            return formato.percentual(v) if v is not None else "—"

        linhas_anos = []
        for b in balancos:
            i = modulo_fundamentos.indicadores(b)
            colunas = [str(b["ano"]), _dinheiro(b["receita"]), _dinheiro(b["lucro_liquido"]),
                       _pct(i.get("margem_liquida")), _pct(i.get("roe"))]
            if not financeiro:
                colunas += [_dinheiro(i.get("ebitda")), _dinheiro(i.get("divida_liquida"))]
            colunas += [_dinheiro(b["patrimonio_liquido"])]
            linhas_anos.append("<tr>" + "".join(f"<td>{c}</td>" for c in colunas) + "</tr>")
        cab = ["ano", "receita", "lucro líquido", "margem líq.", "ROE"]
        if not financeiro:
            cab += ["EBITDA", "dívida líquida"]
        cab += ["patrimônio líquido"]
        cabecalho = "".join(f"<th>{c}</th>" for c in cab)

        grafico_resultado = ""
        serie_receita = [(str(b["ano"]), b["receita"]) for b in balancos if b["receita"] is not None]
        serie_lucro = [(str(b["ano"]), b["lucro_liquido"]) for b in balancos if b["lucro_liquido"] is not None]
        series_plot = [s for s in (("Receita", serie_receita), ("Lucro líquido", serie_lucro)) if len(s[1]) >= 2]
        if series_plot:
            svg = graficos.grafico_linhas(series_plot, formatador=formato.moeda_compacta)
            if svg:
                grafico_resultado = f'<div class="grafico"><h3>Receita × Lucro líquido (anual)</h3>{svg}</div>'

        secao_balanco = f"""
  <h2>Balanço anual (DFP)</h2>
  <div class="grafico">
  <table class="imoveis">
    <thead><tr>{cabecalho}</tr></thead>
    <tbody>{''.join(linhas_anos)}</tbody>
  </table>
  <div class="nota">demonstrações financeiras padronizadas (CVM), consolidado · valores do exercício
  {"· banco/seguradora: EBITDA e dívida não se aplicam" if financeiro else ""}</div>
  </div>
  {grafico_resultado}
"""

    grafico_cotacao = ""
    if dados["cotacao"]:
        svg = graficos.grafico_linhas(
            [("Cotação", dados["cotacao"])],
            formatador=lambda v: f"R$ {formato.decimal(v)}",
        )
        if svg:
            grafico_cotacao = (
                f'<h2>Gráficos</h2><div class="grafico"><h3>Cotação (fechamento oficial B3)</h3>{svg}</div>'
            )

    rentabilidade = ""
    janela_maxima = dados["rentabilidade"].get("máximo") or dados["rentabilidade"].get("12 meses")
    if janela_maxima and "com" in janela_maxima:
        svg = graficos.grafico_linhas(
            janela_maxima["com"], formatador=lambda v: formato.percentual(v)
        )
        if svg:
            rentabilidade = (
                f'<div class="grafico"><h3>Rentabilidade acumulada × CDI × IPCA</h3>{svg}'
                '<div class="nota">retorno total (preço ajustado por eventos + proventos '
                "reinvestidos) · índices: Banco Central</div></div>"
            )

    itens_regras = "".join(f"<li>{_e(regra)}</li>" for regra in REGRAS_ACOES)
    ultimo_prov = dados["ultimo_provento"]
    if ultimo_prov:
        itens_regras += (
            f"<li><b>Último provento deste papel:</b> {_e(ultimo_prov['label'] or 'provento')} de "
            f"R$ {formato.decimal(ultimo_prov['valor'])}/ação (data-com "
            f"{formato.dia_br(ultimo_prov['data_com'])}) — fonte: B3.</li>"
        )

    # --- Histórico de proventos por ano (barras R$/ação + DY do ano) ----------
    secao_proventos = ""
    proventos_ano = dados.get("proventos_por_ano") or {}
    if proventos_ano:
        preco_fim = dados.get("preco_fim_ano") or {}
        anos_prov = sorted(proventos_ano)[-10:]
        pontos = [(str(ano), proventos_ano[ano]) for ano in anos_prov]
        extras = [
            f"DY {formato.percentual(100 * proventos_ano[ano] / preco_fim[ano])}"
            if preco_fim.get(ano)
            else None
            for ano in anos_prov
        ]
        svg_prov = graficos.grafico_barras(
            pontos, formatador=lambda v: f"R$ {formato.decimal(v)}", extras=extras
        )
        if svg_prov:
            secao_proventos = f"""
  <h2>Histórico de proventos</h2>
  <div class="grafico"><h3>Proventos por ação por ano (R$) · DY do ano no topo</h3>{svg_prov}
  <div class="nota">soma dos proventos com data-com no ano (dividendos + JCP, valores brutos — JCP tem
  15% retido na fonte) · DY = proventos do ano ÷ fechamento do fim do ano · fonte: B3</div></div>
"""

    # --- Calculadoras (opt-in, mesmo padrão da Gordon dos FIIs) ---------------
    lpa = vpa = None
    if ultimo is not None and empresa["acoes_total"]:
        if ultimo["lucro_liquido"] is not None:
            lpa = ultimo["lucro_liquido"] / empresa["acoes_total"]
        if ultimo["patrimonio_liquido"] is not None:
            vpa = ultimo["patrimonio_liquido"] / empresa["acoes_total"]
    ano_atual = agora.year
    anos_cheios = [a for a in sorted(proventos_ano) if a < ano_atual][-5:]
    media5 = sum(proventos_ano[a] for a in anos_cheios) / len(anos_cheios) if anos_cheios else 0.0
    prov_12m = mult.get("proventos_12m") or 0.0
    calc_graham = _calculadora_graham(dados["preco_atual"] or 0, lpa, vpa, ultimo["ano"] if ultimo else 0)
    calc_bazin = _calculadora_bazin(dados["preco_atual"] or 0, media5, prov_12m, len(anos_cheios))
    secao_calculadoras = ""
    if calc_graham or calc_bazin:
        secao_calculadoras = f"""
  <h2 id="calculadoras">Calculadoras</h2>
{calc_graham}
{calc_bazin}
"""

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
            itens_ok = "".join(f"<li>{_e(texto)}</li>" for texto in resultado.aprovadas)
            partes.append(
                '<p class="ok">✓ Verificações que rodaram e passaram sem alerta:</p>'
                f'<ul class="ok">{itens_ok}</ul>'
            )
        for pendente in resultado.nao_avaliadas:
            partes.append(f'<p class="na">· não avaliada: {_e(pendente)}</p>')
        flags_html = f"<h2>🚩 Red flags</h2>{''.join(partes)}"

    # --- Quem manda na empresa (FRE estruturado — conselho/diretoria/fiscal) --
    secao_adm = ""
    administradores = dados.get("administradores") or []
    if administradores:
        def _orgao_curto(texto: str) -> str:
            t = (texto or "").lower()
            if "conselho de administra" in t and "diretoria" in t:
                return "Conselho + Diretoria"
            if "conselho de administra" in t:
                return "Conselho de Administração"
            if "diretoria" in t:
                return "Diretoria"
            if "fiscal" in t:
                return "Conselho Fiscal"
            return texto or "—"

        def _cargo_curto(texto: str) -> str:
            partes_c = (texto or "").split(" - ", 1)
            return partes_c[1] if len(partes_c) == 2 else (texto or "—")

        linhas_adm = []
        for a in administradores:
            desde = a["primeiro_mandato"][:4] if a["primeiro_mandato"] else "—"
            presenca = formato.percentual(a["presenca"]) if a["presenca"] is not None else "—"
            badge = (
                ' <span style="font-size:9.5px;font-weight:700;letter-spacing:.05em;'
                'text-transform:uppercase;background:#1B2225;color:#9AA7B2;border:1px solid #263034;'
                'border-radius:99px;padding:1px 7px">eleito p/ controlador</span>'
                if a["controlador"]
                else ""
            )
            titulo_exp = _e((a["experiencia"] or "")[:300])
            linhas_adm.append(
                f'<tr><td title="{titulo_exp}">{_e(a["nome"])}{badge}</td>'
                f"<td>{_e(_orgao_curto(a['orgao']))}</td><td>{_e(_trunca(_cargo_curto(a['cargo']), 38))}</td>"
                f"<td>{desde}</td><td>{presenca}</td></tr>"
            )
        referencia_adm = administradores[0]["referencia"] or ""
        secao_adm = f"""
  <h2>Quem manda na empresa</h2>
  <div class="grafico">
  <table class="imoveis">
    <thead><tr><th>nome</th><th>órgão</th><th>cargo</th><th>na casa desde</th><th>presença</th></tr></thead>
    <tbody>{''.join(linhas_adm)}</tbody>
  </table>
  <div class="nota">Formulário de Referência (FRE/CVM{f", ref. {formato.dia_br(referencia_adm)}" if referencia_adm else ""}) —
  passe o mouse no nome para ver a experiência declarada · "presença" = % de participação nas reuniões do órgão</div>
  </div>
"""

    secao_partes = ""
    partes_rel = dados.get("partes_relacionadas") or []
    if partes_rel:
        linhas_pr = []
        for p in partes_rel:
            montante = formato.moeda_compacta(p["montante"]) if p["montante"] else "—"
            linhas_pr.append(
                f'<tr><td title="{_e((p["objeto"] or "")[:280])}">{_e(_trunca(p["parte"], 46))}</td>'
                f'<td title="{_e((p["relacao"] or "")[:200])}">{_e(_trunca(p["relacao"] or "—", 40))}</td>'
                f"<td>{montante}</td><td>{formato.dia_br(p['data']) if p['data'] else '—'}</td></tr>"
            )
        secao_partes = f"""
  <h2>Transações com partes relacionadas</h2>
  <div class="grafico">
  <table class="imoveis">
    <thead><tr><th>parte relacionada</th><th>relação com a empresa</th><th>montante</th><th>data</th></tr></thead>
    <tbody>{''.join(linhas_pr)}</tbody>
  </table>
  <div class="nota">as maiores transações declaradas no FRE (negócios da empresa com quem é "de casa":
  controlador, coligadas, administradores) — passe o mouse para ver o objeto do contrato · fatos declarados, não julgamento</div>
  </div>
"""

    auditor = (empresa["auditor"] or "").strip()
    meta_auditor = f" · auditor: {_e(_trunca(auditor, 40))}" if auditor else ""
    situacao = (empresa["situacao"] or "").strip().upper()
    aviso_situacao = (
        f'<span class="selo" style="background:#DB7A7A">{_e(situacao.title())}</span>'
        if situacao and situacao != "ATIVO"
        else ""
    )

    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(ticker)} — Scout</title>
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
.calc .gd-base {{ display:flex; flex-wrap:wrap; align-items:center; gap:8px; margin:0 0 12px; color:#9AA7B2; font-size:12px; }}
.calc .gd-base button {{ background:#1B2225; color:#9AA7B2; border:1px solid #33434A; border-radius:7px; padding:4px 12px; font-size:12px; cursor:pointer; }}
.calc .gd-base button.ativo {{ background:#8FCB9B; color:#0F1416; border-color:#8FCB9B; font-weight:700; }}
.calc .gd-cap {{ margin-top:5px; max-width:170px; font-size:11px; color:#6B7681; line-height:1.5; }}
.btn-topo {{ background:#1B2225; border:1px solid #33434A; color:#8FCB9B; padding:6px 14px; border-radius:8px; font-size:13px; font-weight:600; cursor:pointer; }}
.btn-topo:hover {{ border-color:#8FCB9B; }}
.regras {{ background:#161D20; border:1px solid #8FCB9B; border-radius:10px; padding:16px 18px; }}
.regras h2 {{ margin:0 0 8px; font-size:16px; color:#8FCB9B; }}
.regras li {{ margin:6px 0 6px 18px; font-size:14px; }}
.grafico {{ background:#161D20; border:1px solid #1B2225; border-radius:10px; padding:14px 16px 10px; margin-bottom:14px; }}
.grafico h3 {{ font-size:15px; color:#9AA7B2; margin-bottom:8px; }}
.grafico .nota, .nota {{ color:#6B7681; font-size:11.5px; }}
table.imoveis {{ width:100%; border-collapse:collapse; font-size:13.5px; font-variant-numeric:tabular-nums; }}
table.imoveis th {{ color:#9AA7B2; font-size:11.5px; text-transform:uppercase; letter-spacing:.05em; text-align:left; padding:6px 10px; border-bottom:1px solid #263034; }}
table.imoveis td {{ padding:7px 10px; border-bottom:1px solid #1B2225; }}
table.imoveis td:not(:first-child):not(:nth-child(2)), table.imoveis th:not(:first-child):not(:nth-child(2)) {{ text-align:right; }}
.rodape {{ color:#9AA7B2; font-size:12.5px; border-top:1px solid #1B2225; margin-top:30px; padding-top:14px; }}
{css_menu}
{CSS_MARCA}
</style>
</head>
<body>
<div class="pagina">
  {marca_html("index.html", com_busca_ticker=com_menu)}
  {menu}
  <h1>{_e(ticker)} <small title="{_e(empresa["nome"] or "")}">{_e(_trunca(empresa["nome_pregao"] or empresa["nome"] or "", 60))}</small> {selo_html}{aviso_situacao}</h1>
  <div class="meta">Ação · {_e(dados["multiplos"].get(ticker, {}).get("tipo") or "")} · {_e(_setor_curto(empresa))}
  · {_e(empresa["segmento_listagem"] or "—")}{meta_auditor} · página gerada em {agora.strftime("%d/%m/%Y %H:%M")}</div>

  <div class="cards">{"".join(cards)}</div>

  {flags_html}

  {_secao_parecer(leitura)}

  {_secao_ia(leitura, agora)}

  <div class="regras">
  <h2>As regras desta classe (Ações)</h2>
  <ul>{itens_regras}</ul>
  </div>

  {secao_papeis}

  {secao_adm}

  {secao_partes}

  {secao_balanco}

  {secao_proventos}

  {grafico_cotacao}
  {rentabilidade}

  {secao_calculadoras}

  <div class="rodape">{_RODAPE}<br>
  Projeto open source: <a href="https://github.com/Ruamms/scout">github.com/Ruamms/scout</a>
  · <a href="apoie.html">apoie o projeto</a>
  · <a href="acoes.html">todas as ações</a> · <a href="index.html">início</a></div>
</div>
<script>
const num = id => {{ const el = document.getElementById(id); return el ? (parseFloat(el.value) || 0) : 0; }};
const brl2 = v => v.toLocaleString('pt-BR', {{style: 'currency', currency: 'BRL', minimumFractionDigits: 2}});

function calcGraham() {{
  const el = document.getElementById('gr-justo');
  if (!el) return;
  const lpa = num('gr-lpa'), vpa = num('gr-vpa'), mult = num('gr-mult');
  if (lpa <= 0 || vpa <= 0 || mult <= 0) {{ el.textContent = 'não se aplica (LPA/VPA ≤ 0)'; return; }}
  el.textContent = brl2(Math.sqrt(mult * lpa * vpa));
}}

function calcBazin() {{
  const el = document.getElementById('bz-teto');
  if (!el) return;
  const div = num('bz-div'), dy = num('bz-dy') / 100;
  if (div <= 0 || dy <= 0) {{ el.textContent = '—'; return; }}
  el.textContent = brl2(div / dy);
}}

function bazinBase(modo, botao) {{
  const inp = document.getElementById('bz-div');
  if (!inp) return;
  inp.dataset.modo = modo;
  inp.value = modo === '12m' ? inp.dataset.v12m : inp.dataset.vmed;
  if (botao) botao.parentElement.querySelectorAll('button').forEach(b => b.classList.toggle('ativo', b === botao));
  calcBazin();
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
