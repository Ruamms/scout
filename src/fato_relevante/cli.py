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
        _exibir_raio_x(ticker, interativo=True)


def _exibir_raio_x(ticker: str, html: bool = False, interativo: bool = False) -> bool:
    from . import analise, armazenamento
    from .relatorio.terminal import renderizar

    from .coleta import cotacoes, indices

    con = armazenamento.conectar()
    try:
        if armazenamento.base_vazia(con) and not _oferecer_atualizacao(con, interativo):
            return False
        aviso_cotacao = cotacoes.garantir_atualizada(con, ticker)
        aviso_indices = indices.garantir_atualizados(con)
        completo = analise.montar_completo(con, ticker)
        if completo is None:
            console.print(
                f"[red]Ticker '{ticker.strip().upper()}' não encontrado nos informes da CVM.[/] "
                "[dim]Confira o código ou rode 'fato atualizar' para renovar a base.[/]"
            )
            return False
        raiox = completo.raiox
        sem_cotacao = any("sem cotação de bolsa" in nota for nota in raiox.notas)
        if aviso_cotacao and not sem_cotacao:
            raiox.notas.insert(0, aviso_cotacao)
        if aviso_indices:
            raiox.notas.insert(0, aviso_indices)
        renderizar(raiox, console)
        if html:
            _gerar_html(completo)
        elif interativo:
            console.print(f"  [dim]relatório com gráficos: fato analisar {raiox.ticker} --html[/]")
        return True
    finally:
        con.close()


def _gerar_html(completo) -> None:
    import webbrowser

    from . import armazenamento
    from .relatorio import html as relatorio_html

    caminho = relatorio_html.salvar(completo, armazenamento.diretorio_dados() / "relatorios")
    console.print(f"Relatório salvo em [bold]{caminho}[/] — abrindo no navegador…")
    webbrowser.open(caminho.as_uri())


def _oferecer_atualizacao(con, interativo: bool) -> bool:
    if not interativo:
        console.print("[yellow]Base local vazia.[/] Rode [bold]fato atualizar[/] para baixar os dados da CVM.")
        return False
    resposta = console.input(
        "Base local vazia. Baixar agora os informes de FII da CVM (~10 MB)? [S/n] "
    )
    if resposta.strip().lower() not in ("", "s", "sim"):
        return False
    _executar_atualizacao(con)
    return True


def _executar_atualizacao(con) -> None:
    from . import armazenamento
    from .coleta import cvm

    console.print(f"Baixando informes mensais de FII da CVM para [dim]{armazenamento.diretorio_dados()}[/]…")
    cvm.atualizar(con, ao_progredir=lambda msg: console.print(f"  [dim]{msg}[/]"))
    console.print("[green]Base atualizada.[/]")


@app.command()
def analisar(
    ticker: str = typer.Argument(..., help="Código de negociação do ativo, ex.: ADSH11."),
    html: bool = typer.Option(False, "--html", help="Gera o relatório em HTML e abre no navegador."),
) -> None:
    """Monta o raio-x de um ativo a partir do cache local de dados oficiais."""
    if not _exibir_raio_x(ticker, html):
        raise typer.Exit(1)


@app.command()
def atualizar() -> None:
    """Baixa/atualiza os dados abertos da CVM para o cache local."""
    from . import armazenamento

    con = armazenamento.conectar()
    try:
        _executar_atualizacao(con)
    finally:
        con.close()


if __name__ == "__main__":
    app()
