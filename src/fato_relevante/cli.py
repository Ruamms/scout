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
    console.print(
        "[dim]Comandos: [bold]TICKER[/bold] · [bold]TICKER html[/bold] (relatório com gráficos) · "
        "[bold]atualizar[/bold] · [bold]ranking \\[dy|pvp|pl|cotistas] \\[sem-alertas][/bold] · "
        "[bold]ia TICKER[/bold] · [bold]sair[/bold][/]"
    )
    while True:
        console.print()
        try:
            entrada = console.input("[bold cyan]fato> [/]").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not entrada:
            break
        try:
            if not _executar_entrada(entrada):
                break
        except typer.Exit:
            pass  # o erro já foi explicado na tela; o modo interativo continua


def _executar_entrada(entrada: str) -> bool:
    """Interpreta uma linha do modo interativo. False encerra o loop."""
    tokens = entrada.split()
    if tokens and tokens[0].lower() == "fato":  # quem digita 'fato analisar X' também acerta
        tokens = tokens[1:]
    if not tokens:
        return True
    comando = tokens[0].lower()

    if comando in ("sair", "exit", "quit"):
        return False
    if comando == "atualizar":
        from . import armazenamento

        con = armazenamento.conectar()
        try:
            _executar_atualizacao(con)
        finally:
            con.close()
        return True
    if comando == "ranking":
        from . import ranking as modulo_ranking

        por = next((t.lower() for t in tokens[1:] if t.lower() in modulo_ranking.CRITERIOS), "dy")
        sem_alertas = any("sem-alertas" in t.lower() for t in tokens[1:])
        _mostrar_ranking(por=por, top=10, sem_alertas=sem_alertas, segmento=None)
        return True
    if comando == "ia":
        if len(tokens) < 2:
            console.print("[yellow]Uso: ia TICKER (ex.: ia HGLG11)[/]")
            return True
        ia(ticker=tokens[1], modelo=None)
        return True
    if comando == "analisar":
        tokens = tokens[1:]
        if not tokens:
            console.print("[yellow]Uso: analisar TICKER \\[html][/]")
            return True

    ticker = tokens[0]
    html = any(t.lower() in ("html", "--html") for t in tokens[1:])
    _exibir_raio_x(ticker, html=html, interativo=True)
    return True


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
    from .relatorio import apoio
    from .relatorio import html as relatorio_html

    destino = armazenamento.diretorio_dados() / "relatorios"
    caminho = relatorio_html.salvar(completo, destino)
    apoio.salvar(destino)
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
    from datetime import date

    from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn

    from . import armazenamento
    from .coleta import cvm

    console.print(f"Baixando informes de FII da CVM para [dim]{armazenamento.diretorio_dados()}[/]…")
    hoje = date.today()
    total = len(cvm.anos_pendentes(con, hoje)) + len(
        cvm.anos_pendentes(con, hoje, cvm.nome_arquivo_trimestral)
    )
    if not console.is_terminal:
        cvm.atualizar(con, ao_progredir=lambda msg: console.print(f"  [dim]{msg}[/]"))
    else:
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as barra:
            tarefa = barra.add_task("informes CVM", total=total)

            def _avanca(msg: str) -> None:
                barra.console.print(f"  [dim]{msg}[/]")
                barra.advance(tarefa)

            cvm.atualizar(con, ao_progredir=_avanca)
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
def ranking(
    por: str = typer.Option("dy", "--por", help="Critério: dy, pvp, pl, cotistas ou cotacao."),
    top: int = typer.Option(10, "--top", help="Quantos fundos listar."),
    sem_alertas: bool = typer.Option(
        False, "--sem-alertas", help="Só fundos sem alertas de atenção ou graves."
    ),
    segmento: str = typer.Option(None, "--segmento", help="Filtra por segmento (contém)."),
    incluir_nao_listados: bool = typer.Option(
        False, "--incluir-nao-listados", help="Inclui fundos sem ticker (não negociáveis)."
    ),
) -> None:
    """Ranking de FIIs da base local — fato ordenado com critério explícito."""
    _mostrar_ranking(por, top, sem_alertas, segmento, incluir_nao_listados)


def _mostrar_ranking(
    por: str,
    top: int = 10,
    sem_alertas: bool = False,
    segmento: str | None = None,
    incluir_nao_listados: bool = False,
) -> None:
    from . import armazenamento
    from . import ranking as modulo_ranking
    from .relatorio.terminal import renderizar_ranking

    con = armazenamento.conectar()
    try:
        if armazenamento.base_vazia(con):
            console.print("[yellow]Base local vazia.[/] Rode [bold]fato atualizar[/] primeiro.")
            raise typer.Exit(1)
        try:
            resultado = modulo_ranking.montar(
                con,
                por=por,
                top=top,
                sem_alertas=sem_alertas,
                segmento=segmento,
                apenas_negociaveis=not incluir_nao_listados,
            )
        except ValueError as erro:
            console.print(f"[red]{erro}[/]")
            raise typer.Exit(1) from erro
        renderizar_ranking(resultado, console)
    finally:
        con.close()


