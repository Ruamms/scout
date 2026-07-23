"""Interface de linha de comando do Scout."""

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
    help="Scout — nós exploramos, você decide. Fatos, não dicas.",
    no_args_is_help=False,
    add_completion=False,
)
console = Console()


@app.callback(invoke_without_command=True)
def principal(ctx: typer.Context) -> None:
    """Sem argumentos: modo interativo (ex.: duplo clique no scout.exe)."""
    if ctx.invoked_subcommand is not None:
        return
    if sys.stdin is not None and sys.stdin.isatty() and console.is_terminal:
        _modo_interativo()
    else:
        typer.echo(ctx.get_help())


def _modo_interativo() -> None:
    console.print()
    console.print("[bold]SCOUT[/] [dim]— nós exploramos, você decide[/]")
    console.print(
        "[dim]Comandos: [bold]TICKER[/bold] · [bold]TICKER html[/bold] (relatório com gráficos) · "
        "[bold]atualizar[/bold] · [bold]ranking \\[dy|pvp|pl|cotistas] \\[sem-alertas][/bold] · "
        "[bold]ia TICKER[/bold] · [bold]sair[/bold][/]"
    )
    while True:
        console.print()
        try:
            entrada = console.input("[bold cyan]scout> [/]").strip()
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
    if tokens and tokens[0].lower() == "scout":  # quem digita 'scout analisar X' também acerta
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


def _exibir_etf(con, ticker: str, html: bool) -> bool:
    """Ticker de ETF: gera a página própria (raio-x de ETF) e abre no navegador."""
    from . import armazenamento
    from .relatorio import etf_html

    dados = etf_html.montar_dados_etf(con, ticker)
    if dados is None:
        return False
    destino = armazenamento.diretorio_dados() / "relatorios"
    destino.mkdir(parents=True, exist_ok=True)
    caminho = destino / f"{dados['etf']['ticker']}.html"
    caminho.write_text(etf_html.gerar(dados), encoding="utf-8")
    classe = dados["classe"] or "ETF"
    console.print(
        f"[bold]{dados['etf']['ticker']}[/] é um ETF ([green]{classe}[/]) — "
        f"página própria gerada em [dim]{caminho}[/]"
    )
    if html:
        import webbrowser

        webbrowser.open(caminho.as_uri())
    else:
        console.print(f"  [dim]abra com: scout analisar {dados['etf']['ticker']} --html[/]")
    return True


