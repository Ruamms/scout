"""Renderização do raio-x no terminal, com rich."""

from __future__ import annotations

from rich import box
from rich.console import Console, Group
from rich.padding import Padding
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ..modelos import RaioX, RedFlag, Severidade

_COR_SEVERIDADE = {
    Severidade.ALTA: "bold white on red",
    Severidade.MEDIA: "black on yellow",
    Severidade.BAIXA: "black on cyan",
}

_RODAPE = "Isto não é recomendação de investimento. Fontes: dados abertos da CVM."


def renderizar(raiox: RaioX, console: Console) -> None:
    console.print()
    if raiox.exemplo:
        console.print(
            Panel(
                "DADOS DE EXEMPLO — o coletor de dados reais da CVM ainda não foi ligado.",
                style="bold yellow",
                box=box.HEAVY,
            )
        )
    console.print(_cabecalho(raiox))
    console.print(_tabela_indicadores(raiox))
    console.print(_secao_red_flags(raiox))
    if raiox.sem_alerta:
        console.print(_sem_alerta(raiox))
    console.print(Padding(Text(_RODAPE, style="dim italic"), (1, 0, 1, 2)))


def _cabecalho(raiox: RaioX) -> Panel:
    linha1 = Text.assemble(
        (f" {raiox.ticker} ", "bold black on white"),
        ("  "),
        (raiox.nome, "bold"),
        ("  ·  ", "dim"),
        (raiox.cnpj, "dim"),
    )
    linha2 = Text(
        f"{raiox.classificacao}  ·  Gestão {raiox.gestao.lower()}"
        f"  ·  informes CVM até {raiox.dados_ate}",
        style="dim",
    )
    return Panel(
        Group(linha1, linha2),
        title="[bold]FATO RELEVANTE[/] [dim]— o raio-x dos ativos da bolsa[/]",
        box=box.ROUNDED,
        padding=(0, 1),
    )


def _tabela_indicadores(raiox: RaioX) -> Table:
    tabela = Table(
        title="INDICADORES",
        title_justify="left",
        title_style="bold",
        box=box.SIMPLE_HEAD,
        pad_edge=False,
        padding=(0, 2, 0, 1),
    )
    tabela.add_column("")
    tabela.add_column("atual", justify="right")
    tabela.add_column("12 meses", justify="right")
    tabela.add_column("histórico", justify="right", style="dim")
    for linha in raiox.indicadores:
        estilo = "yellow" if linha.alerta else ""
        marca = " ⚠" if linha.alerta else ""
        tabela.add_row(
            Text(linha.nome, style=estilo),
            Text(linha.atual, style=estilo),
            Text(linha.doze_meses + marca, style=estilo),
            linha.historico,
        )
    return tabela


def _secao_red_flags(raiox: RaioX) -> Group:
    if not raiox.red_flags:
        titulo = Text("✓ RED FLAGS — nenhum alerta disparado", style="bold green")
        return Group(Padding(titulo, (1, 0, 0, 1)))
    titulo = Text(
        f"🚩 RED FLAGS — {len(raiox.red_flags)} "
        f"alerta{'s' if len(raiox.red_flags) > 1 else ''}",
        style="bold red",
    )
    blocos: list = [Padding(titulo, (1, 0, 0, 1))]
    for flag in raiox.red_flags:
        blocos.append(Padding(_bloco_red_flag(flag), (1, 0, 0, 2)))
    return Group(*blocos)


def _bloco_red_flag(flag: RedFlag) -> Group:
    cabecalho = Text.assemble(
        (f" {flag.severidade.value} ", _COR_SEVERIDADE[flag.severidade]),
        ("  "),
        (flag.titulo, "bold"),
    )
    corpo = Group(
        Text(flag.fato),
        Text(f"evidência: {flag.evidencia}", style="dim"),
        Text(f"fonte: {flag.fonte}", style="dim italic"),
    )
    return Group(cabecalho, Padding(corpo, (0, 0, 0, 8)))


def _sem_alerta(raiox: RaioX) -> Padding:
    texto = Text.assemble(
        ("✓ sem alerta: ", "green"),
        ("; ".join(raiox.sem_alerta), "dim"),
    )
    return Padding(texto, (1, 0, 0, 2))
