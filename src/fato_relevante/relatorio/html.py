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
    if dados.vacancia:
        secoes_graficos.append(
            _card_grafico(
                "Vacância (%)",
                graficos.grafico_linhas(
                    [("Vacância", dados.vacancia)], formatador=lambda v: formato.percentual(v)
                ),
                nota="vacância física ponderada pela área dos imóveis, por trimestre",
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

    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(raiox.ticker)} — Fato Relevante</title>
<style>
:root {{ color-scheme: dark; }}
html {{ scroll-behavior: smooth; }}
* {{ box-sizing: border-box; margin: 0; }}
body {{ background:#0b1017; color:#dbe3ec; font-family:system-ui,-apple-system,sans-serif; line-height:1.5; }}
.pagina {{ max-width:960px; margin:0 auto; padding:28px 20px 40px; }}
a {{ color:#5eead4; }}
.topo {{ display:flex; flex-wrap:wrap; align-items:baseline; gap:10px 14px; }}
.marca {{ color:#8b98a9; font-size:14px; letter-spacing:.14em; text-transform:uppercase; }}
h1 {{ font-size:34px; }} h1 small {{ color:#8b98a9; font-size:17px; font-weight:400; }}
.selo {{ display:inline-block; padding:4px 14px; border-radius:999px; font-weight:700; font-size:14px; color:#0b1017; }}
.btn-topo {{ margin-left:auto; background:#1a2432; border:1px solid #2a3441; color:#5eead4; text-decoration:none; padding:6px 14px; border-radius:8px; font-size:13px; font-weight:600; }}
.btn-topo:hover {{ border-color:#5eead4; }}
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
.ajuda {{ display:inline-flex; align-items:center; justify-content:center; width:15px; height:15px;
  border-radius:50%; background:#2a3441; color:#8b98a9; font-size:10px; font-weight:700;
  cursor:help; position:relative; vertical-align:middle; margin-left:5px; }}
.ajuda .dica {{ visibility:hidden; opacity:0; transition:opacity .15s; position:absolute; z-index:10;
  bottom:135%; left:50%; transform:translateX(-50%); width:270px; background:#1a2432;
  border:1px solid #2a3441; border-radius:9px; padding:10px 12px; color:#dbe3ec;
  font-size:12.5px; font-weight:400; line-height:1.45; text-transform:none; letter-spacing:0;
  text-align:left; box-shadow:0 6px 20px rgba(0,0,0,.45); }}
.ajuda:hover .dica, .ajuda:focus .dica {{ visibility:visible; opacity:1; }}
.calc {{ background:#121a24; border:1px solid #1f2a38; border-radius:10px; padding:16px; margin-bottom:14px; }}
.calc h3 {{ font-size:15px; color:#aeb9c7; margin-bottom:4px; }}
.calc .desc {{ color:#8b98a9; font-size:13px; margin-bottom:12px; }}
.calc .campos {{ display:flex; flex-wrap:wrap; gap:10px; align-items:end; }}
.calc label {{ display:block; color:#8b98a9; font-size:11.5px; text-transform:uppercase; letter-spacing:.05em; margin-bottom:3px; }}
.calc input[type=number] {{ background:#0b1017; color:#dbe3ec; border:1px solid #2a3441; border-radius:8px; padding:8px 10px; width:130px; font-size:15px; }}
.calc select {{ background:#0b1017; color:#dbe3ec; border:1px solid #2a3441; border-radius:8px; padding:8px 10px; font-size:15px; }}
.calc .check {{ display:flex; align-items:center; gap:6px; color:#aeb9c7; font-size:13px; padding-bottom:8px; }}
.calc .resultado {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(170px,1fr)); gap:10px; margin-top:14px; }}
.calc .res {{ background:#0b1017; border:1px solid #1f2a38; border-radius:9px; padding:10px 12px; }}
.calc .res .rotulo {{ color:#8b98a9; font-size:11.5px; text-transform:uppercase; letter-spacing:.05em; }}
.calc .res .num {{ font-size:19px; font-weight:700; margin-top:2px; color:#5eead4; }}
.calc .aviso {{ color:#66707d; font-size:11.5px; margin-top:10px; }}
table.imoveis {{ width:100%; border-collapse:collapse; font-size:13.5px; }}
table.imoveis th {{ color:#8b98a9; font-size:11.5px; text-transform:uppercase; letter-spacing:.05em; text-align:left; padding:6px 10px; border-bottom:1px solid #2a3441; }}
table.imoveis td {{ padding:7px 10px; border-bottom:1px solid #1a2432; }}
table.imoveis td:not(:first-child), table.imoveis th:not(:first-child) {{ text-align:right; }}
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
    <a class="btn-topo" href="#calculadoras">🧮 Calculadoras</a>
  </div>
  <div class="meta">
    {_e(raiox.cnpj)} · {_e(raiox.classificacao)} · Gestão {_e(raiox.gestao.lower())}<br>
    informes CVM até <b>{_e(raiox.dados_ate)}</b>{_cotacao_em(raiox)} · relatório gerado em {agora.strftime("%d/%m/%Y %H:%M")}
  </div>

  <div class="cards">{_cards_indicadores(raiox)}</div>

  <h2>🚩 Red flags{_ajuda("Red flags")}</h2>
  {_secao_flags(raiox)}

  {_secao_imoveis(raiox)}

  {_secao_administrador(raiox)}

  <h2>Gráficos</h2>
  {"".join(secoes_graficos) or '<p class="na">sem séries suficientes para gráficos</p>'}

  {_secao_calculadoras(completo)}

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
        extra = f"12m: {_e(linha.doze_meses)}" if linha.doze_meses != "—" else ""
        historico = _e(linha.historico) if linha.historico != "—" else ""
        separador = " · " if extra and historico else ""
        cards.append(
            f'<div class="{classe}"><div class="nome">{_e(linha.nome)}'
            f'{" ⚠" if linha.alerta else ""}{_ajuda(linha.nome)}</div>'
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


def _secao_imoveis(raiox: RaioX, limite: int = 10) -> str:
    if not raiox.imoveis:
        return ""

    def _pct(valor: float | None) -> str:
        return formato.percentual(valor) if valor is not None else "—"

    linhas = []
    for imovel in raiox.imoveis[:limite]:
        area = f"{formato.decimal(imovel.area, 0)} m²" if imovel.area else "—"
        linhas.append(
            f"<tr><td>{_e(imovel.nome)}</td><td>{area}</td>"
            f"<td>{_pct(imovel.pct_receita)}</td><td>{_pct(imovel.vacancia)}</td>"
            f"<td>{_pct(imovel.inadimplencia)}</td></tr>"
        )
    rodape_tabela = ""
    if len(raiox.imoveis) > limite:
        rodape_tabela = (
            f'<tr><td colspan="5" class="na">… e mais '
            f"{len(raiox.imoveis) - limite} imóveis no informe</td></tr>"
        )
    return f"""
  <h2>Imóveis ({len(raiox.imoveis)}){_ajuda("Imóveis")}</h2>
  <div class="grafico" style="overflow-x:auto">
  <table class="imoveis">
    <thead><tr><th>imóvel</th><th>área</th><th>% da receita</th><th>vacância</th><th>inadimplência</th></tr></thead>
    <tbody>{"".join(linhas)}{rodape_tabela}</tbody>
  </table>
  <div class="nota">informe trimestral de {_e(raiox.imoveis_em)} · ordenados por participação na receita</div>
  </div>
"""


def _secao_administrador(raiox: RaioX, limite: int = 12) -> str:
    if not raiox.fundos_irmaos:
        return ""
    linhas = []
    for irmao in raiox.fundos_irmaos[:limite]:
        cor = _COR_SELO.get(irmao.selo.nivel, "#94a3b8") if irmao.selo else "#94a3b8"
        selo = (
            f'<span class="selo" style="background:{cor};font-size:11px;padding:2px 10px" '
            f'title="{_e(irmao.selo.descricao)}">{_e(irmao.selo.rotulo)}</span>'
            if irmao.selo
            else "—"
        )
        rotulo = (
            f'<a href="{_e(irmao.ticker)}.html">{_e(irmao.ticker)}</a>'
            if irmao.ticker
            else _e(irmao.nome[:40])
        )
        idade = f"{irmao.anos:.0f} anos" if irmao.anos >= 1 else "&lt;1 ano"
        linhas.append(
            f"<tr><td>{rotulo}</td><td>{_e(irmao.nome[:44])}</td>"
            f"<td>{idade}</td><td>{_e(irmao.segmento)}</td><td>{selo}</td></tr>"
        )
    rodape_tabela = ""
    if len(raiox.fundos_irmaos) > limite:
        rodape_tabela = (
            f'<tr><td colspan="5" class="na">… e mais '
            f"{len(raiox.fundos_irmaos) - limite} fundos do mesmo administrador</td></tr>"
        )
    return f"""
  <h2>Administrador{_ajuda("Administrador")}</h2>
  <div class="grafico" style="overflow-x:auto">
  <p class="desc" style="color:#aeb9c7;font-size:13.5px;margin-bottom:10px">
  <b>{_e(raiox.administrador)}</b> administra outros {len(raiox.fundos_irmaos)} FIIs na base da CVM:</p>
  <table class="imoveis">
    <thead><tr><th>ticker</th><th>fundo</th><th>idade</th><th>segmento</th><th>selo</th></tr></thead>
    <tbody>{"".join(linhas)}{rodape_tabela}</tbody>
  </table>
  <div class="nota">selo calculado sem cotação de bolsa (P/VP fora) · o link abre o relatório do
  fundo se ele já tiver sido gerado · ticker derivado do ISIN</div>
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
"""


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
    <div class="nota">* marcado: rentabilidade com proventos reinvestidos (cotação ajustada, Yahoo);
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
