"""Interface de linha de comando do Fato Relevante."""

from __future__ import annotations

import sys

import typer
from rich.console import Console


def _garantir_stdio_utf8() -> None:
    """Evita UnicodeEncodeError quando a saída é redirecionada (pipe/arquivo).

    Em console interativo o Windows usa WriteConsoleW e nada muda; em pipe,
    o Python herda a codepage legada (cp850/cp1252), que não tem ⚠, · etc.
    """
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


_garantir_stdio_utf8()

app = typer.Typer(
    help="Fato Relevante — o raio-x dos ativos da bolsa. Fatos, não dicas.",
    no_args_is_help=False,
    add_completion=False,
)
console = Console()


@app.callback(invoke_without_command=True)
def principal(ctx: typer.Context) -> None:
    """Sem argumentos: modo interativo (ex.: duplo clique no fato.exe)."""
    if ctx.invoked_subcommand is not None:
        return
    if sys.stdin is not None and sys.stdin.isatty() and console.is_terminal:
        _modo_interativo()
    else:
        typer.echo(ctx.get_help())


def _modo_interativo() -> None:
    console.print()
    console.print("[bold]FATO RELEVANTE[/] [dim]— o raio-x dos ativos da bolsa[/]")
    console.print("[dim]Digite o ticker de um ativo (ex.: ADSH11) ou Enter para sair.[/]")
    while True:
        console.print()
        try:
            ticker = console.input("[bold cyan]ticker> [/]").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not ticker:
            break
        _exibir_raio_x(ticker)


def _exibir_raio_x(ticker: str, html: bool = False) -> None:
    from .dados_exemplo import raio_x_exemplo
    from .relatorio.terminal import renderizar

    raiox = raio_x_exemplo(ticker.strip().upper())
    renderizar(raiox, console)
    if html:
        console.print("[yellow]Relatório HTML ainda não implementado (milestone 5 do ROADMAP).[/]")


@app.command()
def analisar(
    ticker: str = typer.Argument(..., help="Código de negociação do ativo, ex.: ADSH11."),
    html: bool = typer.Option(False, "--html", help="Gera o relatório em HTML e abre no navegador."),
) -> None:
    """Monta o raio-x de um ativo a partir do cache local de dados oficiais."""
    _exibir_raio_x(ticker, html)


@app.command()
def atualizar() -> None:
    """Baixa/atualiza os dados abertos da CVM para o cache local."""
    console.print("[yellow]Coletor CVM ainda não implementado (milestone 2 do ROADMAP).[/]")


if __name__ == "__main__":
    app()
