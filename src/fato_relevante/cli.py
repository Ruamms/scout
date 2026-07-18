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
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


@app.command()
def analisar(
    ticker: str = typer.Argument(..., help="Código de negociação do ativo, ex.: ADSH11."),
    html: bool = typer.Option(False, "--html", help="Gera o relatório em HTML e abre no navegador."),
) -> None:
    """Monta o raio-x de um ativo a partir do cache local de dados oficiais."""
    from .dados_exemplo import raio_x_exemplo
    from .relatorio.terminal import renderizar

    raiox = raio_x_exemplo(ticker.strip().upper())
    renderizar(raiox, console)
    if html:
        console.print("[yellow]Relatório HTML ainda não implementado (milestone 5 do ROADMAP).[/]")


@app.command()
def atualizar() -> None:
    """Baixa/atualiza os dados abertos da CVM para o cache local."""
    console.print("[yellow]Coletor CVM ainda não implementado (milestone 2 do ROADMAP).[/]")


if __name__ == "__main__":
    app()