@app.command()
def site(
    destino: str = typer.Option(None, "--destino", help="Pasta de saída (padrão: dados/site)."),
    sem_cotacoes: bool = typer.Option(False, "--sem-cotacoes", help="Não busca cotações na internet."),
    limite: int = typer.Option(None, "--limite", help="Gera só os N maiores fundos (para teste)."),
) -> None:
    """Gera o site estático completo: índice buscável + página de cada FII."""
    from pathlib import Path

    from . import armazenamento
    from .relatorio import site as modulo_site

    con = armazenamento.conectar()
    try:
        if armazenamento.base_vazia(con):
            console.print("[yellow]Base local vazia.[/] Rode [bold]fato atualizar[/] primeiro.")
            raise typer.Exit(1)
        pasta = Path(destino) if destino else armazenamento.diretorio_dados() / "site"
        console.print(f"Gerando site em [bold]{pasta}[/]…")
        if not console.is_terminal:
            resumo = modulo_site.gerar(
                con,
                pasta,
                com_cotacoes=not sem_cotacoes,
                limite=limite,
                ao_progredir=lambda msg: console.print(f"  [dim]{msg}[/]"),
            )
        else:
            from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn

            with Progress(
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=console,
            ) as barra:
                tarefas: dict[str, object] = {}

                def _item(fase: str, atual: int, total: int) -> None:
                    if fase not in tarefas:
                        tarefas[fase] = barra.add_task(fase, total=total)
                    barra.update(tarefas[fase], completed=atual, total=total)

                resumo = modulo_site.gerar(
                    con,
                    pasta,
                    com_cotacoes=not sem_cotacoes,
                    limite=limite,
                    ao_item=_item,
                )
        console.print(f"[green]{resumo['paginas']} páginas geradas em {resumo['destino']}[/]")
    finally:
        con.close()


@app.command()
def ia(
    ticker: str = typer.Argument(..., help="Código de negociação do FII, ex.: HGLG11."),
    modelo: str = typer.Option(None, "--modelo", help="Modelo do Ollama (padrão: qwen2.5:14b)."),
) -> None:
    """Lê o último relatório gerencial do fundo com IA local (Ollama)."""
    from rich.panel import Panel

    from . import analise, armazenamento
    from . import ia as modulo_ia
    from .coleta import fnet

    con = armazenamento.conectar()
    try:
        if armazenamento.base_vazia(con):
            console.print("[yellow]Base local vazia.[/] Rode [bold]fato atualizar[/] primeiro.")
            raise typer.Exit(1)
        if not modulo_ia.disponivel():
            console.print(
                "[red]Ollama não encontrado em http://localhost:11434.[/]\n"
                "Para usar a leitura por IA local (grátis, nada sai da sua máquina):\n"
                "  1. instale:  [bold]winget install Ollama.Ollama[/]\n"
                "  2. baixe um modelo:  [bold]ollama pull qwen2.5:14b[/]  "
                "(ou [bold]llama3.1:8b[/] se tiver menos de 16 GB de RAM)\n"
                "  3. rode de novo:  [bold]fato ia " + ticker.upper() + "[/]"
            )
            raise typer.Exit(1)
        modelo_final = modelo or modulo_ia.MODELO_PADRAO
        instalados = modulo_ia.modelos_instalados()
        if not any(nome.startswith(modelo_final.split(":")[0]) for nome in instalados):
            console.print(
                f"[red]Modelo '{modelo_final}' não está instalado no Ollama.[/] "
                f"Instalados: {', '.join(instalados) or 'nenhum'}.\n"
                f"Baixe com: [bold]ollama pull {modelo_final}[/] ou use [bold]--modelo[/]."
            )
            raise typer.Exit(1)

        fundo = armazenamento.resolver_fundo(con, ticker)
        if fundo is None:
            console.print(f"[red]Ticker '{ticker.strip().upper()}' não encontrado.[/]")
            raise typer.Exit(1)

        console.print(f"Buscando o último relatório gerencial de {ticker.upper()} no FNET…")
        resultado = fnet.garantir_relatorio(con, fundo.cnpj)
        if resultado is None:
            console.print("[yellow]Nenhum relatório gerencial encontrado no FNET para este fundo.[/]")
            raise typer.Exit(1)
        caminho, meta = resultado
        console.print(f"  [dim]{meta['tipo']} de {meta['data_entrega']} — {caminho}[/]")

        console.print("Extraindo texto do PDF…")
        texto = modulo_ia.extrair_texto_pdf(caminho)
        if len(texto) < 500:
            console.print(
                "[yellow]O PDF tem pouco texto extraível (provavelmente é imagem/escaneado) — "
                "a leitura por IA ficaria pobre. Abra o original:[/] " + str(caminho)
            )
            raise typer.Exit(1)

        raiox = analise.montar_raio_x(con, ticker)
        contexto = modulo_ia.contexto_do_raiox(raiox) if raiox else ""
        console.print(f"Lendo com o modelo [bold]{modelo_final}[/] (local)… pode levar alguns minutos.")
        leitura = modulo_ia.analisar_relatorio(texto, contexto, modelo_final)

        console.print()
        console.print(
            Panel(
                leitura,
                title=f"[bold]Leitura do relatório gerencial — {ticker.upper()} ({meta['data_entrega'][:10]})[/]",
                subtitle=f"[dim]IA local ({modelo_final}) · confira o original: {caminho}[/]",
                padding=(1, 2),
            )
        )
        console.print(
            "[dim italic]Resumo gerado por IA a partir do relatório oficial — pode conter "
            "erros de leitura; os trechos citados permitem conferir. Não é recomendação "
            "de investimento.[/]"
        )
    finally:
        con.close()


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
