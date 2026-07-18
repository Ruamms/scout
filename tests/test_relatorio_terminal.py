from rich.console import Console
from typer.testing import CliRunner

from fato_relevante.cli import app
from fato_relevante.dados_exemplo import raio_x_exemplo
from fato_relevante.modelos import RaioX
from fato_relevante.relatorio.terminal import renderizar


def _render(raiox: RaioX) -> str:
    console = Console(record=True, width=100)
    renderizar(raiox, console)
    return console.export_text()


def test_renderiza_raio_x_completo():
    saida = _render(raio_x_exemplo("ADSH11"))
    assert "ADSH11" in saida
    assert "RED FLAGS" in saida
    assert "evidência:" in saida
    assert "fonte:" in saida
    # o disclaimer legal precisa aparecer em toda saída
    assert "não é recomendação de investimento" in saida


def test_dados_de_exemplo_exibem_aviso():
    saida = _render(raio_x_exemplo("XPTO11"))
    assert "DADOS DE EXEMPLO" in saida


def test_cli_analisar_renderiza_ticker():
    resultado = CliRunner().invoke(app, ["analisar", "adsh11"])
    assert resultado.exit_code == 0
    assert "ADSH11" in resultado.output


def test_cli_sem_argumentos_fora_de_terminal_mostra_ajuda():
    # stdin do CliRunner não é um TTY, então deve cair na ajuda, não no interativo
    resultado = CliRunner().invoke(app, [])
    assert resultado.exit_code == 0
    assert "analisar" in resultado.output


def test_sem_red_flags_mostra_nenhum_alerta():
    raiox = RaioX(
        ticker="XPTO11",
        nome="FUNDO SEM ALERTAS",
        cnpj="00.000.000/0001-00",
        classificacao="Lajes",
        gestao="Passiva",
        dados_ate="05/2026",
    )
    saida = _render(raiox)
    assert "nenhum alerta disparado" in saida
