"""Gera o site estático completo: índice buscável + página de cada FII.

Pensado para rodar no GitHub Actions e publicar no GitHub Pages, mas
funciona igual localmente: `fato site` gera tudo em uma pasta.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from .. import analise, formato, ranking
from . import apoio
from . import html as relatorio_html

_COR_SELO = relatorio_html._COR_SELO


def gerar(
    con: sqlite3.Connection,
    destino: Path,
    com_cotacoes: bool = True,
    limite: int | None = None,
    ao_progredir: Callable[[str], None] | None = None,
    agora: datetime | None = None,
) -> dict:
    destino.mkdir(parents=True, exist_ok=True)
    progresso = ao_progredir or (lambda mensagem: None)

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
        from ..coleta import cotacoes, indices

        indices.garantir_atualizados(con)
        for posicao, resumo in enumerate(fundos, start=1):
            cotacoes.garantir_atualizada(con, resumo.ticker)
            time.sleep(0.15)  # educação com a fonte de cotações
            if posicao % 50 == 0:
                progresso(f"cotações: {posicao}/{len(fundos)}")
        # re-varre para os resumos (P/VP dos rankings/pares) enxergarem os preços
        base = ranking.varrer(con)
        por_ticker = {resumo.ticker: resumo for resumo in base if resumo.ticker}
        fundos = [por_ticker.get(resumo.ticker, resumo) for resumo in fundos]

    publicados = []
    for posicao, resumo in enumerate(fundos, start=1):
        completo = analise.montar_completo(con, resumo.ticker, varredura=base)
        if completo is None:
            continue
        relatorio_html.salvar(completo, destino, agora=agora)
        publicados.append(resumo)
        if posicao % 50 == 0:
            progresso(f"páginas: {posicao}/{len(fundos)}")

    apoio.salvar(destino)
    (destino / "index.html").write_text(
        _indice(publicados, base, agora or datetime.now()), encoding="utf-8"
    )
    return {"paginas": len(publicados), "destino": str(destino)}


def _indice(fundos: list, base: list, agora: datetime) -> str:
    linhas = "".join(_linha_fundo(resumo) for resumo in fundos)
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
<title>Fato Relevante — o raio-x dos FIIs</title>
<style>
:root {{ color-scheme: dark; }}
* {{ box-sizing:border-box; margin:0; }}
body {{ background:#0b1017; color:#dbe3ec; font-family:system-ui,sans-serif; line-height:1.5; }}
.pagina {{ max-width:1020px; margin:0 auto; padding:28px 20px 40px; }}
.marca {{ color:#8b98a9; font-size:14px; letter-spacing:.14em; text-transform:uppercase; }}
h1 {{ font-size:30px; margin:4px 0 6px; }}
.meta {{ color:#8b98a9; font-size:13px; }}
a {{ color:#5eead4; }}
input#busca {{ width:100%; background:#121a24; color:#dbe3ec; border:1px solid #2a3441;
  border-radius:10px; padding:12px 16px; font-size:16px; margin:18px 0 10px; }}
table {{ width:100%; border-collapse:collapse; font-size:13.5px; }}
th {{ color:#8b98a9; font-size:11.5px; text-transform:uppercase; letter-spacing:.05em;
  text-align:left; padding:6px 10px; border-bottom:1px solid #2a3441; position:sticky; top:0; background:#0b1017; }}
td {{ padding:7px 10px; border-bottom:1px solid #1a2432; }}
td:not(:first-child):not(:nth-child(2)):not(:nth-child(3)), th:not(:first-child):not(:nth-child(2)):not(:nth-child(3)) {{ text-align:right; }}
.selo {{ display:inline-block; padding:2px 10px; border-radius:999px; font-weight:700;
  font-size:11px; color:#0b1017; white-space:nowrap; }}
h2 {{ font-size:18px; margin:28px 0 10px; }}
.blocos {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:14px; }}
.bloco {{ background:#121a24; border:1px solid #1f2a38; border-radius:10px; padding:14px 16px; }}
.bloco h3 {{ font-size:14px; color:#aeb9c7; margin-bottom:8px; }}
.bloco ol {{ padding-left:22px; font-size:13.5px; }}
.bloco li {{ margin:4px 0; }}
.rodape {{ color:#8b98a9; font-size:12.5px; border-top:1px solid #1f2a38; margin-top:30px; padding-top:14px; }}
</style>
</head>
<body>
<div class="pagina">
  <div class="marca">FATO RELEVANTE</div>
  <h1>O raio-x dos FIIs</h1>
  <div class="meta">{len(fundos)} fundos negociáveis analisados com dados públicos oficiais ·
  atualizado em {agora.strftime("%d/%m/%Y %H:%M")} ·
  <a href="apoie.html">☕ apoie o projeto</a></div>

  <input id="busca" type="search" placeholder="Busque por ticker, nome ou segmento… (ex.: HGLG, shopping, logística)"
   oninput="filtrar(this.value)">

  <table id="fundos">
    <thead><tr><th>ticker</th><th>fundo</th><th>segmento</th><th>DY 12m</th><th>P/VP</th><th>PL</th><th>selo</th></tr></thead>
    <tbody>{linhas}</tbody>
  </table>

  <h2>Rankings do dia</h2>
  <div class="blocos">{rankings}</div>
  <p class="meta" style="margin-top:8px">rankings são fatos ordenados com critério explícito — não recomendação ·
  só fundos negociáveis · "sem alertas de atenção" = selo verde ou amarelo</p>

  <div class="rodape">Isto não é recomendação de investimento. Fontes: dados abertos da CVM,
  Banco Central (SGS) e cotações via Yahoo Finance. Critérios de todos os alertas são públicos:
  <a href="https://github.com/Ruamms/fato-relevante">github.com/Ruamms/fato-relevante</a></div>
</div>
<script>
function filtrar(texto) {{
  const termo = texto.trim().toLowerCase();
  document.querySelectorAll('#fundos tbody tr').forEach(tr => {{
    tr.hidden = termo !== '' && !tr.dataset.busca.includes(termo);
  }});
}}
</script>
</body>
</html>
"""


def _linha_fundo(resumo) -> str:
    def _ou_traco(valor, formatador):
        return formatador(valor) if valor is not None else "—"

    cor = _COR_SELO.get(resumo.selo.nivel, "#94a3b8")
    dica = "Alertas: " + "; ".join(resumo.motivos) if resumo.motivos else resumo.selo.descricao
    busca = f"{resumo.ticker} {resumo.nome} {resumo.segmento}".lower().replace('"', "")
    return (
        f'<tr data-busca="{busca}">'
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