def _exibir_acao(con, ticker: str, html: bool) -> bool:
    """Ticker de ação (IBrX-100): gera a página da empresa e abre no navegador."""
    from . import armazenamento
    from .relatorio import acao_html

    dados = acao_html.montar_dados_acao(con, ticker)
    if dados is None:
        return False
    from pathlib import Path

    from . import leituras

    leitura = leituras.carregar(Path("leituras"), dados["ticker"])
    destino = armazenamento.diretorio_dados() / "relatorios"
    destino.mkdir(parents=True, exist_ok=True)
    caminho = destino / f"{dados['ticker']}.html"
    caminho.write_text(acao_html.gerar(dados, leitura=leitura), encoding="utf-8")
    console.print(
        f"[bold]{dados['ticker']}[/] é uma ação ([green]{dados['empresa']['nome_pregao']}[/]) — "
        f"página da empresa gerada em [dim]{caminho}[/]"
    )
    if html:
        import webbrowser

        webbrowser.open(caminho.as_uri())
    else:
        console.print(f"  [dim]abra com: scout analisar {dados['ticker']} --html[/]")
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
            if _exibir_etf(con, ticker, html):
                return True
            if _exibir_acao(con, ticker, html):
                return True
            console.print(
                f"[red]Ticker '{ticker.strip().upper()}' não encontrado nos informes da CVM.[/] "
                "[dim]Confira o código ou rode 'scout atualizar' para renovar a base.[/]"
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
            console.print(f"  [dim]relatório com gráficos: scout analisar {raiox.ticker} --html[/]")
        return True
    finally:
        con.close()


def _gerar_html(completo) -> None:
    import webbrowser

    from . import armazenamento
    from .relatorio import html as relatorio_html

    destino = armazenamento.diretorio_dados() / "relatorios"
    caminho = relatorio_html.salvar(completo, destino)
    console.print(f"Relatório salvo em [bold]{caminho}[/] — abrindo no navegador…")
    webbrowser.open(caminho.as_uri())


def _oferecer_atualizacao(con, interativo: bool) -> bool:
    if not interativo:
        console.print("[yellow]Base local vazia.[/] Rode [bold]scout atualizar[/] para baixar os dados da CVM.")
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
    from .coleta import b3, cvm

    console.print(
        f"Baixando informes da CVM e cotações da B3 para [dim]{armazenamento.diretorio_dados()}[/]…"
    )
    hoje = date.today()
    total = (
        len(cvm.anos_pendentes(con, hoje))
        + len(cvm.anos_pendentes(con, hoje, cvm.nome_arquivo_trimestral))
        + len(b3.arquivos_pendentes(con, hoje))
    )
    from .coleta import b3fundos, b3rf, bancos, cda, empresas, etf_renda, fre, fundamentos, taxas_etf

    # empresas ANTES das cotações: o ajuste por eventos precisa dos papéis
    passos = [
        ("informes da CVM", lambda p: cvm.atualizar(con, ao_progredir=p)),
        ("empresas (IBrX-100)", lambda p: empresas.atualizar_empresas(con, ao_progredir=p)),
        ("balanços (DFP)", lambda p: fundamentos.atualizar(con, ao_progredir=p)),
        ("trimestres (ITR)", lambda p: fundamentos.atualizar_trimestres(con, ao_progredir=p)),
        ("FRE (administradores/partes)", lambda p: fre.atualizar(con, ao_progredir=p)),
        ("carreira (FREs antigos)", lambda p: fre.atualizar_historico(con, ao_progredir=p)),
        ("bancos (IF.data)", lambda p: bancos.atualizar_bancos(con, ao_progredir=p)),
        ("cotações da B3", lambda p: b3.atualizar(con, ao_progredir=p)),
        ("ETFs listados", lambda p: b3fundos.atualizar_etfs(con, ao_progredir=p)),
        ("carteiras de ETF", lambda p: cda.atualizar_composicao(con, ao_progredir=p)),
        ("cotações de renda fixa", lambda p: b3rf.atualizar_diaria(con, ao_progredir=p)),
        ("proventos de ETF", lambda p: etf_renda.atualizar_proventos(con, ao_progredir=p)),
        ("taxas de ETF (regulamento)", lambda p: taxas_etf.atualizar(con, ao_progredir=p)),
    ]

    def _rodar(avancar) -> None:
        # cada etapa é ISOLADA: uma fonte fora do ar (ex.: um proxy da B3
        # inacessível do GitHub Actions) não pode derrubar as demais e publicar
        # o site pela metade — foi assim que os ETFs zeraram
        for nome, passo in passos:
            try:
                passo(avancar)
            except Exception as erro:  # noqa: BLE001
                console.print(
                    f"  [yellow]etapa '{nome}' falhou[/] "
                    f"[dim]({type(erro).__name__}: {erro}) — seguindo com as demais[/]"
                )

    if not console.is_terminal:
        _rodar(lambda msg: console.print(f"  [dim]{msg}[/]"))
    else:
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as barra:
            tarefa = barra.add_task("CVM + B3", total=total)

            def _avanca(msg: str) -> None:
                barra.console.print(f"  [dim]{msg}[/]")
                barra.advance(tarefa)

            _rodar(_avanca)
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
            console.print("[yellow]Base local vazia.[/] Rode [bold]scout atualizar[/] primeiro.")
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


@app.command(name="etf-taxas-proposta")
def etf_taxas_proposta() -> None:
    """Lê o REGULAMENTO no FNET e preenche dados/taxas_etfs.csv (um lote).

    Acha a taxa → grava com a confiança (entra direto no site). Não acha → grava
    a linha como 'nao_achou'/'sem_regulamento' (fica aguardando você conferir e
    preencher). Incremental: quem já está no arquivo NÃO é relido. É o MESMO
    passo que roda dentro do `scout atualizar` — este comando só o dispara na mão.
    """
    from . import armazenamento
    from .coleta import taxas_etf

    con = armazenamento.conectar()
    try:
        mensagem = taxas_etf.atualizar(con, ao_progredir=lambda m: console.print(f"  [dim]{m}[/]"))
        if mensagem is None:
            console.print(
                "[green]Nada pendente[/] — todos os ETFs já estão no arquivo "
                "(ou você está rodando do executável, que não grava a curadoria)."
            )
    finally:
        con.close()


# Formulário de "Reportar bug" (Google Forms): a página e o ticker entram no
# campo do relato via {URL}/{TICKER} (o botão substitui no clique). Padrão do
# projeto; a variável de ambiente SCOUT_REPORT_URL sobrescreve, e "" desliga.
_URL_REPORTAR_PADRAO = (
    "https://docs.google.com/forms/d/e/"
    "1FAIpQLSftvZBa_cP1h6JUReAVytwsc89LfIX9nzy0qUM86VXX1QU2ZA/viewform?usp=pp_url"
    "&entry.1054971382=Pagina%3A%20{URL}%0AFundo%3A%20{TICKER}%0A%0AO%20que%20aconteceu%3A%0A"
)


@app.command()
def site(
    destino: str = typer.Option(None, "--destino", help="Pasta de saída (padrão: dados/site)."),
    sem_cotacoes: bool = typer.Option(False, "--sem-cotacoes", help="Não busca cotações na internet."),
    limite: int = typer.Option(None, "--limite", help="Gera só os N maiores fundos (para teste)."),
    leituras: str = typer.Option(
        None, "--leituras", help="Pasta com as leituras por IA (leituras/) para embutir nas páginas."
    ),
    analytics: str = typer.Option(
        None,
        "--analytics",
        help="Código GoatCounter (analytics sem cookie). Padrão: variável SCOUT_ANALYTICS.",
    ),
    reportar: str = typer.Option(
        None,
        "--reportar",
        help="URL do formulário de reportar bug (tokens {URL}/{TICKER}). "
        'Padrão: form do projeto (ou SCOUT_REPORT_URL; "" desliga).',
    ),
) -> None:
    """Gera o site estático completo: índice buscável + página de cada FII."""
    import os
    from pathlib import Path

    from . import armazenamento
    from .relatorio import site as modulo_site

    codigo_analytics = analytics if analytics is not None else os.environ.get("SCOUT_ANALYTICS", "")
    url_reportar = (
        reportar if reportar is not None
        else os.environ.get("SCOUT_REPORT_URL", _URL_REPORTAR_PADRAO)
    )

    con = armazenamento.conectar()
    try:
        if armazenamento.base_vazia(con):
            console.print("[yellow]Base local vazia.[/] Rode [bold]scout atualizar[/] primeiro.")
            raise typer.Exit(1)
        pasta = Path(destino) if destino else armazenamento.diretorio_dados() / "site"
        pasta_leituras = Path(leituras) if leituras else None
        console.print(f"Gerando site em [bold]{pasta}[/]…")
        if not console.is_terminal:
            resumo = modulo_site.gerar(
                con,
                pasta,
                com_cotacoes=not sem_cotacoes,
                limite=limite,
                ao_progredir=lambda msg: console.print(f"  [dim]{msg}[/]"),
                leituras_dir=pasta_leituras,
                analytics=codigo_analytics,
                reportar=url_reportar,
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
                    leituras_dir=pasta_leituras,
                    analytics=codigo_analytics,
                    reportar=url_reportar,
                )
        console.print(f"[green]{resumo['paginas']} páginas geradas em {resumo['destino']}[/]")
    finally:
        con.close()


@app.command()
def ia(
    ticker: str = typer.Argument(..., help="Código de negociação do FII, ex.: HGLG11."),
    modelo: str = typer.Option(None, "--modelo", help="Modelo do Ollama (padrão: qwen2.5:14b)."),
    sem_fatos: bool = typer.Option(
        False, "--sem-fatos", help="Lê só o relatório gerencial, sem os fatos relevantes."
    ),
) -> None:
    """Lê o relatório gerencial e os fatos relevantes do fundo com IA local (Ollama)."""
    from rich.panel import Panel

    from . import analise, armazenamento
    from . import ia as modulo_ia
    from .coleta import fnet

    con = armazenamento.conectar()
    try:
        if armazenamento.base_vazia(con):
            console.print("[yellow]Base local vazia.[/] Rode [bold]scout atualizar[/] primeiro.")
            raise typer.Exit(1)
        modelo_final = _preparar_ia(modelo)

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
        console.print(
            f"Lendo com o modelo [bold]{modelo_final}[/] (local)… a primeira resposta "
            "pode demorar alguns minutos enquanto o modelo processa o relatório."
        )
        with console.status("processando o relatório…") as estado:
            leitura = modulo_ia.analisar_relatorio(
                texto,
                contexto,
                modelo_final,
                ao_progresso=lambda n: estado.update(f"gerando a leitura… {n} trechos recebidos"),
            )

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

        if not sem_fatos:
            _ler_fatos_relevantes(con, fundo, contexto, modelo_final, ticker)
    finally:
        con.close()


def _preparar_ia(modelo: str | None) -> str:
    """Garante Ollama de pé e o modelo instalado; retorna o nome final."""
    from . import ia as modulo_ia

    if not modulo_ia.disponivel():
        console.print(
            "[red]Ollama não encontrado em http://localhost:11434.[/]\n"
            "Para usar a leitura por IA local (grátis, nada sai da sua máquina):\n"
            "  1. instale:  [bold]winget install Ollama.Ollama[/]\n"
            "  2. baixe um modelo:  [bold]ollama pull qwen2.5:14b[/]  "
            "(ou [bold]llama3.1:8b[/] se tiver menos de 16 GB de RAM)\n"
            "  3. rode de novo o comando"
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
    return modelo_final


def _ler_fatos_relevantes(con, fundo, contexto: str, modelo_final: str, ticker: str) -> None:
    from rich.panel import Panel

    from . import ia as modulo_ia
    from .coleta import fnet

    console.print()
    console.print(f"Buscando os últimos fatos relevantes de {ticker.upper()} no FNET…")
    try:
        documentos = fnet.garantir_fatos_relevantes(con, fundo.cnpj)
    except Exception:
        console.print("[yellow]Não foi possível buscar os fatos relevantes agora (rede?).[/]")
        return
    if not documentos:
        console.print("[dim]Nenhum fato relevante recente encontrado para este fundo.[/]")
        return

    fatos, ilegiveis = [], []
    for caminho, meta in documentos:
        texto = modulo_ia.extrair_texto_pdf(caminho, max_paginas=6)
        if len(texto) < 200:
            ilegiveis.append(meta["data_entrega"][:10])
            continue
        fatos.append((meta["data_entrega"][:10], texto))
        console.print(f"  [dim]fato relevante de {meta['data_entrega'][:10]} — {caminho}[/]")
    if ilegiveis:
        console.print(
            f"  [yellow]{len(ilegiveis)} documento(s) sem texto extraível (imagem/escaneado): "
            f"{', '.join(ilegiveis)} — abra os originais.[/]"
        )
    if not fatos:
        return

    with console.status("lendo os fatos relevantes…") as estado:
        leitura = modulo_ia.analisar_fatos_relevantes(
            fatos,
            contexto,
            modelo_final,
            ao_progresso=lambda n: estado.update(f"lendo os fatos relevantes… {n} trechos"),
        )
    console.print()
    console.print(
        Panel(
            leitura,
            title=f"[bold]Fatos relevantes recentes — {ticker.upper()} ({len(fatos)} documento(s))[/]",
            subtitle=f"[dim]IA local ({modelo_final}) · originais em ~/.scout/documentos[/]",
            padding=(1, 2),
        )
    )
    console.print(
        "[dim italic]Resumos gerados por IA a partir dos comunicados oficiais, com citação "
        "para conferência. Não é recomendação de investimento.[/]"
    )


@app.command(name="ia-lote")
def ia_lote(
    modelo: str = typer.Option(None, "--modelo", help="Modelo do Ollama (padrão: qwen2.5:14b — o mais confiável)."),
    destino: str = typer.Option("leituras", "--destino", help="Pasta dos JSONs de leitura (versionada no repo)."),
    limite: int = typer.Option(None, "--limite", help="Só os N maiores fundos (para teste)."),
    so_ticker: str = typer.Option(
        None, "--ticker", help="Lê só este ticker (ex.: BOVA11) — testa 1 fundo/ETF sem esperar a fila."
    ),
    sem_fatos: bool = typer.Option(False, "--sem-fatos", help="Só relatórios gerenciais."),
    apenas_erros: bool = typer.Option(
        False, "--apenas-erros", help="Reprocessa somente os fundos listados no arquivo de erros da rodada anterior."
    ),
    modelo_visao: str = typer.Option(
        None,
        "--modelo-visao",
        help="Modelo de visão do Ollama para relatórios escaneados (padrão: SCOUT_MODELO_VISAO "
        "ou llama3.2-vision se instalado). Não instalado = escaneado fica pulado, como hoje.",
    ),
) -> None:
    """Lê com IA os relatórios de TODOS os fundos negociáveis (incremental).

    Um por um, salvando ao terminar cada fundo. Pode interromper (Ctrl+C ou
    fechar a janela) e retomar depois: documento já lido é pulado. Fundos com
    erro são pulados e registrados em `<destino>/_erros.txt` — reprocesse só
    eles com --apenas-erros.
    """
    import time as _time
    from pathlib import Path

    from . import analise, armazenamento, leituras, ranking
    from . import ia as modulo_ia
    from .coleta import fnet

    con = armazenamento.conectar()
    try:
        if armazenamento.base_vazia(con):
            console.print("[yellow]Base local vazia.[/] Rode [bold]scout atualizar[/] primeiro.")
            raise typer.Exit(1)
        modelo_final = _preparar_ia(modelo)
        # visão é opcional: só para relatórios escaneados (imagem). Se não houver
        # modelo de visão instalado no Ollama, o escaneado segue "pulado".
        modelo_visao_final = modulo_ia.modelo_visao_instalado(modelo_visao)
        if modelo_visao_final:
            console.print(f"[dim]visão p/ escaneados: modelo [bold]{modelo_visao_final}[/][/]")
        pasta = Path(destino)
        arquivo_erros = pasta / "_erros.txt"

        base = ranking.varrer(con)
        fundos = sorted(
            (resumo for resumo in base if resumo.ticker),
            key=lambda resumo: resumo.pl or 0,
            reverse=True,
        )
        # fundo em liquidação/cancelado no registro CVM: a página exibe a red
        # flag, mas a leitura por IA não gasta tempo com quem está encerrando
        situacoes = ranking.situacoes_do_cadastro(con)

        def _encerrando(cnpj: str) -> bool:
            situacao = (situacoes.get(armazenamento.so_digitos(cnpj)) or "").upper()
            return situacao.startswith(("EM LIQUIDA", "CANCELAD"))

        pulados = [f.ticker for f in fundos if _encerrando(f.cnpj)]
        if pulados:
            fundos = [f for f in fundos if not _encerrando(f.cnpj)]
            console.print(
                f"[dim]{len(pulados)} fundos em liquidação/cancelados fora da fila "
                f"(a página deles mostra a red flag): {', '.join(pulados[:10])}"
                f"{'…' if len(pulados) > 10 else ''}[/]"
            )
        # fundo cujo ticker (derivado do ISIN) não resolve para um fundo real —
        # classe/não listado, ex.: 0NDO11 — NÃO gera página no site (é o mesmo
        # filtro do `scout site`). Auditado: 0 desses têm cotação. Não vale
        # gastar leitura de IA (o gargalo) com quem nunca vai aparecer.
        publicaveis = [f for f in fundos if armazenamento.resolver_fundo(con, f.ticker) is not None]
        nao_negociaveis = len(fundos) - len(publicaveis)
        if nao_negociaveis:
            fundos = publicaveis
            console.print(
                f"[dim]{nao_negociaveis} fundos não negociáveis fora da fila "
                f"(ticker do ISIN sem listagem em bolsa; não geram página no site)[/]"
            )
        vistos: set[str] = set()
        fundos = [f for f in fundos if not (f.ticker in vistos or vistos.add(f.ticker))]
        # E7: ETFs entram no fim da fila — sem relatório gerencial, o fluxo
        # sem_relatorio lê fatos/comunicados/assembleias e o parecer da DF
        from types import SimpleNamespace as _NS

        fundos += [
            _NS(ticker=etf["ticker"], cnpj=etf["cnpj"])
            for etf in armazenamento.etfs_listados(con)
            if etf["ticker"] not in vistos
        ]
        # A5: EMPRESAS no fim da fila — fatos relevantes/comunicados vêm do IPE
        # (índice anual da CVM, 1 download serve a fila toda) pelo mesmo fluxo
        # sem_relatorio dos ETFs. Um papel por empresa basta (o fato é da empresa).
        vistos_empresas: set[str] = set()
        for empresa in armazenamento.empresas_listadas(con):
            papeis_e = armazenamento.papeis_da_empresa(con, empresa["cod_cvm"])
            if not papeis_e or empresa["cod_cvm"] in vistos_empresas:
                continue
            vistos_empresas.add(empresa["cod_cvm"])
            fundos.append(
                _NS(
                    ticker=papeis_e[0]["ticker"], cnpj=empresa["cnpj"],
                    cod_cvm=empresa["cod_cvm"], classe="empresa",
                )
            )
        if so_ticker:
            alvo = so_ticker.strip().upper()
            fundos = [f for f in fundos if f.ticker.upper() == alvo]
            if not fundos:
                console.print(
                    f"[yellow]Ticker '{alvo}' não está na fila[/] — não é um FII/ETF "
                    "negociável conhecido (confira o código ou rode 'scout atualizar')."
                )
                raise typer.Exit(1)
        if apenas_erros:
            if not arquivo_erros.exists():
                console.print(f"[yellow]Nenhum arquivo de erros em {arquivo_erros} — nada a reprocessar.[/]")
                raise typer.Exit(0)
            com_erro = {
                linha.split()[0].upper()
                for linha in arquivo_erros.read_text(encoding="utf-8").splitlines()
                if linha.strip()
            }
            fundos = [f for f in fundos if f.ticker in com_erro]
            console.print(f"Reprocessando apenas os {len(fundos)} fundos com erro da rodada anterior.")
        if limite:
            fundos = fundos[:limite]

        console.print(
            f"Lote de leitura por IA: {len(fundos)} fundos · modelo [bold]{modelo_final}[/] · "
            f"destino [bold]{pasta}[/] · incremental por documento (interrompeu? rode de novo que continua)"
        )
        from datetime import datetime as _dt

        arquivo_historico = pasta / "_historico.txt"

        def _registrar(linha: str) -> None:
            """Histórico permanente do lote (versionado junto com as leituras):
            o que foi lido, o que não tinha relatório e o que falhou — com data,
            para comparar rodadas futuras."""
            pasta.mkdir(parents=True, exist_ok=True)
            with arquivo_historico.open("a", encoding="utf-8") as saida:
                saida.write(f"{_dt.now():%Y-%m-%d %H:%M:%S}\t{linha}\n")

        _registrar(f"--- lote iniciado · modelo {modelo_final} · {len(fundos)} fundos na fila")

        import concurrent.futures as _futures
        import queue as _queue
        import threading as _threading

        def _selecao(docs: list[dict]) -> tuple[dict | None, list[dict]]:
            relatorio = fnet.ultimo_relatorio_gerencial(docs)
            docs_meta = (
                []
                if sem_fatos
                else [
                    {**meta, "rotulo": "Fato Relevante"}
                    for meta in fnet.fatos_relevantes(docs, 3)
                ]
                + fnet.comunicados_e_assembleias(docs)
            )
            return relatorio, docs_meta

        # A IA é o gargalo (GPU) e fica estritamente sequencial; o prefetch
        # adianta a parte de REDE/DISCO (listagem no FNET + download dos PDFs).
        # É PARALELO (pool de threads) porque o `fnet.listar` de cada fundo
        # oscila e, em série, a fila de 1200+ fundos levava ~15 min só nas
        # checagens antes de a IA começar. `executor.map` PRESERVA A ORDEM — o
        # consumidor pareia `fundos[i]` com o i-ésimo item da fila. Timeout
        # curto: um fundo que pendura vira erro e é retomado na próxima rodada.
        # 8 era o mais rápido (5,1x vs serial), mas sob carga SUSTENTADA (lote de
        # 751) o FNET estrangula e devolve read-timeout em massa — poucos fundos
        # (ex.: --apenas-erros) quase não davam timeout. 5 pressiona menos e
        # segue ~4x mais rápido que serial; ajustável por SCOUT_PREFETCH_WORKERS.
        import os as _os
        _PREFETCH_WORKERS = max(1, int(_os.environ.get("SCOUT_PREFETCH_WORKERS", "5")))
        # O FNET oscila de forma intermitente: a mesma requisição ora responde
        # em 0,2s ora pendura (medido: o listar do MXRF11 deu timeout na 1ª e
        # voltou em 1,8s na 2ª). O que resolve é o RETRY — sem ele, um stall
        # solitário derrubava os maiores FIIs (MXRF11, KNRI11…). Timeout do
        # download é maior (PDF grande; HGRU11 levou 60s pra 2,9 MB).
        _TIMEOUT_LISTA, _TIMEOUT_DOC = 15, 90
        fila: _queue.Queue = _queue.Queue(maxsize=_PREFETCH_WORKERS * 2)
        _local = _threading.local()

        def _con_worker():
            # uma conexão por thread do pool (~8): SQLite proíbe usar/fechar uma
            # conexão fora da thread que a criou — ficam abertas até o processo
            # sair (batch curto), sem cross-thread close
            con_w = getattr(_local, "con", None)
            if con_w is None:
                con_w = _local.con = armazenamento.conectar()
                con_w.execute("PRAGMA busy_timeout=30000")  # 8 threads gravam o cache de docs
            return con_w

        def _preparar(resumo_p):
            """SÓ REDE/DISCO (roda numa thread do pool): lista o FNET e baixa
            os documentos novos. Retorna o `docs` bruto — o consumidor refaz a
            seleção e a decisão de leitura (fonte única da verdade)."""
            try:
                con_p = _con_worker()
                destino_docs = armazenamento.diretorio_dados() / "documentos"
                if getattr(resumo_p, "classe", None) == "empresa":
                    from .coleta import ipe

                    docs_p = ipe.listar(resumo_p.cod_cvm)
                    for meta_p in docs_p:
                        if meta_p["id"] not in leituras.ids_comunicados(
                            leituras.carregar(pasta, resumo_p.ticker)
                        ):
                            ipe.garantir_documento(con_p, resumo_p.cnpj, meta_p, destino_docs)
                    return docs_p, None
                # 80 documentos: fundo movimentado publica dezenas de informes
                # por ano e a DF anual cairia fora dos 30
                docs_p = fnet.listar(
                    resumo_p.cnpj, quantidade=80, timeout=_TIMEOUT_LISTA, tentativas=3
                )
                relatorio_p, docs_meta_p = _selecao(docs_p)
                df_p = fnet.ultima_demonstracao_financeira(docs_p)
                existente_p = leituras.carregar(pasta, resumo_p.ticker)
                ids_lidos_p = leituras.ids_comunicados(existente_p)
                # espelho da decisão do consumidor: fundo pulável não gasta download
                relatorio_reaproveitavel = bool(
                    relatorio_p
                    and existente_p
                    and existente_p.get("relatorio")
                    and existente_p["relatorio"]["id"] == relatorio_p["id"]
                    and existente_p["relatorio"].get("texto")
                )
                marcado_sem_relatorio = bool(
                    relatorio_p is None and existente_p and existente_p.get("sem_relatorio")
                )
                parecer_atual_p = df_p is None or bool(
                    existente_p and (existente_p.get("parecer") or {}).get("id") == df_p["id"]
                )
                pulavel = (
                    (relatorio_reaproveitavel or marcado_sem_relatorio)
                    and ids_lidos_p >= {meta["id"] for meta in docs_meta_p}
                    and parecer_atual_p
                )
                if not pulavel:
                    baixa = dict(timeout=_TIMEOUT_DOC, tentativas=3)  # retry o stall do FNET
                    if relatorio_p and not relatorio_reaproveitavel:
                        fnet._garantir_documento(con_p, resumo_p.cnpj, relatorio_p, destino_docs, **baixa)
                    for meta_p in docs_meta_p:
                        if meta_p["id"] not in ids_lidos_p:
                            fnet._garantir_documento(con_p, resumo_p.cnpj, meta_p, destino_docs, **baixa)
                    if df_p and not parecer_atual_p:
                        fnet._garantir_documento(con_p, resumo_p.cnpj, df_p, destino_docs, **baixa)
                return docs_p, None
            except Exception as erro_p:  # o consumidor registra a falha
                return None, erro_p

        def _prefetch() -> None:
            with _futures.ThreadPoolExecutor(max_workers=_PREFETCH_WORKERS) as executor:
                for resultado in executor.map(_preparar, fundos):
                    fila.put(resultado)  # ordem preservada

        _threading.Thread(target=_prefetch, daemon=True).start()

        def _proximo_da_fila() -> tuple[list[dict] | None, Exception | None]:
            # timeout curto mantém o Ctrl+C responsivo no Windows
            while True:
                try:
                    return fila.get(timeout=1)
                except _queue.Empty:
                    continue

        novos, pulados = 0, 0
        falhas: list[tuple[str, str]] = []
        inicio = _time.monotonic()
        for posicao, resumo in enumerate(fundos, start=1):
            prefixo = f"[{posicao}/{len(fundos)}] {resumo.ticker}"
            inicio_fundo = _time.monotonic()

            def _ler_documentos(docs_meta: list[dict], contexto: str) -> str | None:
                from .coleta import ipe as modulo_ipe

                itens = []
                for meta in docs_meta:
                    garantir = (
                        modulo_ipe.garantir_documento if meta.get("link") else fnet._garantir_documento
                    )
                    caminho_doc = garantir(
                        con, resumo.cnpj, meta, armazenamento.diretorio_dados() / "documentos",
                        timeout=90, tentativas=3,
                    )
                    texto_doc = modulo_ia.extrair_texto_pdf(caminho_doc, max_paginas=6)
                    if len(texto_doc) >= 200:
                        itens.append(
                            (meta.get("rotulo", "Fato Relevante"), meta["data_entrega"][:10], texto_doc)
                        )
                if not itens:
                    return None
                with console.status(f"{prefixo}: lendo fatos e comunicados…") as estado:
                    return modulo_ia.analisar_comunicados(
                        itens,
                        contexto,
                        modelo_final,
                        ao_progresso=lambda n: estado.update(
                            f"{prefixo}: lendo fatos e comunicados… {n} trechos recebidos"
                        ),
                    )

            def _processar_parecer(df: dict | None, existente: dict | None) -> dict | None:
                """Bloco `parecer` do JSON: classificação determinística do
                parecer do auditor na DF anual. Reaproveita quando a DF é a
                mesma; DF nova custa só download + regex (sem IA)."""
                from . import parecer as modulo_parecer

                if df is None:
                    return (existente or {}).get("parecer")
                if existente and (existente.get("parecer") or {}).get("id") == df["id"]:
                    return existente["parecer"]
                ilegivel = {"tipo": "nao_identificado", "rotulo": "PDF não legível (protegido/escaneado)",
                            "grave": False, "continuidade": False, "trecho": ""}
                try:
                    caminho_df = fnet._garantir_documento(
                        con, resumo.cnpj, df, armazenamento.diretorio_dados() / "documentos",
                        timeout=90, tentativas=3,
                    )
                    texto_df = modulo_ia.extrair_texto_pdf(caminho_df)
                    resultado = modulo_parecer.classificar(texto_df) if len(texto_df) >= 500 else ilegivel
                except Exception:  # DF problemática não derruba a leitura do fundo
                    resultado = ilegivel
                return {"id": df["id"], "data_entrega": df["data_entrega"], **resultado}

            def _parecer_atual(existente: dict | None, df: dict | None) -> bool:
                if df is None:
                    return True
                return bool(existente and (existente.get("parecer") or {}).get("id") == df["id"])

            def _doc_fre():
                if getattr(resumo, "classe", None) != "empresa":
                    return None
                return con.execute(
                    "SELECT * FROM fre_docs WHERE cod_cvm = ?", (resumo.cod_cvm,)
                ).fetchone()

            def _processos_atual(existente: dict | None) -> bool:
                doc = _doc_fre()
                if doc is None or not doc["link"]:
                    return True
                return bool(existente and (existente.get("processos") or {}).get("id") == doc["id_doc"])

            def _processar_processos(existente: dict | None) -> dict | None:
                """Empresas: seção de processos judiciais do FRE (PDF embutido)
                lida por IA — incremental por id do FRE (documento anual)."""
                doc = _doc_fre()
                if doc is None or not doc["link"]:
                    return (existente or {}).get("processos")
                if existente and (existente.get("processos") or {}).get("id") == doc["id_doc"]:
                    return existente["processos"]
                from .coleta import fre_processos

                caminho_p, valor_prov = fre_processos.garantir_pdf_processos(
                    doc["link"], doc["id_doc"],
                    armazenamento.diretorio_dados() / "documentos" / "fre",
                )
                bloco = {
                    "id": doc["id_doc"], "referencia": doc["referencia"],
                    "valor_provisionado": valor_prov,
                }
                if caminho_p:
                    texto_p = modulo_ia.extrair_texto_pdf(caminho_p, max_paginas=25)
                    if len(texto_p) >= 500:
                        with console.status(f"{prefixo}: lendo processos judiciais (FRE)…"):
                            bloco["texto"] = modulo_ia.analisar_processos(
                                texto_p, f"Empresa: {resumo.ticker}", modelo_final
                            )
                return bloco

            try:
                docs, erro_prefetch = _proximo_da_fila()
                if erro_prefetch is not None:
                    raise erro_prefetch
                relatorio, docs_meta = _selecao(docs)
                df = fnet.ultima_demonstracao_financeira(docs)
                existente = leituras.carregar(pasta, resumo.ticker)
                ids_novos = {meta["id"] for meta in docs_meta}
                # comunicados já lidos podem ser reaproveitados quando não há documento novo
                bloco_lido = leituras.bloco_comunicados_lido(existente)
                reusar_docs = bool(
                    docs_meta and bloco_lido and bloco_lido["texto"] and set(bloco_lido["ids"]) >= ids_novos
                )
                if relatorio is None:
                    # relatório gerencial é opcional no FNET; fatos relevantes,
                    # comunicados e assembleias, quando existem, são lidos mesmo assim
                    if existente and existente.get("sem_relatorio") and leituras.ids_comunicados(
                        existente
                    ) >= ids_novos and _parecer_atual(existente, df) and _processos_atual(existente):
                        pulados += 1
                        continue  # já marcado e sem documento novo
                    texto_docs = None
                    if docs_meta and not reusar_docs:
                        raiox = analise.montar_raio_x(con, resumo.ticker, varredura=base)
                        contexto = modulo_ia.contexto_do_raiox(raiox) if raiox else ""
                        texto_docs = _ler_documentos(docs_meta, contexto)
                    dados = leituras.montar_sem_relatorio(
                        resumo.ticker, docs_meta, texto_docs, modelo=modelo_final
                    )
                    if reusar_docs:
                        dados["comunicados"] = bloco_lido
                    bloco_parecer = _processar_parecer(df, existente)
                    if bloco_parecer:
                        dados["parecer"] = bloco_parecer
                    try:
                        bloco_processos = _processar_processos(existente)
                    except Exception:  # RAD fora do ar não derruba a leitura
                        bloco_processos = (existente or {}).get("processos")
                    if bloco_processos:
                        dados["processos"] = bloco_processos
                    leituras.salvar(pasta, dados)
                    if texto_docs:
                        novos += 1
                        _registrar(
                            f"{resumo.ticker}\tsem-relatorio-fatos-lidos\t{_time.monotonic() - inicio_fundo:.0f}s"
                        )
                        console.print(
                            f"{prefixo}: [green]fatos/comunicados lidos[/] [dim](fundo sem relatório gerencial)[/]"
                        )
                    else:
                        pulados += 1
                        _registrar(f"{resumo.ticker}\tsem-relatorio")
                        console.print(f"{prefixo}: [dim]sem relatório gerencial no FNET[/]")
                    continue
                if existente and existente.get("relatorio") and existente["relatorio"]["id"] == relatorio["id"] and leituras.ids_comunicados(
                    existente
                ) >= ids_novos and _parecer_atual(existente, df):
                    pulados += 1
                    if pulados % 25 == 0:
                        console.print(f"[dim][{posicao}/{len(fundos)}] {pulados} fundos já em dia até aqui…[/]")
                    continue  # nada novo desde a última leitura

                raiox = analise.montar_raio_x(con, resumo.ticker, varredura=base)
                contexto = modulo_ia.contexto_do_raiox(raiox) if raiox else ""
                meta_cotacao = armazenamento.cotacao_meta(con, resumo.ticker)
                snapshot = None
                if raiox is not None:
                    snapshot = {
                        "selo": raiox.selo.rotulo if raiox.selo else None,
                        "nivel": raiox.selo.nivel if raiox.selo else None,
                        "alertas": [flag.titulo for flag in raiox.red_flags],
                        "cota": meta_cotacao["preco_atual"] if meta_cotacao else None,
                    }

                # relatório já lido nesta versão do documento: reaproveita a
                # leitura e só processa os comunicados que faltam
                leitura_relatorio = None
                via_visao = False
                if (
                    existente
                    and existente.get("relatorio")
                    and existente["relatorio"]["id"] == relatorio["id"]
                    and existente["relatorio"].get("texto")
                ):
                    leitura_relatorio = existente["relatorio"]["texto"]
                if leitura_relatorio is None:
                    caminho = fnet._garantir_documento(
                        con, resumo.cnpj, relatorio, armazenamento.diretorio_dados() / "documentos",
                        timeout=90, tentativas=3,
                    )
                    texto = modulo_ia.extrair_texto_pdf(caminho)
                    if len(texto) < 500:
                        # relatório escaneado (imagem, sem texto). PLUS: se houver
                        # modelo de VISÃO instalado, lê pela imagem; senão fica
                        # "pulado" (terminal, NÃO vai para _erros.txt — repetir
                        # não geraria texto, e --apenas-erros o repetiria à toa).
                        leitura_visao = None
                        if modelo_visao_final:
                            with console.status(f"{prefixo}: lendo o relatório (imagem) por visão…"):
                                leitura_visao = modulo_ia.analisar_relatorio_imagem(
                                    caminho, contexto, modelo_visao_final
                                )
                        if leitura_visao is None:
                            texto_docs = (
                                _ler_documentos(docs_meta, contexto)
                                if docs_meta and not reusar_docs else None
                            )
                            dados = leituras.montar_relatorio_ilegivel(
                                resumo.ticker, relatorio, docs_meta, texto_docs, modelo=modelo_final
                            )
                            if reusar_docs:
                                dados["comunicados"] = bloco_lido
                            bloco_parecer = _processar_parecer(df, existente)
                            if bloco_parecer:
                                dados["parecer"] = bloco_parecer
                            leituras.salvar(pasta, dados)
                            console.print(
                                f"{prefixo}: [yellow]relatório em imagem/escaneado — "
                                "pulado (sem modelo de visão)[/]"
                            )
                            _registrar(f"{resumo.ticker}\tsem-texto\trelatorio id {relatorio['id']} (imagem/escaneado)")
                            pulados += 1
                            continue
                        # leu pela imagem: segue como uma leitura normal do relatório
                        leitura_relatorio = leitura_visao
                        via_visao = True
                    if not via_visao:
                        with console.status(f"{prefixo}: lendo o relatório com IA…") as estado:
                            leitura_relatorio = modulo_ia.analisar_relatorio(
                                texto,
                                contexto,
                                modelo_final,
                                ao_progresso=lambda n: estado.update(
                                    f"{prefixo}: lendo o relatório com IA… {n} trechos recebidos"
                                ),
                            )

                texto_docs = (
                    _ler_documentos(docs_meta, contexto) if docs_meta and not reusar_docs else None
                )

                dados = leituras.montar(
                    resumo.ticker,
                    modelo_visao_final if via_visao else modelo_final,
                    relatorio, leitura_relatorio, docs_meta, texto_docs,
                )
                if via_visao:
                    dados["relatorio"]["via_visao"] = True
                dados = leituras.anexar_snapshot(dados, snapshot, existente)
                if reusar_docs:
                    dados["comunicados"] = bloco_lido
                bloco_parecer = _processar_parecer(df, existente)
                if bloco_parecer:
                    dados["parecer"] = bloco_parecer
                leituras.salvar(pasta, dados)
                novos += 1
                decorrido = _time.monotonic() - inicio
                _registrar(f"{resumo.ticker}\tlido\t{_time.monotonic() - inicio_fundo:.0f}s")
                console.print(
                    f"{prefixo}: [green]lido[/] "
                    f"[dim]({decorrido / max(novos, 1):.0f}s/fundo em média)[/]"
                )
            except KeyboardInterrupt:
                console.print("\n[yellow]Interrompido — rode de novo para continuar de onde parou.[/]")
                _registrar(f"--- lote interrompido pelo usuário em {resumo.ticker}")
                break
            except Exception as erro:  # fundo problemático não derruba o lote
                falhas.append((resumo.ticker, str(erro)[:120]))
                _registrar(f"{resumo.ticker}\terro\t{str(erro)[:120]}")
                console.print(f"{prefixo}: [red]erro[/] [dim]{erro}[/]")

        if falhas:
            pasta.mkdir(parents=True, exist_ok=True)
            arquivo_erros.write_text(
                "\n".join(f"{ticker}\t{motivo}" for ticker, motivo in falhas) + "\n",
                encoding="utf-8",
            )
        elif not apenas_erros or novos:
            arquivo_erros.unlink(missing_ok=True)  # rodada limpa: some a lista antiga

        _registrar(f"--- lote encerrado · {novos} lidos, {pulados} em dia/sem relatório, {len(falhas)} erros")
        console.print(
            f"\n[bold]Lote concluído:[/] {novos} lidos, {pulados} já em dia, {len(falhas)} com erro."
        )
        # 2ª passada AUTOMÁTICA só nos timeouts de rede (transitórios do FNET, que
        # oscila sob carga): reprocessa esses sozinho, sequencialmente/gentil —
        # é o que a rodada --apenas-erros já fazia à mão (9→1). Só na 1ª rodada
        # (a recursão vai com apenas_erros=True, então não repete pra sempre).
        _REDE = ("timed out", "stream has ended", "connection reset", "connection aborted", "timeout")
        rede = [t for t, m in falhas if any(k in m.lower() for k in _REDE)]
        if rede and not apenas_erros and not so_ticker:
            console.print(
                f"\n[bold]2ª passada automática[/] nos {len(rede)} fundos com timeout de rede "
                "(o FNET oscila sob carga) — reprocessando só eles…"
            )
            _registrar(f"--- 2a passada automatica em {len(rede)} fundos com timeout de rede")
            con.close()  # a recursão abre a sua própria conexão (close é idempotente)
            ia_lote(
                modelo=modelo, destino=destino, limite=None, so_ticker=None,
                sem_fatos=sem_fatos, apenas_erros=True, modelo_visao=modelo_visao,
            )
            return
        if falhas:
            console.print(
                f"Fundos com erro registrados em [bold]{arquivo_erros}[/] — "
                "reprocesse só eles com [bold]scout ia-lote --apenas-erros[/]"
            )
        console.print(
            f"Para publicar no site: [bold]git add {pasta} && git commit -m 'leituras' && git push[/]"
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
